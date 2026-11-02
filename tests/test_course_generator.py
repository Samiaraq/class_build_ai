
import json
import logging
import unittest
from unittest.mock import Mock, patch

from groq import BadRequestError
from pydantic import ValidationError

from classbuild.course_config import CourseConfig
from classbuild.llm.exceptions import (
    AuthenticationError,
    EmptyResponseError,
    GroqAPIError,
    GroqClientError,
    InvalidJSONError,
    RateLimitError,
    GroqServerError,
)
from classbuild.llm.groq_client import GroqClient
from classbuild.models.course import validate_outline
from classbuild.services.course_generator import (
    CourseGenerator,
    OutlineValidationError,
    build_prompt,
    outline_json_schema,
)
from classbuild.services.structured_output import (
    StructuredGenerationError,
)
from tests.fixtures import valid_outline, copy_of


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_json(self, **kwargs):
        self.calls.append(kwargs)

        response = self.responses.pop(0)

        if isinstance(response, Exception):
            raise response

        return response


def json_failure(message="Invalid JSON response"):
    return InvalidJSONError(
        message,
        category="json_validate_failed",
    )


def make_config(topic="Python Basics", difficulty="Beginner", lesson_count=3):
    return CourseConfig(
        topic=topic,
        difficulty=difficulty,
        lesson_count=lesson_count,
    )


def fake_completion(content, finish_reason="stop"):
    return Mock(
        choices=[
            Mock(
                message=Mock(content=content),
                finish_reason=finish_reason,
            )
        ]
    )


def groq_400(body):
    response = Mock()
    response.json.return_value = body
    response.status_code = 400  # أضيفي هذا السطر

    return BadRequestError(
        "Bad request",
        response=response,
        body=body,
    )


class SuccessfulGenerationTests(unittest.TestCase):

    def test_success_on_first_attempt(self):
        expected = valid_outline(lesson_count=4)
        client = FakeClient([expected])

        generator = CourseGenerator(client=client)

        outline = generator.generate_outline(
            make_config(lesson_count=4)
        )

        self.assertEqual(len(outline.lessons), 4)
        self.assertEqual(len(client.calls), 1)

    def test_request_settings(self):
        client = FakeClient([valid_outline()])

        generator = CourseGenerator(client=client)
        generator.generate_outline(make_config())

        call = client.calls[0]

        self.assertEqual(call["system_prompt"], call["system_prompt"])
        self.assertEqual(call["max_completion_tokens"], 3000)
        self.assertEqual(call["reasoning_effort"], "low")

    def test_prompt_contains_request(self):
        config = make_config(
            topic="Python Functions",
            difficulty="Intermediate",
            lesson_count=4,
        )

        prompt = build_prompt(config)

        self.assertIn("Python Functions", prompt)
        self.assertIn("Intermediate", prompt)
        self.assertIn("exactly 4", prompt)


