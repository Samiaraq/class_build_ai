import copy
import json
import logging

from pydantic import ValidationError

from classbuild.llm.exceptions import (
    EmptyResponseError,
    InvalidJSONError,
    GroqClientError,
)


MAX_ATTEMPTS = 2
LOG_PREVIEW_CHARS = 200

_UNSENT_KEYWORDS = {
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
}


class CourseGenerationError(Exception):
    """Base class for generation errors."""


class ContentValidationError(CourseGenerationError):
    """Raised when generated JSON does not match the expected schema."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__("\n".join(problems))


class StructuredGenerationError(CourseGenerationError):
    """Raised when structured generation fails after all attempts."""


def _clean_schema(node):
    if isinstance(node, dict):
        return {
            key: _clean_schema(value)
            for key, value in node.items()
            if key not in _UNSENT_KEYWORDS
        }

    if isinstance(node, list):
        return [_clean_schema(item) for item in node]

    return node


def strict_schema(schema):
    cleaned = copy.deepcopy(schema)
    return _clean_schema(cleaned)


def describe_validation_error(exc):
    problems = []

    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        message = error["msg"]
        problems.append(f"{location}: {message}")

    return problems


def _log_structured_failure(logger, model, attempt, exc):
    module_logger = logger or logging.getLogger(__name__)
    preview = str(exc)[:LOG_PREVIEW_CHARS]
    category = getattr(exc, "category", type(exc).__name__)

    module_logger.warning(
        "Structured generation failed | model=%s | attempt=%s | "
        "category=%s | preview=%s",
        model,
        attempt,
        category,
        preview,
    )


def request_structured_json(
    client,
    *,
    prompt,
    schema,
    schema_name,
    system_prompts,
    max_completion_tokens,
    reasoning_effort,
    logger=None,
    what="content",
    advice="Please try again.",
):
    if len(system_prompts) != MAX_ATTEMPTS:
        raise ValueError("Exactly two system prompts are required.")

    last_error = None

    for attempt in range(MAX_ATTEMPTS):
        try:
            messages = [
                {
                    "role": "system",
                    "content": system_prompts[attempt],
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ]

            result = client.generate_json(
                prompt=prompt,
                schema=schema,
                schema_name=schema_name,
                system_prompt=system_prompts[attempt],
                max_completion_tokens=max_completion_tokens,
                reasoning_effort=reasoning_effort,
            )

            if isinstance(result, str):
                return json.loads(result)

            return result

        except InvalidJSONError as exc:
            last_error = exc
            _log_structured_failure(
                logging.getLogger(__name__),
                getattr(client, "model", "unknown"),
                attempt + 1,
                exc,
            )

        except json.JSONDecodeError as exc:
            last_error = exc
            _log_structured_failure(
                logging.getLogger(__name__),
                getattr(client, "model", "unknown"),
                attempt + 1,
                exc,
            )

        except GroqClientError:
            raise

    raise StructuredGenerationError(
        f"The AI couldn't produce valid {what} after "
        f"{MAX_ATTEMPTS} attempts. {advice}"
    ) from last_error