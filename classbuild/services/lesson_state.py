
from classbuild.models.lesson import LessonContent


def stale_grounded_lessons(
    lessons: dict[int, LessonContent],
    current_fingerprint: str | None,
) -> list[int]:
    return [
        lesson_number
        for lesson_number, lesson in lessons.items()
        if (
            lesson.grounding is not None
            and lesson.grounding.document_fingerprint != current_fingerprint
        )
    ]


def remove_stale_grounded_lessons(
    lessons: dict[int, LessonContent],
    current_fingerprint: str | None,
    *dependent: dict,
) -> None:
    stale_numbers = stale_grounded_lessons(
        lessons,
        current_fingerprint,
    )

    for lesson_number in stale_numbers:
        lessons.pop(lesson_number, None)

        for state_dict in dependent:
            state_dict.pop(lesson_number, None)