class RetryTests(unittest.TestCase):

    def test_first_attempt_fails_second_succeeds(self):
        client = FakeClient([
            json_failure(),
            valid_outline(),
        ])

        generator = CourseGenerator(client=client)

        with self.assertLogs(
            "classbuild.services.structured_output",
            level="WARNING",
        ):
            outline = generator.generate_outline(make_config())

        self.assertEqual(len(outline.lessons), 3)
        self.assertEqual(len(client.calls), 2)
        self.assertNotEqual(
            client.calls[0]["system_prompt"],
            client.calls[1]["system_prompt"],
        )

    def test_truncated_output_is_retried(self):
        client = FakeClient([
            json_failure("Response was truncated"),
            valid_outline(),
        ])

        generator = CourseGenerator(client=client)

        with self.assertLogs(
            "classbuild.services.structured_output",
            level="WARNING",
        ):
            outline = generator.generate_outline(make_config())

        self.assertEqual(len(outline.lessons), 3)
        self.assertEqual(len(client.calls), 2)

    def test_both_attempts_fail(self):
        client = FakeClient([
            json_failure(),
            json_failure(),
        ])

        generator = CourseGenerator(client=client)

        with self.assertLogs(
            "classbuild.services.structured_output",
            level="WARNING",
        ):
            with self.assertRaises(StructuredGenerationError):
                generator.generate_outline(make_config())

        self.assertEqual(len(client.calls), 2)

    def test_log_preview_is_truncated(self):
        from classbuild.services.structured_output import (
            _log_structured_failure,
            LOG_PREVIEW_CHARS,
        )

        logger = logging.getLogger("test_logger")
        error = json_failure("X" * 5000)

        with self.assertLogs(logger, level="WARNING") as captured:
            _log_structured_failure(
                logger,
                "test-model",
                1,
                error,
            )

        self.assertLessEqual(
            len(captured.output[0]),
            LOG_PREVIEW_CHARS + 200,
        )

    def test_unrelated_errors_are_not_retried(self):
        errors = [
            AuthenticationError("Unauthorized"),
            RateLimitError("Rate limit"),
            GroqServerError("Server error"),
            GroqAPIError("API error"),
            EmptyResponseError("Empty response"),
        ]

        for error in errors:
            with self.subTest(error=type(error).__name__):
                client = FakeClient([error])
                generator = CourseGenerator(client=client)

                with self.assertRaises(GroqClientError):
                    generator.generate_outline(make_config())

                self.assertEqual(len(client.calls), 1)


class ValidationTests(unittest.TestCase):

    def test_wrong_lesson_count_rejected_without_retry(self):
        client = FakeClient([valid_outline(lesson_count=2)])

        generator = CourseGenerator(client=client)

        with self.assertRaises(OutlineValidationError):
            generator.generate_outline(
                make_config(lesson_count=3)
            )

        self.assertEqual(len(client.calls), 1)

    def test_invalid_pydantic_data_rejected(self):
        invalid_cases = []

        missing_field = copy_of(valid_outline())
        del missing_field["title"]
        invalid_cases.append(missing_field)

        bad_difficulty = copy_of(valid_outline())
        bad_difficulty["difficulty"] = "Expert"
        invalid_cases.append(bad_difficulty)

        empty_objective = copy_of(valid_outline())
        empty_objective["learning_objectives"][0] = ""
        invalid_cases.append(empty_objective)

        bad_numbering = copy_of(valid_outline())
        bad_numbering["lessons"][1]["lesson_number"] = 5
        invalid_cases.append(bad_numbering)

        for data in invalid_cases:
            with self.subTest(data=data):
                client = FakeClient([data])
                generator = CourseGenerator(client=client)

                with self.assertRaises(OutlineValidationError):
                    generator.generate_outline(make_config())

                self.assertEqual(len(client.calls), 1)

    def test_difficulty_mismatch_rejected(self):
        client = FakeClient([
            valid_outline(difficulty="Advanced")
        ])

        generator = CourseGenerator(client=client)

        with self.assertRaises(OutlineValidationError):
            generator.generate_outline(
                make_config(difficulty="Beginner")
            )

        self.assertEqual(len(client.calls), 1)


