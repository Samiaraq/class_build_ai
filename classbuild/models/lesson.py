from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from classbuild.models.course import NonEmptyStr


class LessonSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: NonEmptyStr = Field(description="The section heading")
    explanation: NonEmptyStr = Field(description="A clear explanation of the topic")
    example: NonEmptyStr = Field(description="A practical example")


class Exercise(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: NonEmptyStr = Field(description="The exercise question")
    hint: NonEmptyStr = Field(description="A hint to help solve the exercise")


class LessonContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_number: int = Field(ge=1)
    title: NonEmptyStr
    introduction: NonEmptyStr = Field(description="An introduction to the lesson")
    sections: list[LessonSection] = Field(
        min_length=2,
        max_length=4,
        description="The main sections of the lesson",
    )
    summary: NonEmptyStr = Field(description="A summary of the lesson")
    exercises: list[Exercise] = Field(
        min_length=2,
        max_length=2,
        description="Two exercises for students",
    )

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
            and _normalize(self.title) != _normalize(expected_title)
        ):
            raise ValueError(
                f"Expected lesson title '{expected_title}', "
                f"but received '{self.title}'."
            )

        return self


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def validate_lesson(
    data,
    expected_lesson_number=None,
    expected_title=None,
):
    return LessonContent.model_validate(
        data,
        context={
            "expected_lesson_number": expected_lesson_number,
            "expected_title": expected_title,
        },
    )