from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from classbuild.models.course import NonEmptyStr


QUESTION_COUNT = 5
OPTION_COUNT = 4


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: NonEmptyStr
    options: list[NonEmptyStr] = Field(
        min_length=OPTION_COUNT,
        max_length=OPTION_COUNT,
    )
    correct_answer: int = Field(
        strict=True,
        ge=0,
        le=3,
        description="The index of the correct answer (0-3)",
    )
    explanation: NonEmptyStr

    @field_validator("options")
    @classmethod
    def options_must_be_distinct(cls, options):
        normalized = [_normalize(option) for option in options]

        if len(normalized) != len(set(normalized)):
            raise ValueError("All options must be different.")

        return options


class Quiz(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_number: int = Field(ge=1)
    lesson_title: NonEmptyStr
    questions: list[Question] = Field(
        min_length=QUESTION_COUNT,
        max_length=QUESTION_COUNT,
    )

    @model_validator(mode="after")
    def questions_must_be_distinct(self):
        normalized = [
            _normalize(question.question)
            for question in self.questions
        ]

        if len(normalized) != len(set(normalized)):
            raise ValueError("Questions must not be repeated.")

        return self

    @model_validator(mode="after")
    def check_matches_selected_lesson(self, info: ValidationInfo):
        context = info.context or {}

        expected_lesson_number = context.get("expected_lesson_number")
        expected_title = context.get("expected_title")

        if (
            expected_lesson_number is not None
            and self.lesson_number != expected_lesson_number
        ):
            raise ValueError(
                f"Expected lesson number {expected_lesson_number}, "
                f"but received {self.lesson_number}."
            )

        if (
            expected_title is not None
            and _normalize(self.lesson_title) != _normalize(expected_title)
        ):
            raise ValueError(
                f"Expected lesson title '{expected_title}', "
                f"but received '{self.lesson_title}'."
            )

        return self


def validate_quiz(
    data,
    expected_lesson_number=None,
    expected_title=None,
):
    return Quiz.model_validate(
        data,
        context={
            "expected_lesson_number": expected_lesson_number,
            "expected_title": expected_title,
        },
    )