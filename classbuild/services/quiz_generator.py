
import logging

from pydantic import ValidationError

from classbuild.llm.groq_client import GroqClient
from classbuild.models.quiz import Quiz, validate_quiz
from classbuild.services.lesson_generator import (
    LessonSelectionError,
    find_lesson,
)
from classbuild.services.structured_output import (
    ContentValidationError,
    describe_validation_error,
    request_structured_json,
    strict_schema,
)


SCHEMA_NAME = "lesson_quiz"
MAX_COMPLETION_TOKENS = 3000
REASONING_EFFORT = "low"

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
You are an expert educational assessment designer.

Create a quiz based only on the provided lesson content.

Follow these rules:
- Generate exactly 5 different questions.
- Each question must have exactly 4 distinct options.
- Each question must have exactly one correct answer.
- The correct answer must be represented by an index from 0 to 3.
- Include a clear explanation for the correct answer.
- Test only concepts covered in the lesson.
- Include a mix of understanding and application questions.
- Avoid trick questions and ambiguous wording.
- Do not repeat questions.
- Return only valid JSON matching the provided schema.
"""

RETRY_SYSTEM_PROMPT = """
Return one valid JSON object only.
Follow the provided schema exactly.
Create exactly 5 questions with 4 distinct options each.
Each question must have one correct answer.
Do not include Markdown, explanations outside the JSON, or code fences.
"""


class QuizPrerequisiteError(ValueError):
    """Raised when the lesson content required for a quiz is missing or invalid."""


class QuizValidationError(ContentValidationError):
    """Raised when the generated quiz fails validation."""


def build_quiz_prompt(outline, lesson, content) -> str:
    sections_text = "\n\n".join(
        f"""
        Section: {section.heading}
        Explanation: {section.explanation}
        Example: {section.example}
        """
        for section in content.sections
    )

    return f"""
Create a quiz based on the following lesson content.

Course title: {outline.title}
Course difficulty: {outline.difficulty}

Lesson number: {lesson.lesson_number}
Lesson title: {lesson.title}
Lesson learning objectives: {lesson.learning_objectives}

Lesson introduction:
{content.introduction}

Lesson sections:
{sections_text}

Lesson summary:
{content.summary}

Requirements:
- Generate exactly 5 different questions.
- Each question must have exactly 4 distinct options.
- Each question must have exactly one correct answer.
- Use correct_answer as an integer from 0 to 3.
- Include an explanation for each question.
- Test only information covered in this lesson.
- Include both understanding and application questions.
- Avoid trick questions.

Return JSON matching the provided schema.
"""


def quiz_json_schema(lesson) -> dict:
    schema = Quiz.model_json_schema()

    schema["properties"]["lesson_number"]["enum"] = [
        lesson.lesson_number
    ]

    schema["properties"]["lesson_title"]["enum"] = [
        lesson.title
    ]

    question_schema = schema["$defs"]["Question"]

    question_schema["properties"]["correct_answer"]["enum"] = [
        0, 1, 2, 3
    ]

    return strict_schema(schema)


class QuizGenerator:

    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = GroqClient()

        return self._client

    def generate_quiz(
        self,
        outline,
        lesson_number: int,
        content,
    ) -> Quiz:

        try:
            lesson = find_lesson(outline, lesson_number)
        except LessonSelectionError as exc:
            raise QuizPrerequisiteError(str(exc)) from exc

        if content is None:
            raise QuizPrerequisiteError(
                "Lesson content must be generated before creating a quiz."
            )

        if (
            content.lesson_number != lesson.lesson_number
            or content.title.strip().lower() != lesson.title.strip().lower()
        ):
            raise QuizPrerequisiteError(
                "The provided lesson content does not match the selected lesson."
            )

        prompt = build_quiz_prompt(outline, lesson, content)

        data = request_structured_json(
            self.client,
            prompt=prompt,
            schema=quiz_json_schema(lesson),
            schema_name=SCHEMA_NAME,
            system_prompts=[
                SYSTEM_PROMPT,
                RETRY_SYSTEM_PROMPT,
            ],
            max_completion_tokens=MAX_COMPLETION_TOKENS,
            reasoning_effort=REASONING_EFFORT,
            logger=logger,
            what="lesson quiz",
            advice="Please try generating the quiz again.",
        )

        try:
            return validate_quiz(
                data,
                expected_lesson_number=lesson.lesson_number,
                expected_title=lesson.title,
            )

        except ValidationError as exc:
            problems = describe_validation_error(exc)

            logger.warning(
                "Generated quiz failed validation: %s",
                problems,
            )

            raise QuizValidationError(problems) from exc