class SchemaTests(unittest.TestCase):

    def test_schema_is_strict_mode_friendly(self):
        schema = outline_json_schema()

        def check_node(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertEqual(
                        node.get("additionalProperties"),
                        False,
                    )
                    self.assertEqual(
                        set(node.get("required", [])),
                        set(node.get("properties", {}).keys()),
                    )

                forbidden = {
                    "minItems",
                    "maxItems",
                    "minLength",
                    "maxLength",
                    "minimum",
                    "maximum",
                    "exclusiveMinimum",
                    "exclusiveMaximum",
                }

                self.assertTrue(forbidden.isdisjoint(node.keys()))

                for value in node.values():
                    check_node(value)

            elif isinstance(node, list):
                for value in node:
                    check_node(value)

        check_node(schema)

    def test_build_prompt(self):
        prompt = build_prompt(make_config(topic="Machine Learning"))

        self.assertIn("Machine Learning", prompt)


class GenerateJsonTests(unittest.TestCase):

    def setUp(self):
        self.sdk = Mock()
        self.client = GroqClient.__new__(GroqClient)
        self.client.client = self.sdk
        self.client.model = "openai/gpt-oss-20b"
        self.client.timeout_seconds = 60

        self.sdk.chat.completions.create.return_value = (
            fake_completion('{"result": "ok"}')
        )

    def test_strict_schema_mode_for_gpt_oss(self):
        schema = {
            "name": "test_schema",
            "schema": {
                "type": "object",
                "properties": {
                    "result": {"type": "string"}
                },
                "required": ["result"],
                "additionalProperties": False,
            },
        }

        result = self.client.generate_json(
            "Return JSON",
            schema,
            schema_name="test_schema",
        )

        self.assertEqual(result, {"result": "ok"})

        kwargs = self.sdk.chat.completions.create.call_args.kwargs

        self.assertEqual(
            kwargs["response_format"]["type"],
            "json_schema",
        )
        self.assertTrue(
            kwargs["response_format"]["json_schema"]["strict"]
        )

    def test_token_and_reasoning_settings_sent(self):
        self.client.generate_json(
            "Return JSON",
            {},
            schema_name="test",
            max_completion_tokens=3000,
            reasoning_effort="low",
        )

        kwargs = self.sdk.chat.completions.create.call_args.kwargs

        self.assertEqual(kwargs["max_completion_tokens"], 3000)
        self.assertEqual(kwargs["reasoning_effort"], "low")

    def test_reasoning_effort_skipped_for_non_reasoning_models(self):
        self.client.model = "llama-3.3-70b-versatile"

        self.client.generate_json(
            "Return JSON",
            {},
            schema_name="test",
            reasoning_effort="low",
        )

        kwargs = self.sdk.chat.completions.create.call_args.kwargs

        self.assertNotIn("reasoning_effort", kwargs)

    def test_json_object_mode_for_other_models(self):
        self.client.model = "llama-3.3-70b-versatile"

        self.client.generate_json(
            "Return JSON",
            {"type": "object"},
            schema_name="test",
        )

        kwargs = self.sdk.chat.completions.create.call_args.kwargs

        self.assertEqual(
            kwargs["response_format"]["type"],
            "json_object",
        )
        self.assertIn("JSON schema", kwargs["messages"][0]["content"])

    def test_json_validate_failed_is_recognized(self):
        body = {
            "error": {
                "code": "json_validate_failed",
                "message": "Invalid schema output",
            }
        }

        error = groq_400(body)

        with patch.object(
            self.client,
            "_chat",
            side_effect=error,
        ):
            with self.assertRaises(InvalidJSONError):
                self.client.generate_json("Return JSON", {})

    def test_other_400_is_not_a_json_failure(self):
        body = {
            "error": {
                "code": "bad_request",
                "message": "Invalid request",
            }
        }

        error = groq_400(body)

        with patch.object(
            self.client,
            "_chat",
            side_effect=error,
        ):
            with self.assertRaises(GroqAPIError):
                self.client.generate_json("Return JSON", {})

    def test_truncated_output(self):
        self.sdk.chat.completions.create.return_value = (
            fake_completion('{"result":', finish_reason="length")
        )

        with self.assertRaises(InvalidJSONError):
            self.client.generate_json("Return JSON", {})

    def test_invalid_json_raises(self):
        self.sdk.chat.completions.create.return_value = (
            fake_completion("This is not JSON")
        )

        with self.assertRaises(InvalidJSONError):
            self.client.generate_json("Return JSON", {})

    def test_empty_response_raises(self):
        self.sdk.chat.completions.create.return_value = (
            fake_completion("")
        )

        with self.assertRaises(EmptyResponseError):
            self.client.generate_json("Return JSON", {})

    def test_text_generation_unchanged(self):
        self.client.generate("Say hello")

        kwargs = self.sdk.chat.completions.create.call_args.kwargs

        self.assertNotIn("response_format", kwargs)


if __name__ == "__main__":
    unittest.main()
