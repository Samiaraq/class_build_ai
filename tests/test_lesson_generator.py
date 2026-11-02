
import unittest

from pydantic import ValidationError

from classbuild.models.lesson import validate_lesson
from classbuild.services.lesson_generator import (
    LessonGenerator,
    LessonSelectionError,
    LessonValidationError,
    build_lesson_prompt,
    find_lesson,
    lesson_json_schema,
)
from classbuild.llm.exceptions import (
    AuthenticationError,
    RateLimitError,
)
from classbuild.services.structured_output import (
    StructuredGenerationError,
)
from tests.fixtures import valid_outline, valid_lesson, copy_of
from classbuild.models.course import validate_outline

def make_outline(lessons=3, difficulty="Beginner"):
    return validate_outline(
        valid_outline(
            lesson_count=lessons,
            difficulty=difficulty,
        )
    )

class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_json(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)

        if isinstance(response, Exception):
            raise response

        return response


class LessonModelTests(unittest.TestCase):

    def test_valid_lesson_passes(self):
        for section_count in [2, 3, 4]:
            with self.subTest(section_count=section_count):
                lesson = validate_lesson(
                    valid_lesson(sections=section_count),
                    expected_lesson_number=1,
                    expected_title="Lesson 1 title",
                )

                self.assertEqual(len(lesson.sections), section_count)

    def test_missing_fields_rejected(self):
        data = valid_lesson()
        del data["introduction"]

        with self.assertRaises(ValidationError):
            validate_lesson(data)

        data = valid_lesson()
        del data["sections"][0]["example"]

        with self.assertRaises(ValidationError):
            validate_lesson(data)

        data = valid_lesson()
        del data["exercises"][0]["hint"]

        with self.assertRaises(ValidationError):
            validate_lesson(data)

    def test_empty_text_rejected(self):
        data = valid_lesson()
        data["sections"][0]["example"] = "   "

        with self.assertRaises(ValidationError):
            validate_lesson(data)

    def test_section_and_exercise_counts(self):
        for count in [1, 5]:
            with self.subTest(section_count=count):
                with self.assertRaises(ValidationError):
                    validate_lesson(valid_lesson(sections=count))

        for count in [1, 3]:
            with self.subTest(exercise_count=count):
                data = valid_lesson()
                data["exercises"] = data["exercises"][:count]

                if count == 3:
                    data["exercises"].append({
                        "question": "Extra question",
                        "hint": "Extra hint",
                    })

                with self.assertRaises(ValidationError):
                    validate_lesson(data)

    def test_wrong_lesson_number_rejected(self):
        with self.assertRaises(ValidationError):
            validate_lesson(
                valid_lesson(lesson_number=3),
                expected_lesson_number=2,
            )

    def test_wrong_title_rejected(self):
        with self.assertRaises(ValidationError):
            validate_lesson(
                valid_lesson(title="Another lesson"),
                expected_title="Lesson 1 title",
            )

    def test_title_match_ignores_case_and_spacing(self):
        data = valid_lesson(title="  LESSON 1 TITLE  ")

        lesson = validate_lesson(
            data,
            expected_title="Lesson 1 title",
        )

        self.assertEqual(lesson.title.strip(), "LESSON 1 TITLE")

    def test_extra_fields_rejected(self):
        data = valid_lesson()
        data["unexpected_field"] = "not allowed"

        with self.assertRaises(ValidationError):
            validate_lesson(data)


