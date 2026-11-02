import unittest
from pydantic import ValidationError

from classbuild.models.course import validate_outline
from classbuild.models.lesson import validate_lesson
from classbuild.models.quiz import validate_quiz
from classbuild.services.quiz_grader import (
    QuizSubmissionError,
    grade_quiz,
)
from classbuild.services.quiz_generator import (
    QuizGenerator,
    QuizPrerequisiteError,
    QuizValidationError,
    build_quiz_prompt,
    quiz_json_schema,
    SYSTEM_PROMPT,
)
from classbuild.llm.exceptions import (
    AuthenticationError,
    InvalidJSONError,
    RateLimitError,
)

from tests.fixtures import (
    QUIZ_CORRECT_ANSWERS,
    valid_outline,
    valid_lesson,
    valid_quiz,
    copy_of,
)


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def make_outline(lessons=3, difficulty="Beginner"):
    data = valid_outline(
        lesson_count=lessons,
        difficulty=difficulty,
    )
    return validate_outline(
        data,
        expected_lesson_count=lessons,
        expected_difficulty=difficulty,
    )


def lesson2_content():
    outline = make_outline()
    selected_lesson = outline.lessons[1]

    content_data = valid_lesson(
        lesson_number=2,
        title=selected_lesson.title,
    )

    return validate_lesson(
        content_data,
        expected_lesson_number=2,
        expected_title=selected_lesson.title,
    )


def make_quiz(lesson_number=1, lesson_title="Lesson 1 title"):
    return validate_quiz(
        valid_quiz(
            lesson_number=lesson_number,
            lesson_title=lesson_title,
        ),
        expected_lesson_number=lesson_number,
        expected_title=lesson_title,
    )


