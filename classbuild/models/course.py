from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    model_validator,
)


Difficulty = Literal["Beginner", "Intermediate", "Advanced"]

NonEmptyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class LessonOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_number: int = Field(ge=1)
    title: NonEmptyStr
    description: NonEmptyStr
    learning_objectives: list[NonEmptyStr] = Field(
        min_length=2,
        max_length=3,
    )


class CourseOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: NonEmptyStr
    description: NonEmptyStr
    difficulty: Difficulty
    learning_objectives: list[NonEmptyStr] = Field(
        min_length=3,
        max_length=5,
    )
    lessons: list[LessonOutline] = Field(min_length=1)

    @model_validator(mode="after")
    def check_lesson_numbers(self):
        expected_numbers = list(range(1, len(self.lessons) + 1))
        actual_numbers = [
            lesson.lesson_number for lesson in self.lessons
        ]

        if actual_numbers != expected_numbers:
            raise ValueError(
                "Lesson numbers must be sequential, starting from 1."
            )

        return self

    @model_validator(mode="after")
    def check_matches_request(self, info: ValidationInfo):
        context = info.context or {}

        expected_lesson_count = context.get("expected_lesson_count")
        expected_difficulty = context.get("expected_difficulty")

        if (
            expected_lesson_count is not None
            and len(self.lessons) != expected_lesson_count
        ):
            raise ValueError(
                f"Expected {expected_lesson_count} lessons, "
                f"but received {len(self.lessons)}."
            )

        if (
            expected_difficulty is not None
            and self.difficulty != expected_difficulty
        ):
            raise ValueError(
                f"Expected difficulty {expected_difficulty}, "
                f"but received {self.difficulty}."
            )

        return self


def validate_outline(
    data,
    expected_lesson_count=None,
    expected_difficulty=None,
):
    return CourseOutline.model_validate(
        data,
        context={
            "expected_lesson_count": expected_lesson_count,
            "expected_difficulty": expected_difficulty,
        },
    )