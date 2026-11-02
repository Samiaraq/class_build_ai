
from dataclasses import dataclass

from classbuild.models.quiz import Quiz


class QuizSubmissionError(ValueError):
    """Raised when quiz answers are incomplete or invalid."""

    def __init__(self, message: str, unanswered: list[int] | None = None):
        self.unanswered = unanswered or []
        super().__init__(message)


@dataclass(frozen=True)
class QuestionResult:
    number: int
    question: str
    options: list[str]
    selected_answer: int
    correct_answer: int
    is_correct: bool
    explanation: str

    @property
    def selected_text(self) -> str:
        return self.options[self.selected_answer]

    @property
    def correct_text(self) -> str:
        return self.options[self.correct_answer]


@dataclass(frozen=True)
class QuizResult:
    lesson_number: int
    correct_count: int
    total_questions: int
    percentage: float
    question_results: list[QuestionResult]


def _is_valid_index(value: object) -> bool:
    return type(value) is int and 0 <= value <= 3


def grade_quiz(quiz: Quiz, answers: list[int]) -> QuizResult:
    if not isinstance(answers, list):
        raise QuizSubmissionError("Answers must be provided as a list.")

    if len(answers) != len(quiz.questions):
        raise QuizSubmissionError(
            f"Expected {len(quiz.questions)} answers, "
            f"but received {len(answers)}."
        )

    unanswered = [
        index 
        for index, answer in enumerate(answers)
        if answer is None
    ]

    if unanswered:
        raise QuizSubmissionError(
            f"Please answer all questions before submitting. "
            f"Unanswered questions: {unanswered}.",
            unanswered=unanswered,
        )

    invalid_answers = [
        index + 1
        for index, answer in enumerate(answers)
        if not _is_valid_index(answer)
    ]

    if invalid_answers:
        raise QuizSubmissionError(
            f"Invalid answer indices for questions: {invalid_answers}."
        )

    question_results = []
    correct_count = 0

    for index, question in enumerate(quiz.questions):
        selected_answer = answers[index]
        is_correct = selected_answer == question.correct_answer

        if is_correct:
            correct_count += 1

        question_results.append(
            QuestionResult(
                number=index + 1,
                question=question.question,
                options=question.options,
                selected_answer=selected_answer,
                correct_answer=question.correct_answer,
                is_correct=is_correct,
                explanation=question.explanation,
            )
        )

    total_questions = len(quiz.questions)
    percentage = (correct_count / total_questions) * 100

    return QuizResult(
        lesson_number=quiz.lesson_number,
        correct_count=correct_count,
        total_questions=total_questions,
        percentage=percentage,
        question_results=question_results,
    )
