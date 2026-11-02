
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from app import (
    CONFIG_KEY,
    OUTLINE_KEY,
    LESSONS_KEY,
    COURSE_ID_KEY,
    QUIZZES_KEY,
    RESULTS_KEY,
    ATTEMPTS_KEY,
)


from classbuild.models.course import validate_outline
from classbuild.models.lesson import validate_lesson
from classbuild.models.quiz import validate_quiz

from tests.fixtures import (
    valid_outline,
    valid_lesson,
    valid_quiz,
)


 
# Fake Generators


class FakeCourseGenerator:

    calls = 0
    should_fail = False

    def generate_outline(self, config):
        type(self).calls += 1

        if type(self).should_fail:
            raise RuntimeError("Course generation failed")

        return validate_outline(
            valid_outline(
                lesson_count=config.lesson_count,
                difficulty=config.difficulty,
            ),
            expected_lesson_count=config.lesson_count,
            expected_difficulty=config.difficulty,
        )


class FakeLessonGenerator:

    calls = []

    def generate_lesson(self, outline, lesson_number):
        type(self).calls.append(lesson_number)

        lesson = outline.lessons[lesson_number - 1]

        return validate_lesson(
            valid_lesson(
                lesson_number=lesson_number,
                title=lesson.title,
            ),
            expected_lesson_number=lesson_number,
            expected_title=lesson.title,
        )


class FakeQuizGenerator:

    calls = []
    should_fail = False

    def generate_quiz(self, outline, lesson_number, content):
        type(self).calls.append(lesson_number)

        if type(self).should_fail:
            raise RuntimeError("Quiz generation failed")

        lesson = outline.lessons[lesson_number - 1]

        return validate_quiz(
            valid_quiz(
                lesson_number=lesson_number,
                lesson_title=lesson.title,
            ),
            expected_lesson_number=lesson_number,
            expected_title=lesson.title,
        )


# Test Helpers
def app_script():
    import app
    app.main()


def start():
    return AppTest.from_function(app_script).run()

def submit(app, topic="Python Programming"):
    app.text_input[0].set_value(topic)

    app.button[0].click()

    return app.run()


def lesson_button(app, lesson_number):
    button = app.button(
        key=f"generate_lesson_{lesson_number}"
    )
    button.click()

    return app.run()


def new_course(app, topic="New Python Course"):
    return submit(app, topic)


def prefix(app, lesson_number, attempt=0):
    course_id = app.session_state[COURSE_ID_KEY]

    return (
        f"quiz_{course_id}"
        f"_l{lesson_number}"
        f"_a{attempt}"
    )


def open_quiz(app, lesson_number):
    button = app.button(
        key=f"generate_quiz_{lesson_number}"
    )
    button.click()

    return app.run()


def quiz_radios(app):
    return [
        radio
        for radio in app.radio
        if radio.key and "_q" in radio.key
    ]


def answer(app, answers):
    radios = quiz_radios(app)

    for radio, selected in zip(radios, answers):
        if selected is not None:
            radio.set_value(selected)

    return app


def prepare_lesson_and_quiz(app, lesson_number=1):
    lesson_button(app, lesson_number)
    open_quiz(app, lesson_number)

    return app


 
# App Tests Course and Lesson Behaviour


