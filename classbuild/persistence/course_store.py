
"""Safe local JSON storage for saved Mini ClassBuild courses."""

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .saved_course import (
    SavedCourse,
    SCHEMA_VERSION,
)


DEFAULT_SAVE_DIR = "saved_courses"
SAVE_DIR_ENV = "MINICLASSBUILD_SAVE_DIR"
MAX_COURSE_FILE_BYTES = 2 * 1024 * 1024

COURSE_FILE_PATTERN = re.compile(r"^course-([a-fA-F0-9]{32})\.json$")


class CourseStorageError(Exception):
    """Base exception for course storage errors."""


class InvalidCourseIdError(CourseStorageError):
    """Raised when a course ID is invalid."""


class CourseNotFoundError(CourseStorageError):
    """Raised when a saved course does not exist."""


class CourseFileTooLargeError(CourseStorageError):
    """Raised when a course file exceeds the allowed size."""


class CorruptedCourseFileError(CourseStorageError):
    """Raised when a saved course file cannot be read or validated."""


class UnsupportedSchemaVersionError(CourseStorageError):
    """Raised when a course uses an unsupported file format version."""


@dataclass(frozen=True)
class SavedCourseSummary:
    """Short information about one saved course."""

    course_id: str
    title: str
    topic: str
    difficulty: str
    lesson_count: int
    quiz_count: int
    is_pdf_based: bool
    updated_at: datetime


@dataclass(frozen=True)
class CourseListing:
    """Readable courses and notes about files that could not be read."""

    courses: tuple[SavedCourseSummary, ...]
    issues: tuple[str, ...]


class CourseStore:
    """Save and load validated courses from a local folder."""

    def __init__(self, directory=None, max_bytes=MAX_COURSE_FILE_BYTES):
        if max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero.")

        configured_directory = (
            directory
            if directory is not None
            else os.getenv(SAVE_DIR_ENV, DEFAULT_SAVE_DIR)
        )

        self.directory = Path(configured_directory).expanduser().resolve()
        self.max_bytes = max_bytes
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, course_id):
        """Return the safe file path for a valid course ID."""

        if not isinstance(course_id, str) or not re.fullmatch(
            r"[a-fA-F0-9]{32}", course_id
        ):
            raise InvalidCourseIdError(
                "Invalid course ID. The ID must contain 32 hexadecimal characters."
            )

        filename = f"course-{course_id}.json"
        path = (self.directory / filename).resolve()

        try:
            path.relative_to(self.directory)
        except ValueError as exc:
            raise InvalidCourseIdError(
                "The course file path is outside the storage directory."
            ) from exc

        return path

    def save(self, course):
        """Validate and atomically save a course. Return its file path."""

        try:
            if isinstance(course, SavedCourse):
                validated_course = SavedCourse.model_validate(
                    course.model_dump()
                )
            else:
                validated_course = SavedCourse.model_validate(course)
        except Exception as exc:
            raise CorruptedCourseFileError(
                f"Course data is invalid: {exc}"
            ) from exc

        path = self.path_for(validated_course.course_id)

        try:
            content = validated_course.model_dump_json(
                indent=2
            ).encode("utf-8")
        except Exception as exc:
            raise CorruptedCourseFileError(
                f"Could not serialize the course: {exc}"
            ) from exc

        if len(content) > self.max_bytes:
            raise CourseFileTooLargeError(
                f"Course file exceeds the {self.max_bytes}-byte size limit."
            )

        temporary_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.directory,
                prefix=".course-",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, path)

        except OSError as exc:
            raise CourseStorageError(
                f"Could not save the course: {exc}"
            ) from exc

        finally:
            if temporary_path is not None and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

        return path

    def load(self, course_id):
        """Load a course and validate its ID, size, schema and contents."""

        path = self.path_for(course_id)

        if not path.is_file():
            raise CourseNotFoundError(
                f"No saved course was found for ID: {course_id}"
            )

        try:
            file_size = path.stat().st_size

            if file_size > self.max_bytes:
                raise CourseFileTooLargeError(
                    f"Course file exceeds the {self.max_bytes}-byte size limit."
                )

            raw_content = path.read_text(encoding="utf-8")
            data = json.loads(raw_content)

        except CourseFileTooLargeError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CorruptedCourseFileError(
                f"The saved course file is damaged or unreadable: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise CorruptedCourseFileError(
                "The saved course file must contain a JSON object."
            )

        if data.get("schema_version") != SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError(
                "This saved course uses an unsupported schema version."
            )

        try:
            course = SavedCourse.model_validate(data)
        except Exception as exc:
            raise CorruptedCourseFileError(
                f"The saved course data is invalid: {exc}"
            ) from exc

        if course.course_id != course_id:
            raise CorruptedCourseFileError(
                "The course ID inside the file does not match its filename."
            )

        return course

    def list_courses(self):
        """Return readable course summaries, newest first."""

        summaries = []
        issues = []

        for path in self.directory.glob("course-*.json"):
            match = COURSE_FILE_PATTERN.fullmatch(path.name)

            if match is None:
                continue

            course_id = match.group(1)

            try:
                course = self.load(course_id)

                summaries.append(
                    SavedCourseSummary(
                        course_id=course.course_id,
                        title=course.outline.title,
                        topic=course.topic,
                        difficulty=str(course.difficulty),
                        lesson_count=len(course.lessons),
                        quiz_count=len(course.quizzes),
                        is_pdf_based=course.source_document is not None,
                        updated_at=course.updated_at,
                    )
                )

            except CourseStorageError as exc:
                issues.append(f"{path.name}: {exc}")

        summaries.sort(
            key=lambda item: item.updated_at,
            reverse=True,
        )

        return CourseListing(
            courses=tuple(summaries),
            issues=tuple(issues),
        )
