
"""Validated data models for locally saved courses."""

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from classbuild.models.course import CourseOutline
from classbuild.models.lesson import LessonContent
from classbuild.models.quiz import Quiz


SCHEMA_VERSION = 1
APP_NAME = "Mini ClassBuild"
COURSE_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{32}$")


def _utc_now():
    return datetime.now(timezone.utc)


def new_course_id():
    """Generate a random 32-character hexadecimal course ID."""
    return uuid.uuid4().hex


class SourceDocument(BaseModel):
    """Metadata about the PDF used for grounded lessons."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: str = Field(min_length=1)
    fingerprint: str = Field(min_length=1)

    @field_validator("filename", "fingerprint")
    @classmethod
    def validate_not_blank(cls, value):
        if not value.strip():
            raise ValueError("This field cannot be blank.")
        return value.strip()


class SavedCourse(BaseModel):
    """Complete validated course data stored in a JSON file."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    app: str = APP_NAME
    course_id: str
    created_at: datetime
    updated_at: datetime

    topic: str = Field(min_length=1)
    difficulty: str
    outline: CourseOutline
    lessons: list[LessonContent] = Field(default_factory=list)
    quizzes: list[Quiz] = Field(default_factory=list)

    source_document: Optional[SourceDocument] = None
    selected_lesson: Optional[int] = None

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value):
        if value != SCHEMA_VERSION:
            raise ValueError("Unsupported saved-course schema version.")
        return value

    @field_validator("app")
    @classmethod
    def validate_app_name(cls, value):
        if value != APP_NAME:
            raise ValueError("Invalid application name.")
        return value

    @field_validator("course_id")
    @classmethod
    def validate_course_id(cls, value):
        if not COURSE_ID_PATTERN.fullmatch(value):
            raise ValueError(
                "Course ID must contain exactly 32 hexadecimal characters."
            )
        return value

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value):
        if not value.strip():
            raise ValueError("Course topic cannot be blank.")
        return value.strip()

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, value):
        if not value.strip():
            raise ValueError("Course difficulty cannot be blank.")
        return value.strip()

    @model_validator(mode="after")
    def check_consistency(self):
        outline_numbers = [
            lesson.lesson_number for lesson in self.outline.lessons
        ]

        lesson_numbers = [
            lesson.lesson_number for lesson in self.lessons
        ]

        quiz_numbers = [
            quiz.lesson_number for quiz in self.quizzes
        ]

        if len(lesson_numbers) != len(set(lesson_numbers)):
            raise ValueError("Duplicate lesson numbers are not allowed.")

        if len(quiz_numbers) != len(set(quiz_numbers)):
            raise ValueError("Duplicate quiz lesson numbers are not allowed.")

        outline_set = set(outline_numbers)
        lesson_set = set(lesson_numbers)

        if not lesson_set.issubset(outline_set):
            raise ValueError(
                "Every generated lesson must exist in the course outline."
            )

        if not set(quiz_numbers).issubset(lesson_set):
            raise ValueError(
                "A quiz can only exist for a generated lesson."
            )

        if self.selected_lesson is not None:
            if self.selected_lesson not in outline_set:
                raise ValueError(
                    "The selected lesson does not exist in the outline."
                )

        grounded_lessons = [
            lesson for lesson in self.lessons
            if lesson.grounding is not None
        ]

        if grounded_lessons and self.source_document is None:
            raise ValueError(
                "Grounded lessons require a source document."
            )

        if self.source_document is not None:
            for lesson in grounded_lessons:
                grounding = lesson.grounding
                
                if grounding.source_filename != self.source_document.filename:
                    raise ValueError(
                        "Grounded lesson filename does not match the source document."
                    )

                if grounding.document_fingerprint != self.source_document.fingerprint:
                    raise ValueError(
                        "Grounded lesson fingerprint does not match the source document."
                    )

        return self

    def lessons_by_number(self):
        """Return generated lessons indexed by lesson number."""
        return {
            lesson.lesson_number: lesson
            for lesson in self.lessons
        }

    def quizzes_by_number(self):
        """Return quizzes indexed by lesson number."""
        return {
            quiz.lesson_number: quiz
            for quiz in self.quizzes
        }

    def content_hash(self):
        """Hash course content without timestamps."""

        content = self.model_dump(
            mode="json",
            exclude={"created_at", "updated_at"},
        )

        serialized = json.dumps(
            content,
            sort_keys=True,
            ensure_ascii=False,
        )

        return hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()


def build_saved_course(
    *,
    course_id,
    topic,
    outline,
    lessons,
    quizzes,
    created_at=None,
    selected_lesson=None,
):
    """Build a validated saved course from the current course data."""

    if isinstance(outline, dict):
        outline = CourseOutline.model_validate(outline)

    validated_lessons = [
        lesson if isinstance(lesson, LessonContent)
        else LessonContent.model_validate(lesson)
        for lesson in lessons
    ]

    validated_quizzes = [
        quiz if isinstance(quiz, Quiz)
        else Quiz.model_validate(quiz)
        for quiz in quizzes
    ]

    source_document = None

    for lesson in validated_lessons:
        if lesson.grounding is not None:
            grounding = lesson.grounding

            current_source = SourceDocument(
                filename=grounding.source_filename,
                fingerprint=grounding.document_fingerprint,
            )

            if source_document is None:
                source_document = current_source
            elif source_document != current_source:
                raise ValueError(
                    "All grounded lessons must use the same source document."
                )

    now = _utc_now()

    return SavedCourse(
        schema_version=SCHEMA_VERSION,
        app=APP_NAME,
        course_id=course_id,
        created_at=created_at or now,
        updated_at=now,
        topic=topic,
        difficulty=outline.difficulty,
        outline=outline,
        lessons=validated_lessons,
        quizzes=validated_quizzes,
        source_document=source_document,
        selected_lesson=selected_lesson,
    )