class AppTests(unittest.TestCase):

    def setUp(self):
        FakeCourseGenerator.calls = 0
        FakeCourseGenerator.should_fail = False

        FakeLessonGenerator.calls = []

        FakeQuizGenerator.calls = []
        FakeQuizGenerator.should_fail = False

        self.course_patch = patch(
            "app.CourseGenerator",
            FakeCourseGenerator,
        )
        self.lesson_patch = patch(
            "app.LessonGenerator",
            FakeLessonGenerator,
        )
        self.quiz_patch = patch(
            "app.QuizGenerator",
            FakeQuizGenerator,
        )

        self.course_patch.start()
        self.lesson_patch.start()
        self.quiz_patch.start()

        self.addCleanup(self.course_patch.stop)
        self.addCleanup(self.lesson_patch.stop)
        self.addCleanup(self.quiz_patch.stop)

        self.app = start()

    def test_invalid_topic_does_not_call_groq(self):
        submit(self.app, "   ")

        self.assertEqual(FakeCourseGenerator.calls, 0)
        self.assertIsNone(
            self.app.session_state.get(OUTLINE_KEY)
        )
        self.assertTrue(self.app.error)

    def test_valid_submit_generates_once_and_survives_reruns(self):
        submit(self.app, "Python Programming")

        self.assertEqual(FakeCourseGenerator.calls, 1)
        self.assertIsNotNone(
            self.app.session_state[OUTLINE_KEY]
        )

        self.app.run()

        self.assertEqual(FakeCourseGenerator.calls, 1)
        self.assertIsNotNone(
            self.app.session_state[OUTLINE_KEY]
        )

    def test_failure_clears_stale_outline(self):
        submit(self.app, "First Course")

        self.assertIsNotNone(
            self.app.session_state[OUTLINE_KEY]
        )

        FakeCourseGenerator.should_fail = True

        submit(self.app, "Second Course")

        self.assertIsNone(
            self.app.session_state.get(OUTLINE_KEY)
        )

    def test_lessons_generated_individually_and_cached(self):
        submit(self.app)

        lesson_button(self.app, 1)
        self.assertEqual(FakeLessonGenerator.calls, [1])

        lesson_button(self.app, 2)
        self.assertEqual(FakeLessonGenerator.calls, [1, 2])

        self.assertIn(1, self.app.session_state[LESSONS_KEY])
        self.assertIn(2, self.app.session_state[LESSONS_KEY])

        self.assertEqual(FakeLessonGenerator.calls, [1, 2])

    def test_new_course_clears_lessons(self):
        submit(self.app)

        lesson_button(self.app, 1)

        self.assertIn(
            1,
            self.app.session_state[LESSONS_KEY],
        )

        new_course(self.app, "Another Course")

        self.assertEqual(
            self.app.session_state.get(LESSONS_KEY, {}),
            {},
        )

    def test_failed_lesson_keeps_existing_content(self):
        submit(self.app)
        original_generate_lesson = FakeLessonGenerator.generate_lesson
        lesson_button(self.app, 1)

        original = self.app.session_state[LESSONS_KEY][1]

        FakeLessonGenerator.generate_lesson = (
            lambda self, outline, number: (
                (_ for _ in ()).throw(
                    RuntimeError("Lesson generation failed")
                )
            )
        )

        lesson_button(self.app, 2)

        self.assertEqual(
            self.app.session_state[LESSONS_KEY][1],
            original,
        )
        FakeLessonGenerator.generate_lesson = original_generate_lesson

    def test_structured_generation_failure_shows_clear_error(self):
        with patch.object(
            FakeCourseGenerator,
            "generate_outline",
            side_effect=RuntimeError("Generation failed"),
        ):
            submit(self.app)

        self.assertTrue(self.app.error)
        self.assertIsNone(
            self.app.session_state.get(OUTLINE_KEY)
        )

# Quiz App Tests


