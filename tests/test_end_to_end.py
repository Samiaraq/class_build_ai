
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from classbuild.course_config import validate_course_config
from classbuild.services.course_generator import CourseGenerator
from classbuild.services.lesson_generator import LessonGenerator
from classbuild.services.quiz_generator import QuizGenerator
from classbuild.services.quiz_grader import grade_quiz
from classbuild.services.grounded_lesson_generator import (
    GroundedLessonDraft,
    GroundedSectionDraft,
    GroundedLessonGenerator,
    SCHEMA_NAME as GROUNDED_SCHEMA_NAME,
)
from classbuild.rag.pdf_processor import process_pdf
from classbuild.rag.embeddings import EmbeddingService
from classbuild.rag.retriever import build_index, search
from classbuild.persistence import (
    CourseStore,
    build_saved_course,
    new_course_id,
)

from classbuild.export import course_to_markdown, course_filename

from tests.fixtures import (
    valid_outline,
    valid_lesson,
    valid_quiz,
    QUIZ_CORRECT_ANSWERS,
)
from tests.embedding_fakes import FakeEncoder
from tests.pdf_fixtures import make_pdf


class ScriptedGroq:
    """Prepared Groq responses, selected by schema name."""

    def __init__(self, answers):
        self.answers = dict(answers)
        self.calls = []

    def generate_json(self, **kwargs):
        self.calls.append(kwargs)

        schema_name = kwargs["schema_name"]

        if schema_name not in self.answers:
            raise AssertionError(
                f"Unexpected Groq schema request: {schema_name}"
            )

        return self.answers.pop(schema_name)


class EndToEndTests(unittest.TestCase):

    def test_complete_course_workflow(self):

        config = validate_course_config(
            topic="Python Programming",
            difficulty="Beginner",
            lesson_count=3,
        )

        outline_data = valid_outline(
            lesson_count=config.lesson_count,
            difficulty=config.difficulty,
        )

        first_lesson_title = outline_data["lessons"][0]["title"]

        lesson_data = valid_lesson(
            lesson_number=1,
            title=first_lesson_title,
        )

        quiz_data = valid_quiz(
            lesson_number=1,
            lesson_title=first_lesson_title,
        )

        grounded_draft = GroundedLessonDraft(
            lesson_number=1,
            title=first_lesson_title,
            introduction=(
                "Python is a programming language used to build software."
            ),
            sections=[
                GroundedSectionDraft(
                    source_ids=["p1-c1"],
                    heading="Python Programming",
                    explanation=(
                        "Python is a programming language."
                    ),
                    example="print('Hello, world!')",
                ),
                GroundedSectionDraft(
                    source_ids=["p1-c1"],
                    heading="Python Features",
                    explanation=(
                        "Python supports functions and classes."
                    ),
                    example="def greet():\n    print('Hello')",
                ),
            ],
            summary="Python provides tools for writing programs.",
            exercises=[
                {
                    "question": "What is Python?",
                    "hint": "Think about its role in programming.",
                },
                {
                    "question": "What is a function?",
                    "hint": "Think about reusable instructions.",
                },
            ],
            evidence_relevant=True,
        )

        groq = ScriptedGroq({
            "course_outline": outline_data,
            "lesson_content": lesson_data,
            "lesson_quiz": quiz_data,
            GROUNDED_SCHEMA_NAME: grounded_draft.model_dump(),
        })

        with patch(
            "socket.socket.connect",
            side_effect=AssertionError("Network access is blocked."),
        ), patch(
            "socket.create_connection",
            side_effect=AssertionError("Network access is blocked."),
        ):

            outline = CourseGenerator(
                client=groq
            ).generate_outline(config)

            self.assertEqual(
                len(outline.lessons),
                config.lesson_count,
            )

            lesson = LessonGenerator(
                client=groq
            ).generate_lesson(outline, 1)

            self.assertEqual(
                lesson.title,
                outline.lessons[0].title,
            )

            quiz = QuizGenerator(
                client=groq
            ).generate_quiz(
                outline,
                1,
                lesson,
            )

            result = grade_quiz(
                quiz,
                QUIZ_CORRECT_ANSWERS,
            )

            self.assertEqual(result.percentage, 100)
            self.assertEqual(len(result.question_results), 5)

            pdf_bytes = make_pdf([
                (
                    "Python is a programming language. "
                    "Python code is used to build software. "
                    "Python supports functions and classes. "
                    "Programming uses instructions and algorithms. "
                    "Python is useful for learning computer science."
                )
            ])

            document = process_pdf(
                "python-guide.pdf",
                pdf_bytes,
            )

            self.assertGreater(document.chunk_count, 0)

            encoder = FakeEncoder()
            embedding_service = EmbeddingService(
                model=encoder
            )

            index = build_index(
                document,
                embedding_service,
            )

            results = search(
                index,
                document,
                "Python programming language and software code",
                embedding_service,
            )

            self.assertTrue(results)
            self.assertEqual(
                results[0].source_filename,
                "python-guide.pdf",
            )

            grounded_lesson = GroundedLessonGenerator(
                client=groq,
                embedding_service=embedding_service,
            ).generate_lesson(
                outline,
                1,
                document,
                index,
            )

            self.assertTrue(grounded_lesson.is_grounded)
            self.assertEqual(
                grounded_lesson.grounding.document_fingerprint,
                document.fingerprint,
            )
            self.assertTrue(grounded_lesson.grounding.sources)
            self.assertEqual(
                grounded_lesson.cited_pages,
                [1],
            )

            with tempfile.TemporaryDirectory() as temp_dir:
                store = CourseStore(directory=temp_dir)

                saved_course = build_saved_course(
                    course_id=new_course_id(),
                    topic=config.topic,
                    outline=outline,
                    lessons=[grounded_lesson],
                    quizzes={},
                )

                saved_path = store.save(saved_course)

                self.assertTrue(saved_path.is_file())

                raw_saved_data = saved_path.read_text(
                    encoding="utf-8"
                )

                self.assertNotIn("api_key", raw_saved_data.lower())
                self.assertNotIn("embedding", raw_saved_data.lower())
                self.assertNotIn("chat", raw_saved_data.lower())

                loaded_course = store.load(
                    saved_course.course_id
                )

                self.assertEqual(
                    loaded_course.content_hash(),
                    saved_course.content_hash(),
                )

                self.assertEqual(
                    loaded_course.lessons_by_number()[1],
                    grounded_lesson,
                )
                
                markdown = course_to_markdown(
                    outline,
                    config.topic,
                    [grounded_lesson],
                    {},
                )

                self.assertIn(outline.title, markdown)
                self.assertIn(grounded_lesson.title, markdown)
                self.assertIn("Sources", markdown)

                filename = course_filename(outline.title)

                self.assertTrue(filename.endswith(".md"))
                self.assertNotIn("/", filename)
                self.assertNotIn("\\", filename)

        self.assertEqual(len(groq.calls), 4)
        self.assertEqual(groq.answers, {})

        requested_schemas = [
            call["schema_name"]
            for call in groq.calls
        ]

        self.assertCountEqual(
            requested_schemas,
            [
                "course_outline",
                "lesson_content",
                "lesson_quiz",
                GROUNDED_SCHEMA_NAME,
            ],
        )


if __name__ == "__main__":
    unittest.main()
