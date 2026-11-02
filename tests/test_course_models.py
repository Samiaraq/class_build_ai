
import unittest
from pydantic import ValidationError

from classbuild.models.course import validate_outline
from tests.fixtures import valid_outline, copy_of


class ValidOutlineTests(unittest.TestCase):

    def test_valid_outline_passes(self):
        data = valid_outline(lesson_count=3)

        outline = validate_outline(
            data,
            expected_lesson_count=3,
            expected_difficulty="Beginner",
        )

        self.assertEqual(
            [lesson.lesson_number for lesson in outline.lessons],
            [1, 2, 3],
        )

    def test_whitespace_is_stripped(self):
        data = valid_outline()
        data["title"] = " Python Basics "

        outline = validate_outline(data)

        self.assertEqual(outline.title, "Python Basics")


class RejectedOutlineTests(unittest.TestCase):

    def test_missing_course_field(self):
        fields = [
            "title",
            "description",
            "difficulty",
            "learning_objectives",
            "lessons",
        ]

        for field in fields:
            with self.subTest(field=field):
                data = copy_of(valid_outline())
                del data[field]

                with self.assertRaises(ValidationError):
                    validate_outline(data)

    def test_missing_lesson_field(self):
        fields = [
            "lesson_number",
            "title",
            "description",
            "learning_objectives",
        ]

        for field in fields:
            with self.subTest(field=field):
                data = copy_of(valid_outline())
                del data["lessons"][0][field]

                with self.assertRaises(ValidationError):
                    validate_outline(data)

    def test_empty_strings(self):
        data = copy_of(valid_outline())
        data["title"] = "   "

        with self.assertRaises(ValidationError):
            validate_outline(data)

        data = copy_of(valid_outline())
        data["lessons"][0]["title"] = ""

        with self.assertRaises(ValidationError):
            validate_outline(data)

    def test_invalid_difficulty(self):
        invalid_values = ["Expert", "beginner", "", 123]

        for value in invalid_values:
            with self.subTest(difficulty=value):
                data = copy_of(valid_outline())
                data["difficulty"] = value

                with self.assertRaises(ValidationError):
                    validate_outline(data)

    def test_difficulty_must_match_request(self):
        data = valid_outline(difficulty="Advanced")

        with self.assertRaises(ValidationError):
            validate_outline(
                data,
                expected_difficulty="Beginner",
            )

    def test_wrong_lesson_count(self):
        for count in [2, 4]:
            with self.subTest(count=count):
                data = valid_outline(lesson_count=count)

                with self.assertRaises(ValidationError):
                    validate_outline(
                        data,
                        expected_lesson_count=3,
                    )

    def test_no_lessons(self):
        data = copy_of(valid_outline())
        data["lessons"] = []

        with self.assertRaises(ValidationError):
            validate_outline(data)

    def test_nonsequential_lesson_numbers(self):
        invalid_sequences = [
            [1, 3, 4],
            [0, 1, 2],
            [2, 1, 3],
            [1, 1, 2],
        ]

        for numbers in invalid_sequences:
            with self.subTest(numbers=numbers):
                data = copy_of(valid_outline())

                for lesson, number in zip(data["lessons"], numbers):
                    lesson["lesson_number"] = number

                with self.assertRaises(ValidationError):
                    validate_outline(data)

    def test_objective_counts(self):
        invalid_course_counts = [
            [],
            ["One", "Two"],
            ["One", "Two", "Three", "Four", "Five", "Six"],
        ]

        for objectives in invalid_course_counts:
            with self.subTest(objectives=objectives):
                data = copy_of(valid_outline())
                data["learning_objectives"] = objectives

                with self.assertRaises(ValidationError):
                    validate_outline(data)

        invalid_lesson_counts = [
            [],
            ["One"],
            ["One", "Two", "Three", "Four"],
        ]

        for objectives in invalid_lesson_counts:
            with self.subTest(objectives=objectives):
                data = copy_of(valid_outline())
                data["lessons"][0]["learning_objectives"] = objectives

                with self.assertRaises(ValidationError):
                    validate_outline(data)

    def test_wrong_types(self):
        data = copy_of(valid_outline())
        data["lessons"][0]["lesson_number"] = "one"

        with self.assertRaises(ValidationError):
            validate_outline(data)

        data = copy_of(valid_outline())
        data["lessons"] = "not a list"

        with self.assertRaises(ValidationError):
            validate_outline(data)

    def test_extra_fields_rejected(self):
        data = copy_of(valid_outline())
        data["unexpected_field"] = "not allowed"

        with self.assertRaises(ValidationError):
            validate_outline(data)

    def test_original_data_not_modified(self):
        data = valid_outline()
        original = copy_of(data)

        validate_outline(data)

        self.assertEqual(data, original)


if __name__ == "__main__":
    unittest.main()
