import json
import tempfile
import unittest
from pathlib import Path

from classbuild.models.course import validate_outline
from classbuild.models.lesson import validate_lesson
from classbuild.models.quiz import validate_quiz

from classbuild.persistence import (
    CourseStore,
    SavedCourse,
    SourceDocument,
    build_saved_course,
    new_course_id,
    CourseStorageError,
    InvalidCourseIdError,
    CourseNotFoundError,
    CourseFileTooLargeError,
    CorruptedCourseFileError,
    UnsupportedSchemaVersionError,
)

from classbuild.export import course_to_markdown, course_filename

from tests.fixtures import (
    valid_outline,
    valid_lesson,
    valid_quiz,
)

from classbuild.services.grounded_lesson_generator import draft_to_lesson

from tests.test_grounded_lessons import (
    make_document,
    make_results,
    make_draft,
)


class CourseStoreTests(unittest.TestCase):

    def test_save_and_load_course(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CourseStore(directory=temp_dir)

            course = build_saved_course(
                course_id=new_course_id(),
                topic="Python Programming",
                outline=valid_outline(),
                lessons=[valid_lesson()],
                quizzes=[valid_quiz()],
            )

            saved_path = store.save(course)
            loaded_course = store.load(course.course_id)

            self.assertTrue(saved_path.exists())
            self.assertEqual(loaded_course.course_id, course.course_id)
            self.assertEqual(loaded_course.topic, course.topic)
            self.assertEqual(
                loaded_course.outline,
                course.outline,
            )
            self.assertEqual(
                loaded_course.lessons,
                course.lessons,
            )
            self.assertEqual(
                loaded_course.quizzes,
                course.quizzes,
            )

    def test_update_saved_course(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CourseStore(directory=temp_dir)

            course = build_saved_course(
                course_id=new_course_id(),
                topic="Python Programming",
                outline=valid_outline(),
                lessons=[valid_lesson()],
                quizzes=[valid_quiz()],
            )

            store.save(course)

            updated_course = course.model_copy(
                update={"topic": "Advanced Python"}
            )
            store.save(updated_course)

            loaded_course = store.load(course.course_id)

            self.assertEqual(loaded_course.topic, "Advanced Python")

    def test_list_saved_courses(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CourseStore(directory=temp_dir)

            course = build_saved_course(
                course_id=new_course_id(),
                topic="Python Programming",
                outline=valid_outline(),
                lessons=[valid_lesson()],
                quizzes=[valid_quiz()],
            )

            store.save(course)

            listing = store.list_courses()

            self.assertEqual(len(listing.courses), 1)
            self.assertEqual(
                listing.courses[0].course_id,
                course.course_id,
            )
            self.assertEqual(
                listing.courses[0].topic,
                "Python Programming",
            )
            self.assertEqual(listing.issues, ())

    def test_grounded_lesson_sources_survive_save_and_load(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CourseStore(directory=temp_dir)

            document = make_document()
            results = make_results()
            draft = make_draft()

            grounded_lesson = draft_to_lesson(
                draft,
                results,
                document,
                "Python programming basics",
            )

            course = build_saved_course(
                course_id=new_course_id(),
                topic="Python Programming",
                outline=valid_outline(),
                lessons=[grounded_lesson],
                quizzes=[],
            )

            store.save(course)
            loaded_course = store.load(course.course_id)

            loaded_lesson = loaded_course.lessons[0]

            self.assertEqual(
                loaded_lesson.grounding,
                grounded_lesson.grounding,
            )
            self.assertEqual(
                loaded_lesson.grounding.sources,
                grounded_lesson.grounding.sources,
            )
            self.assertEqual(
                loaded_course.source_document.filename,
                document.filename,
            )
            self.assertEqual(
                loaded_course.source_document.fingerprint,
                document.fingerprint,
            )

    def test_load_corrupted_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CourseStore(directory=temp_dir)
            course_id = new_course_id()

            course_path = store.path_for(course_id)
            course_path.write_text(
                "{invalid json",
                encoding="utf-8",
            )

            with self.assertRaises(CorruptedCourseFileError):
                store.load(course_id)

    def test_load_invalid_course_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CourseStore(directory=temp_dir)
            course_id = new_course_id()

            course_path = store.path_for(course_id)

            invalid_data = {
                "schema_version": 1,
                "app": "Mini ClassBuild",
                "course_id": course_id,
                "topic": "",
            }

            course_path.write_text(
                json.dumps(invalid_data),
                encoding="utf-8",
            )

            with self.assertRaises(CorruptedCourseFileError):
                store.load(course_id)

    def test_load_unsupported_schema_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CourseStore(directory=temp_dir)
            course_id = new_course_id()

            course_path = store.path_for(course_id)

            invalid_data = {
                "schema_version": 999,
                "app": "Mini ClassBuild",
                "course_id": course_id,
            }

            course_path.write_text(
                json.dumps(invalid_data),
                encoding="utf-8",
            )

            with self.assertRaises(UnsupportedSchemaVersionError):
                store.load(course_id)

    def test_load_course_file_too_large(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CourseStore(directory=temp_dir, max_bytes=100)
            course_id = new_course_id()

            course_path = store.path_for(course_id)
            course_path.write_text(
                "x" * 101,
                encoding="utf-8",
            )

            with self.assertRaises(CourseFileTooLargeError):
                store.load(course_id)

    def test_reject_invalid_course_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CourseStore(directory=temp_dir)

            invalid_ids = [
                "../outside",
                "invalid-id",
                "",
                "a" * 31,
                "g" * 32,
            ]

            for course_id in invalid_ids:
                with self.subTest(course_id=course_id):
                    with self.assertRaises(InvalidCourseIdError):
                        store.path_for(course_id)

    def test_load_mismatched_course_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CourseStore(directory=temp_dir)

            filename_id = new_course_id()
            different_id = new_course_id()

            course = build_saved_course(
                course_id=different_id,
                topic="Python Programming",
                outline=valid_outline(),
                lessons=[valid_lesson()],
                quizzes=[valid_quiz()],
            )

            course_path = store.path_for(filename_id)
            course_path.write_text(
                course.model_dump_json(),
                encoding="utf-8",
            )

            with self.assertRaises(CorruptedCourseFileError):
                store.load(filename_id)

    def test_save_uses_atomic_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CourseStore(directory=temp_dir)

            course = build_saved_course(
                course_id=new_course_id(),
                topic="Python Programming",
                outline=valid_outline(),
                lessons=[valid_lesson()],
                quizzes=[valid_quiz()],
            )

            store.save(course)

            files = list(Path(temp_dir).iterdir())

            self.assertEqual(len(files), 1)
            self.assertEqual(
                files[0].name,
                f"course-{course.course_id}.json",
            )

    def test_list_courses_ignores_temporary_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CourseStore(directory=temp_dir)

            temporary_file = Path(temp_dir) / ".course-test.tmp"
            temporary_file.write_text(
                '{"some": "temporary data"}',
                encoding="utf-8",
            )

            listing = store.list_courses()

            self.assertEqual(listing.courses, ())
            self.assertEqual(listing.issues, ())
            self.assertTrue(temporary_file.exists())


class MarkdownExportTests(unittest.TestCase):

    def test_course_filename_is_safe(self):
        filename = course_filename("Introduction to Python")

        self.assertEqual(
            filename,
            "introduction-to-python.md",
        )

    def test_course_to_markdown_includes_topic(self):
        outline = validate_outline(valid_outline(2))
        markdown = course_to_markdown(
            outline,
            "Python",
            [],
            [],
        )

        self.assertIn("Python", markdown)

    def test_course_to_markdown_includes_topic_and_metadata(self):
        outline = validate_outline(valid_outline(2))
        markdown = course_to_markdown(outline, "Python", [], [])

        self.assertIn("# " + outline.title, markdown)
        self.assertIn("**Topic:** Python", markdown)
        self.assertIn(
            f"**Difficulty:** {outline.difficulty}",
            markdown,
        )

        if outline.description:
            self.assertIn(
                " ".join(outline.description.split()),
                markdown,
            )

        for objective in outline.learning_objectives:
            self.assertIn(
                " ".join(objective.split()),
                markdown,
            )

    def test_course_to_markdown_includes_course_outline(self):
        outline = validate_outline(valid_outline(2))
        markdown = course_to_markdown(outline, "Python", [], [])

        self.assertIn("## Course Outline", markdown)

        for lesson in outline.lessons:
            self.assertIn(
                f"### Lesson {lesson.lesson_number}: {lesson.title}",
                markdown,
            )

    def test_course_to_markdown_shows_lessons_not_generated(self):
        outline = validate_outline(valid_outline(2))
        markdown = course_to_markdown(outline, "Python", [], [])

        for lesson in outline.lessons:
            self.assertIn(
                f"## Lesson {lesson.lesson_number}: Not generated yet",
                markdown,
            )

        self.assertIn(
            "This lesson has not been generated yet.",
            markdown,
        )

    def test_course_to_markdown_includes_lesson_content(self):
        outline = validate_outline(valid_outline(2))
        lesson = validate_lesson(valid_lesson())

        markdown = course_to_markdown(
            outline,
            "Python",
            [lesson],
            [],
        )

        self.assertIn("# Lesson Content", markdown)

        for section in lesson.sections:
            if section.heading:
                self.assertIn(
                    " ".join(section.heading.split()),
                    markdown,
                )

            if section.explanation:
                self.assertIn(
                    " ".join(section.explanation.split()),
                    markdown,
                )

            if section.example:
                self.assertIn(
                    " ".join(section.example.split()),
                    markdown,
                )

        if lesson.summary:
            self.assertIn(
                " ".join(lesson.summary.split()),
                markdown,
            )

        for exercise in lesson.exercises:
            if exercise.question:
                self.assertIn(
                    " ".join(exercise.question.split()),
                    markdown,
                )

            if exercise.hint:
                self.assertIn(
                    "Hint: " + " ".join(exercise.hint.split()),
                    markdown,
                )

    def test_course_to_markdown_includes_grounded_sources(self):
        outline = validate_outline(valid_outline(2))
        document = make_document()
        results = make_results()
        draft = make_draft()

        grounded_lesson = draft_to_lesson(
            draft,
            results,
            document,
            "Python programming basics",
        )

        markdown = course_to_markdown(
            outline,
            "Python",
            [grounded_lesson],
            [],
        )

        self.assertIn("Sources:", markdown)

        grounding = grounded_lesson.grounding
        self.assertIsNotNone(grounding)
        self.assertTrue(grounding.sources)

        source = grounding.sources[0]

        self.assertIn(source.source_filename, markdown)

        if source.page_number is not None:
            self.assertIn(
                f"page {source.page_number}",
                markdown,
            )

    def test_course_to_markdown_separates_quiz_answers(self):
        outline = validate_outline(valid_outline(2))
        quiz = validate_quiz(valid_quiz())

        markdown = course_to_markdown(
            outline,
            "Python",
            [],
            [quiz],
        )

        self.assertIn("# Quizzes", markdown)
        self.assertIn("# Answer Key", markdown)

        quiz_section, answer_key = markdown.split(
            "# Answer Key",
            maxsplit=1,
        )

        for index, question in enumerate(quiz.questions, start=1):
            self.assertIn(
                f"**{index}. {question.question}**",
                quiz_section,
            )

            for option_index, option in enumerate(question.options):
                if option_index >= len("ABCD"):
                    break

                self.assertIn(
                    f"- {'ABCD'[option_index]}. {option}",
                    quiz_section,
                )

            correct_answer = question.correct_answer

            if isinstance(correct_answer, int) and 0 <= correct_answer < 4:
                answer_letter = "ABCD"[correct_answer]
            else:
                answer_letter = "Not available"

            answer_marker = f"{index}. **{answer_letter}**"

            self.assertNotIn(answer_marker, quiz_section)
            self.assertIn(answer_marker, answer_key)

    def test_course_to_markdown_omits_answer_key_without_quizzes(self):
        outline = validate_outline(valid_outline(2))
        markdown = course_to_markdown(
            outline,
            "Python",
            [],
            [],
        )

        self.assertIn("# Quizzes", markdown)
        self.assertNotIn("# Answer Key", markdown)

    def test_course_filename_handles_special_characters(self):
        filename = course_filename("../My Course: Python!")

        self.assertEqual(
            filename,
            "my-course-python.md",
        )


if __name__ == "__main__":
    unittest.main()