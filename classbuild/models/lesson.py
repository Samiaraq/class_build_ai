
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from classbuild.models.course import NonEmptyStr


class LessonSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: NonEmptyStr = Field(description="The section heading")
    explanation: NonEmptyStr = Field(description="A clear explanation of the topic")
    example: NonEmptyStr = Field(description="A practical example")
    source_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def no_duplicate_ids(self):
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("Duplicate source IDs found.")

        return self


class Exercise(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: NonEmptyStr = Field(description="The exercise question")
    hint: NonEmptyStr = Field(description="A hint to help solve the exercise")


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr
    source_filename: NonEmptyStr
    page_number: int = Field(ge=1)
    chunk_index: int = Field(ge=1)
    similarity: float
    text: str = Field(min_length=1)

class LessonGrounding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_fingerprint: NonEmptyStr
    source_filename: NonEmptyStr
    retrieval_query: NonEmptyStr
    sources: list[SourceReference] = Field(min_length=1)


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
    grounding: LessonGrounding | None = None

    @property
    def is_grounded(self) -> bool:
        return self.grounding is not None

    @property
    def cited_pages(self) -> list[int]:
        if self.grounding is None:
            return []

        return sorted({
            source.page_number
            for source in self.grounding.sources
        })

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

    @model_validator(mode="after")
    def check_citations(self, info: ValidationInfo):
        cited_ids = [
            source_id
            for section in self.sections
            for source_id in section.source_ids
        ]

        if self.grounding is None:
            if cited_ids:
                raise ValueError(
                    "Ordinary lessons cannot contain source citations."
                )
            return self

        context = info.context or {}
        expected_fingerprint = context.get("expected_fingerprint")

        if (
            expected_fingerprint is not None
            and self.grounding.document_fingerprint != expected_fingerprint
        ):
            raise ValueError("Lesson sources belong to a different PDF.")

        allowed_sources = context.get("allowed_sources")

        if allowed_sources is not None:
            allowed_by_id = {
                source.chunk_id: source
                for source in allowed_sources
            }

            if len(allowed_by_id) != len(allowed_sources):
                raise ValueError("Duplicate allowed source IDs found.")

            allowed_filenames = {
                source.source_filename
                for source in allowed_sources
            }

            if self.grounding.source_filename not in allowed_filenames:
                raise ValueError(
                    "Lesson filename does not match retrieved sources."
                )

            for source in self.grounding.sources:
                allowed = allowed_by_id.get(source.chunk_id)

                if allowed is None:
                    raise ValueError(
                        "A lesson source was not retrieved."
                    )
                mismatches = []

                if source.source_filename != allowed.source_filename:
                    mismatches.append("source_filename")

                if source.page_number != allowed.page_number:
                    mismatches.append("page_number")

                if source.chunk_index != allowed.chunk_index:
                    mismatches.append("chunk_index")

                if source.text != allowed.text:
                    mismatches.append("text")

                if source.similarity != allowed.score:
                    mismatches.append("similarity")

                if mismatches:
                    raise ValueError(
                        f"Lesson source details do not match retrieved data: "
                        f"{', '.join(mismatches)}"
                    )
           
        if not cited_ids:
            raise ValueError(
                "Grounded lessons must cite at least one source."
            )

        source_ids = [
            source.chunk_id
            for source in self.grounding.sources
        ]

        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Duplicate sources found.")

        available_ids = set(source_ids)
        cited_id_set = set(cited_ids)

        if not cited_id_set.issubset(available_ids):
            raise ValueError("A cited source is missing from the sources list.")

        if available_ids != cited_id_set:
            raise ValueError("Every listed source must be cited.")

        return self


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def validate_lesson(
    data,
    expected_lesson_number=None,
    expected_title=None,
    allowed_sources=None,
    expected_fingerprint=None,
):
    return LessonContent.model_validate(
        data,
        context={
            "expected_lesson_number": expected_lesson_number,
            "expected_title": expected_title,
            "allowed_sources": allowed_sources,
            "expected_fingerprint": expected_fingerprint,
        },
    )
