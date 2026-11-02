
import logging

from pydantic import ValidationError

from classbuild.course_config import CourseConfig
from classbuild.llm.groq_client import GroqClient
from classbuild.models.course import CourseOutline, validate_outline
from classbuild.services.structured_output import (
    ContentValidationError,
    describe_validation_error,
    request_structured_json,
    strict_schema,
)


SCHEMA_NAME = "course_outline"
MAX_COMPLETION_TOKENS = 3000
REASONING_EFFORT = "low"

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
You are an expert instructional designer.

Create high-quality course outlines that follow these rules:
- Stay focused on the requested topic.
- Match the selected difficulty level.
- Organize lessons from introductory to more advanced concepts.
- Avoid repeating topics across lessons.
- Write clear and practical learning objectives.
- Ensure every lesson contributes to the overall course goals.
- Follow the requested number of lessons exactly.
- Return only valid JSON matching the provided schema.
"""

RETRY_SYSTEM_PROMPT = """
Return one valid JSON object only.
Follow the provided schema exactly.
Do not include Markdown, explanations, or code fences.
Check that all required fields are present and correctly formatted.
"""


class OutlineValidationError(ContentValidationError):
    """Raised when the generated outline fails validation."""


def build_prompt(config: CourseConfig) -> str:
    return f"""
Create a structured course outline using the following configuration:

Topic: {config.topic}
Difficulty: {config.difficulty}
Number of lessons: {config.lesson_count}

Requirements:
- Create exactly {config.lesson_count} lessons.
- Number lessons sequentially from 1 to {config.lesson_count}.
- Include a clear course title and description.
- Include 3 to 5 course learning objectives.
- Each lesson must have a title, description, and 2 to 3 learning objectives.
- Arrange lessons from introductory to advanced.
- Avoid repeating topics between lessons.

Return JSON matching the provided schema.
"""


def outline_json_schema() -> dict:
    schema = CourseOutline.model_json_schema()
    return strict_schema(schema)


class CourseGenerator:

    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = GroqClient()

        return self._client

    def generate_outline(self, config: CourseConfig) -> CourseOutline:
        prompt = build_prompt(config)

        data = request_structured_json(
            self.client,
            prompt=prompt,
            schema=outline_json_schema(),
            schema_name=SCHEMA_NAME,
            system_prompts=[
                SYSTEM_PROMPT,
                RETRY_SYSTEM_PROMPT,
            ],
            max_completion_tokens=MAX_COMPLETION_TOKENS,
            reasoning_effort=REASONING_EFFORT,
            logger=logger,
            what="course outline",
            advice="Please try generating the course again.",
        )

        try:
            return validate_outline(
                data,
                expected_lesson_count=config.lesson_count,
                expected_difficulty=config.difficulty,
            )

        except ValidationError as exc:
            problems = describe_validation_error(exc)

            logger.warning(
                "Generated course outline failed validation: %s",
                problems,
            )

            raise OutlineValidationError(problems) from exc
