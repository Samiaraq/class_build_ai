DIFFICULTY_LEVELS = (
    "Beginner",
    "Intermediate",
    "Advanced",
)

DEFAULT_DIFFICULTY = "Beginner"

MIN_LESSONS = 2
MAX_LESSONS = 5
DEFAULT_LESSONS = 3

from dataclasses import dataclass


@dataclass(frozen=True)
class CourseConfig:
    topic: str
    difficulty: str
    lesson_count: int

    def to_dict(self):
        return {
            "topic": self.topic,
            "difficulty": self.difficulty,
            "lesson_count": self.lesson_count,
        }


class CourseConfigError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("\n".join(errors))


def validate_course_config(topic, difficulty, lesson_count):
    errors = []

    if not isinstance(topic, str) or not topic.strip():
        errors.append("Topic cannot be empty.")

    if difficulty not in DIFFICULTY_LEVELS:
        errors.append(
            f"Difficulty must be one of: {', '.join(DIFFICULTY_LEVELS)}."
        )

    if (
        isinstance(lesson_count, bool)
        or not isinstance(lesson_count, int)
        or not MIN_LESSONS <= lesson_count <= MAX_LESSONS
    ):
        errors.append(
            f"Lesson count must be an integer between "
            f"{MIN_LESSONS} and {MAX_LESSONS}."
        )

    if errors:
        raise CourseConfigError(errors)

    return CourseConfig(
        topic=topic.strip(),
        difficulty=difficulty,
        lesson_count=lesson_count,
    )