class FakeClient:
    """A fake Groq client used to test without API calls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_json(self, **kwargs):
        self.calls.append(kwargs)

        response = self.responses.pop(0)

        if isinstance(response, Exception):
            raise response

        return response


# --------------------------------------------------
# Quiz Model Tests
# --------------------------------------------------

class QuizModelTests(unittest.TestCase):

    def setUp(self):
        self.data = valid_quiz()
        self.quiz = validate_quiz(
            self.data,
            expected_lesson_number=1,
            expected_title="Lesson 1 title",
        )

    def test_valid_quiz_passes(self):
        self.assertEqual(len(self.quiz.questions), 5)

        for question in self.quiz.questions:
            self.assertEqual(len(question.options), 4)

    def test_rejects_four_questions(self):
        data = copy_of(self.data)
        data["questions"] = data["questions"][:4]

        with self.assertRaises(ValidationError):
            validate_quiz(data)

    def test_rejects_six_questions(self):
        data = copy_of(self.data)
        data["questions"].append(
            copy_of(data["questions"][0])
        )

        with self.assertRaises(ValidationError):
            validate_quiz(data)

    def test_rejects_three_options(self):
        data = copy_of(self.data)
        data["questions"][0]["options"] = ["A", "B", "C"]

        with self.assertRaises(ValidationError):
            validate_quiz(data)

    def test_rejects_five_options(self):
        data = copy_of(self.data)
        data["questions"][0]["options"].append("Extra option")

        with self.assertRaises(ValidationError):
            validate_quiz(data)

    def test_rejects_invalid_correct_answer_indices(self):
        invalid_indices = [-1, 4, 10, "2", 1.5, True, None]

        for index in invalid_indices:
            with self.subTest(index=index):
                data = copy_of(self.data)
                data["questions"][0]["correct_answer"] = index

                with self.assertRaises(ValidationError):
                    validate_quiz(data)

    def test_rejects_duplicate_options(self):
        data = copy_of(self.data)
        data["questions"][0]["options"] = [
            "Python",
            "python",
            "Java",
            "C++",
        ]

        with self.assertRaises(ValidationError):
            validate_quiz(data)

    def test_rejects_empty_option(self):
        data = copy_of(self.data)
        data["questions"][0]["options"][0] = "   "

        with self.assertRaises(ValidationError):
            validate_quiz(data)

    def test_rejects_empty_explanation(self):
        data = copy_of(self.data)
        data["questions"][0]["explanation"] = "   "

        with self.assertRaises(ValidationError):
            validate_quiz(data)

    def test_rejects_missing_fields(self):
        data = copy_of(self.data)
        del data["questions"][0]["explanation"]

        with self.assertRaises(ValidationError):
            validate_quiz(data)

    def test_rejects_duplicate_questions(self):
        data = copy_of(self.data)
        data["questions"][1]["question"] = (
            data["questions"][0]["question"]
        )

        with self.assertRaises(ValidationError):
            validate_quiz(data)

    def test_rejects_wrong_lesson_number(self):
        with self.assertRaises(ValidationError):
            validate_quiz(
                copy_of(self.data),
                expected_lesson_number=2,
                expected_title="Lesson 1 title",
            )

    def test_rejects_wrong_lesson_title(self):
        with self.assertRaises(ValidationError):
            validate_quiz(
                copy_of(self.data),
                expected_lesson_number=1,
                expected_title="Different title",
            )


# --------------------------------------------------
# Grading Tests
# --------------------------------------------------

class GradingTests(unittest.TestCase):

    def setUp(self):
        self.quiz = make_quiz()

    def test_all_correct_answers_give_100_percent(self):
        result = grade_quiz(
            self.quiz,
            QUIZ_CORRECT_ANSWERS,
        )

        self.assertEqual(result.percentage, 100)

    def test_three_correct_answers_give_60_percent(self):
        answers = [0, 0, 0, 3, 1]

        result = grade_quiz(self.quiz, answers)

        self.assertEqual(result.percentage, 60)

    def test_zero_correct_answers_give_zero_percent(self):
        answers = [1, 0, 3, 0, 0]

        result = grade_quiz(self.quiz, answers)

        self.assertEqual(result.percentage, 0)

    def test_question_feedback_is_returned(self):
        result = grade_quiz(
            self.quiz,
            QUIZ_CORRECT_ANSWERS,
        )

        self.assertEqual(len(result.question_results), 5)
        self.assertTrue(result.question_results[0].is_correct)
        self.assertTrue(result.question_results[0].selected_text)
        self.assertTrue(result.question_results[0].correct_text)

    def test_incomplete_answers_are_rejected(self):
        answers = [0, 1, None, 3, None]

        with self.assertRaises(QuizSubmissionError) as context:
            grade_quiz(self.quiz, answers)

        message = str(context.exception)

        self.assertIn("2", message)
        self.assertIn("4", message)

    def test_invalid_answer_indices_are_rejected(self):
        invalid_indices = [-1, 4, "1", True, 1.0]

        for index in invalid_indices:
            with self.subTest(index=index):
                answers = list(QUIZ_CORRECT_ANSWERS)
                answers[0] = index

                with self.assertRaises(QuizSubmissionError):
                    grade_quiz(self.quiz, answers)


# --------------------------------------------------
# Quiz Generator Tests
# --------------------------------------------------

class QuizGeneratorTests(unittest.TestCase):

    def setUp(self):
        self.outline = make_outline()
        self.lesson = self.outline.lessons[1]
        self.content = lesson2_content()
        self.quiz_data = valid_quiz(
            lesson_number=2,
            lesson_title=self.lesson.title,
        )

    def test_generated_quiz_uses_lesson_content(self):
        fake_client = FakeClient([self.quiz_data])
        generator = QuizGenerator(client=fake_client)

        quiz = generator.generate_quiz(
            self.outline,
            2,
            self.content,
        )

        self.assertEqual(quiz.lesson_number, 2)
        self.assertEqual(quiz.lesson_title, self.lesson.title)
        self.assertEqual(len(quiz.questions), 5)
        self.assertEqual(len(fake_client.calls), 1)

    def test_prompt_includes_lesson_content(self):
        prompt = build_quiz_prompt(
            self.outline,
            self.lesson,
            self.content,
        )

        self.assertIn(self.content.introduction, prompt)
        self.assertIn(self.content.summary, prompt)

        for section in self.content.sections:
            self.assertIn(section.heading, prompt)
            self.assertIn(section.explanation, prompt)

    def test_system_prompt_contains_quiz_rules(self):
        self.assertIn("5", SYSTEM_PROMPT)
        self.assertIn("4", SYSTEM_PROMPT)

    def test_schema_pins_lesson_information(self):
        schema = quiz_json_schema(self.lesson)

        self.assertIn("properties", schema)
        self.assertIn("lesson_number", schema["properties"])
        self.assertIn("lesson_title", schema["properties"])

    def test_schema_limits_correct_answer_indices(self):
        schema = quiz_json_schema(self.lesson)

        question_schema = schema["$defs"]["Question"]
        answer_schema = question_schema["properties"]["correct_answer"]

        self.assertEqual(answer_schema["enum"], [0, 1, 2, 3])

    def test_missing_outline_is_rejected_before_api_call(self):
        fake_client = FakeClient([])
        generator = QuizGenerator(client=fake_client)

        with self.assertRaises(QuizPrerequisiteError):
            generator.generate_quiz(
                None,
                2,
                self.content,
            )

        self.assertEqual(len(fake_client.calls), 0)

    def test_invalid_lesson_selection_is_rejected_before_api_call(self):
        fake_client = FakeClient([])
        generator = QuizGenerator(client=fake_client)

        for lesson_number in [0, 4, 99]:
            with self.subTest(lesson_number=lesson_number):
                with self.assertRaises(QuizPrerequisiteError):
                    generator.generate_quiz(
                        self.outline,
                        lesson_number,
                        self.content,
                    )

        self.assertEqual(len(fake_client.calls), 0)

    def test_missing_lesson_content_is_rejected_before_api_call(self):
        fake_client = FakeClient([])
        generator = QuizGenerator(client=fake_client)

        with self.assertRaises(QuizPrerequisiteError):
            generator.generate_quiz(
                self.outline,
                2,
                None,
            )

        self.assertEqual(len(fake_client.calls), 0)

    def test_wrong_lesson_content_is_rejected_before_api_call(self):
        wrong_content = validate_lesson(
            valid_lesson(
                lesson_number=1,
                title="Lesson 1 title",
            ),
            expected_lesson_number=1,
            expected_title="Lesson 1 title",
        )

        fake_client = FakeClient([])
        generator = QuizGenerator(client=fake_client)

        with self.assertRaises(QuizPrerequisiteError):
            generator.generate_quiz(
                self.outline,
                2,
                wrong_content,
            )

        self.assertEqual(len(fake_client.calls), 0)

    def test_invalid_quiz_from_model_is_rejected(self):
        invalid_data = copy_of(self.quiz_data)
        invalid_data["questions"] = invalid_data["questions"][:4]

        fake_client = FakeClient([invalid_data])
        generator = QuizGenerator(client=fake_client)

        with self.assertRaises(QuizValidationError):
            generator.generate_quiz(
                self.outline,
                2,
                self.content,
            )

    def test_structured_failure_retries_once(self):
        fake_client = FakeClient([
            InvalidJSONError("Invalid JSON"),
            self.quiz_data,
        ])
        generator = QuizGenerator(client=fake_client)

        quiz = generator.generate_quiz(
            self.outline,
            2,
            self.content,
        )

        self.assertEqual(quiz.lesson_number, 2)
        self.assertEqual(len(fake_client.calls), 2)

    def test_authentication_error_is_not_retried(self):
        fake_client = FakeClient([
            AuthenticationError("Invalid API key"),
        ])
        generator = QuizGenerator(client=fake_client)

        with self.assertRaises(AuthenticationError):
            generator.generate_quiz(
                self.outline,
                2,
                self.content,
            )

        self.assertEqual(len(fake_client.calls), 1)

    def test_rate_limit_error_is_not_retried(self):
        fake_client = FakeClient([
            RateLimitError("Rate limit exceeded"),
        ])
        generator = QuizGenerator(client=fake_client)

        with self.assertRaises(RateLimitError):
            generator.generate_quiz(
                self.outline,
                2,
                self.content,
            )

        self.assertEqual(len(fake_client.calls), 1)


if __name__ == "__main__":
    unittest.main()