class LessonGeneratorTests(unittest.TestCase):

    def setUp(self):
        self.outline = make_outline()
        self.lesson_data = valid_lesson(
            lesson_number=2,
            title="Lesson 2 title",
        )
        self.client = FakeClient([self.lesson_data])
        self.generator = LessonGenerator(client=self.client)

    def test_generates_selected_lesson(self):
        lesson = self.generator.generate_lesson(
            self.outline,
            lesson_number=2,
        )

        self.assertEqual(lesson.lesson_number, 2)
        self.assertEqual(lesson.title, "Lesson 2 title")
        self.assertEqual(len(self.client.calls), 1)

    def test_prompt_contains_course_context(self):
        lesson = find_lesson(self.outline, 2)
        prompt = build_lesson_prompt(
            self.outline,
            lesson,
        )

        self.assertIn(self.outline.title, prompt)
        self.assertIn(lesson.title, prompt)

        for objective in self.outline.learning_objectives:
            self.assertIn(objective, prompt)

        self.assertIn("Lesson 1 title", prompt)
        self.assertIn("Lesson 3 title", prompt)

    def test_request_settings(self):
        self.generator.generate_lesson(
            self.outline,
            lesson_number=2,
        )

        call = self.client.calls[0]

        self.assertEqual(call["max_completion_tokens"], 4000)
        self.assertEqual(call["reasoning_effort"], "low")
        self.assertEqual(call["schema_name"], "lesson_content")

    def test_schema_pins_selected_lesson(self):
        lesson = find_lesson(self.outline, 2)
        schema = lesson_json_schema(lesson)

        self.assertEqual(
            schema["properties"]["lesson_number"]["enum"],
            [2],
        )
        self.assertEqual(
            schema["properties"]["title"]["enum"],
            ["Lesson 2 title"],
        )

    def test_missing_outline(self):
        with self.assertRaises(LessonSelectionError):
            find_lesson(None, 1)

    def test_invalid_lesson_selection(self):
        for number in [0, 4, 99]:
            with self.subTest(lesson_number=number):
                with self.assertRaises(LessonSelectionError):
                    find_lesson(self.outline, number)

    def test_wrong_number_or_title_from_model_rejected(self):
        invalid_responses = [
            valid_lesson(
                lesson_number=3,
                title="Lesson 3 title",
            ),
            valid_lesson(
                lesson_number=2,
                title="Different title",
            ),
        ]

        for response in invalid_responses:
            with self.subTest(response=response):
                client = FakeClient([response])
                generator = LessonGenerator(client=client)

                with self.assertRaises(LessonValidationError):
                    generator.generate_lesson(
                        self.outline,
                        lesson_number=2,
                    )

                self.assertEqual(len(client.calls), 1)

    def test_invalid_content_not_retried(self):
        invalid_data = valid_lesson(sections=1)
        client = FakeClient([invalid_data])
        generator = LessonGenerator(client=client)

        with self.assertRaises(LessonValidationError):
            generator.generate_lesson(
                self.outline,
                lesson_number=2,
            )

        self.assertEqual(len(client.calls), 1)

    def test_structured_failure_retried_once_then_succeeds(self):
        from classbuild.llm.exceptions import InvalidJSONError

        client = FakeClient([
            InvalidJSONError("Invalid JSON"),
            self.lesson_data,
        ])
        generator = LessonGenerator(client=client)

        with self.assertLogs(
            "classbuild.services.structured_output",
            level="WARNING",
        ):
            lesson = generator.generate_lesson(
                self.outline,
                lesson_number=2,
            )

        self.assertEqual(lesson.lesson_number, 2)
        self.assertEqual(len(client.calls), 2)

    def test_structured_failure_twice(self):
        from classbuild.llm.exceptions import InvalidJSONError

        client = FakeClient([
            InvalidJSONError("First failure"),
            InvalidJSONError("Second failure"),
        ])
        generator = LessonGenerator(client=client)

        with self.assertLogs(
            "classbuild.services.structured_output",
            level="WARNING",
        ):
            with self.assertRaises(StructuredGenerationError):
                generator.generate_lesson(
                    self.outline,
                    lesson_number=2,
                )

        self.assertEqual(len(client.calls), 2)

    def test_auth_and_rate_limit_not_retried(self):
        errors = [
            AuthenticationError("Unauthorized"),
            RateLimitError("Rate limit reached"),
        ]

        for error in errors:
            with self.subTest(error=type(error).__name__):
                client = FakeClient([error])
                generator = LessonGenerator(client=client)

                with self.assertRaises(type(error)):
                    generator.generate_lesson(
                        self.outline,
                        lesson_number=2,
                    )

                self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