class QuizAppTests(unittest.TestCase):

    def setUp(self):
        FakeCourseGenerator.calls = 0
        FakeCourseGenerator.should_fail = False

        FakeLessonGenerator.calls = []

        FakeQuizGenerator.calls = []
        FakeQuizGenerator.should_fail = False

        self.course_patch = patch(
            "app.CourseGenerator",
            FakeCourseGenerator,
        )
        self.lesson_patch = patch(
            "app.LessonGenerator",
            FakeLessonGenerator,
        )
        self.quiz_patch = patch(
            "app.QuizGenerator",
            FakeQuizGenerator,
        )

        self.course_patch.start()
        self.lesson_patch.start()
        self.quiz_patch.start()

        self.addCleanup(self.course_patch.stop)
        self.addCleanup(self.lesson_patch.stop)
        self.addCleanup(self.quiz_patch.stop)

        self.app = start()

        submit(self.app)

        lesson_button(self.app, 1)

    def test_generate_quiz_shows_unanswered_questions(self):
        open_quiz(self.app, 1)

        self.assertEqual(FakeQuizGenerator.calls, [1])
        self.assertEqual(len(quiz_radios(self.app)), 5)

        for radio in quiz_radios(self.app):
            self.assertIsNone(radio.value)

    def test_submit_grades_locally_and_shows_feedback(self):
        open_quiz(self.app, 1)

        answers = [0, 0, 0, 3, 1]

        answer(self.app, answers)
       
        next(
            button
            for button in self.app.form_submit_button
            if button.label == "Submit Answers"
        ).click()
        self.app.run()

        result = self.app.session_state[RESULTS_KEY][1]

        self.assertEqual(result.percentage, 60)
        self.assertEqual(FakeQuizGenerator.calls, [1])

    def test_incomplete_submission_is_rejected(self):
        open_quiz(self.app, 1)

        answer(
            self.app,
            [0, None, 2, None, 1],
        )

        next(
            button
            for button in self.app.form_submit_button
            if button.label == "Submit Answers"
        ).click()
        self.app.run()

        self.assertNotIn(
            1,
            self.app.session_state.get(RESULTS_KEY, {}),
        )

        self.assertTrue(self.app.warning)

    def test_try_again_keeps_questions_and_clears_answers(self):
        open_quiz(self.app, 1)
        print(
            "LESSON NUMBERS:",
            [
                lesson.lesson_number
                for lesson in self.app.session_state[OUTLINE_KEY].lessons
            ],
        )

        quiz_before = self.app.session_state[QUIZZES_KEY][1]

        answer(self.app, [0, 1, 2, 3, 1])

        next(
            button
            for button in self.app.form_submit_button
            if button.label == "Submit Answers"
        ).click()
        self.app.run()

        self.assertIn(
            1,
            self.app.session_state[RESULTS_KEY],
        )

        try_again = [
            button
            for button in self.app.button
            if button.label == "Try Again"
        ]

        self.assertTrue(try_again)

        try_again[0].click()
        self.app.run()

        self.assertEqual(
            self.app.session_state[QUIZZES_KEY][1],
            quiz_before,
        )

        self.assertNotIn(
            1,
            self.app.session_state.get(RESULTS_KEY, {}),
        )

        self.assertEqual(
            self.app.session_state[ATTEMPTS_KEY][1],
            1,
        )

        self.assertEqual(FakeQuizGenerator.calls, [1])

        for radio in quiz_radios(self.app):
            self.assertIsNone(radio.value)

    def test_quizzes_are_per_lesson(self):
        open_quiz(self.app, 1)

        lesson_button(self.app, 2)
        open_quiz(self.app, 2)

        self.assertIn(
            1,
            self.app.session_state[QUIZZES_KEY],
        )

        self.assertIn(
            2,
            self.app.session_state[QUIZZES_KEY],
        )

        self.assertEqual(
            FakeQuizGenerator.calls,
            [1, 2],
        )

    def test_new_course_clears_quiz_state(self):
        open_quiz(self.app, 1)

        self.assertIn(
            1,
            self.app.session_state[QUIZZES_KEY],
        )

        new_course(self.app, "New Course")

        self.assertEqual(
            self.app.session_state.get(QUIZZES_KEY, {}),
            {},
        )

        self.assertEqual(
            self.app.session_state.get(RESULTS_KEY, {}),
            {},
        )

        self.assertEqual(
            self.app.session_state.get(ATTEMPTS_KEY, {}),
            {},
        )

    def test_quiz_generation_failure_keeps_lesson(self):
        FakeQuizGenerator.should_fail = True

        open_quiz(self.app, 1)

        self.assertIn(
            1,
            self.app.session_state[LESSONS_KEY],
        )

        self.assertNotIn(
            1,
            self.app.session_state.get(QUIZZES_KEY, {}),
        )

        self.assertTrue(self.app.error)


if __name__ == "__main__":
    unittest.main()
