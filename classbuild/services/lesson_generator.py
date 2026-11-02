
import logging

from pydantic import ValidationError

from classbuild.llm.groq_client import GroqClient
from classbuild.models.lesson import LessonContent, validate_lesson
from classbuild.services.structured_output import (
    ContentValidationError,
    describe_validation_error,
    request_structured_json,
    strict_schema,
)


SCHEMA_NAME = "lesson_content"
MAX_COMPLETION_TOKENS = 4000
REASONING_EFFORT = "low"

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
You are an expert teacher and instructional designer.

Create clear and detailed educational lesson content.
Follow these rules:
- Teach the selected lesson at the course's difficulty level.
- Write approximately 400 to 700 words.
- Start with a clear introduction.
- Create between 2 and 4 sections.
- Each section must include a heading, explanation, and practical example.
- Include a concise summary.
- Create exactly 2 exercises, each with a question and a hint.
- Do not include a quiz.
- Do not repeat topics covered by other lessons.
- Use accurate and useful educational information.
- Return only valid JSON matching the provided schema.
"""

RETRY_SYSTEM_PROMPT = """
Return one valid JSON object only.
Follow the provided schema exactly.
Do not include Markdown, explanations, or code fences.
Make sure all required fields are present and correctly formatted.
"""


class LessonSelectionError(ValueError):
    """Raised when the requested lesson cannot be found."""


class LessonValidationError(ContentValidationError):
    """Raised when generated lesson content fails validation."""


def find_lesson(outline, lesson_number):
    if outline is None:
        raise LessonSelectionError(
            "A course outline is required before generating lesson content."
        )

    for lesson in outline.lessons:
        if lesson.lesson_number == lesson_number:
            return lesson

    available_numbers = [
        lesson.lesson_number for lesson in outline.lessons
    ]

    raise LessonSelectionError(
        f"Lesson {lesson_number} was not found. "
        f"Available lesson numbers: {available_numbers}."
    )


def build_lesson_prompt(outline, lesson) -> str:
    other_lessons = [
        item.title
        for item in outline.lessons
        if item.lesson_number != lesson.lesson_number
    ]

    return f"""
Create the full educational content for one lesson in this course.

Course title: {outline.title}
Course difficulty: {outline.difficulty}
Course learning objectives: {outline.learning_objectives}

Selected lesson:
Lesson number: {lesson.lesson_number}
Lesson title: {lesson.title}
Lesson description: {lesson.description}
Lesson learning objectives: {lesson.learning_objectives}

Other lessons in this course:
{other_lessons}

Requirements:
- Focus only on the selected lesson.
- Cover all its learning objectives.
- Avoid repeating the topics of the other lessons.
- Use the exact lesson number: {lesson.lesson_number}.
- Use the exact lesson title: {lesson.title}.
- Write approximately 400 to 700 words.
- Include an introduction.
- Create 2 to 4 sections.
- Every section must have a heading, explanation, and practical example.
- Include a summary.
- Include exactly 2 exercises.
- Each exercise must contain a question and a hint.
- Do not create a quiz.

Return JSON matching the provided schema.
"""


def lesson_json_schema(lesson) -> dict:
    schema = LessonContent.model_json_schema()

    schema["properties"]["lesson_number"]["enum"] = [
        lesson.lesson_number
    ]
    schema["properties"]["title"]["enum"] = [
        lesson.title
    ]

    return strict_schema(schema)


class LessonGenerator:

    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = GroqClient()

        return self._client

    def generate_lesson(self, outline, lesson_number: int) -> LessonContent:
        lesson = find_lesson(outline, lesson_number)

        prompt = build_lesson_prompt(outline, lesson)

        data = request_structured_json(
            self.client,
            prompt=prompt,
            schema=lesson_json_schema(lesson),
            schema_name=SCHEMA_NAME,
            system_prompts=[
                SYSTEM_PROMPT,
                RETRY_SYSTEM_PROMPT,
            ],
            max_completion_tokens=MAX_COMPLETION_TOKENS,
            reasoning_effort=REASONING_EFFORT,
            logger=logger,
            what="lesson content",
            advice="Please try generating the lesson again.",
        )

        try:
            return validate_lesson(
                data,
                expected_lesson_number=lesson.lesson_number,
                expected_title=lesson.title,
            )

        except ValidationError as exc:
            problems = describe_validation_error(exc)

            logger.warning(
                "Generated lesson failed validation: %s",
                problems,
            )

            raise LessonValidationError(problems) from exc
