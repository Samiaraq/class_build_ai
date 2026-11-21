
import os
import unittest
from unittest.mock import patch
from classbuild.llm.groq_client import redact_secrets
from classbuild.config import get_settings
from classbuild.services.structured_output import request_structured_json
import httpx
from groq import Groq as SDKGroq

from classbuild.llm.groq_client import GroqClient
from classbuild.llm.exceptions import (
    AuthenticationError,
    GroqAPIError,
    ModelNotFoundError,
)

class RetrySettingsTests(unittest.TestCase):

    def test_default_max_retries_is_one(self):
        with patch.dict(os.environ, {"GROQ_MAX_RETRIES": ""}):
            settings = get_settings()

        self.assertEqual(settings.max_retries, 1)

    def test_valid_retry_values(self):
        for value in ["0", "1", "2", "3"]:
            with self.subTest(value=value):
                with patch.dict(os.environ, {"GROQ_MAX_RETRIES": value}):
                    settings = get_settings()

                self.assertEqual(settings.max_retries, int(value))

    def test_retry_value_is_clamped(self):
        test_cases = {
            "-1": 0,
            "4": 3,
            "10": 3,
        }

        for value, expected in test_cases.items():
            with self.subTest(value=value):
                with patch.dict(os.environ, {"GROQ_MAX_RETRIES": value}):
                    settings = get_settings()

                self.assertEqual(settings.max_retries, expected)

    def test_invalid_retry_value_uses_default(self):
        with patch.dict(os.environ, {"GROQ_MAX_RETRIES": "abc"}):
            settings = get_settings()

        self.assertEqual(settings.max_retries, 1)

def completion_response(content="Hello"):
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "llama-3.3-70b-versatile",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        },
    )


class SDKRetryTests(unittest.TestCase):

    def test_temporary_server_error_is_retried(self):
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1

            if calls == 1:
                return httpx.Response(
                    503,
                    json={
                        "error": {
                            "message": "Temporary server error."
                        }
                    },
                )

            return completion_response("Success")

        http_client = httpx.Client(
            transport=httpx.MockTransport(handler)
        )

        try:
            with patch(
                "classbuild.llm.groq_client.Groq",
                side_effect=lambda **kwargs: SDKGroq(
                    **kwargs,
                    http_client=http_client,
                ),
            ):
                client = GroqClient(
                    api_key="gsk_test_key",
                    model="llama-3.3-70b-versatile",
                    max_retries=1,
                )

                result = client.generate("Hello")

            self.assertEqual(result, "Success")
            self.assertEqual(calls, 2)

        finally:
            http_client.close()

    def test_client_errors_are_not_retried(self):
        expected_errors = {
            400: GroqAPIError,
            401: AuthenticationError,
            403: AuthenticationError,
            404: ModelNotFoundError,
        }

        for status, expected_error in expected_errors.items():
            with self.subTest(status=status):
                calls = 0

                def handler(request):
                    nonlocal calls
                    calls += 1

                    return httpx.Response(
                        status,
                        json={
                            "error": {
                                "message": "Request failed."
                            }
                        },
                    )

                http_client = httpx.Client(
                    transport=httpx.MockTransport(handler)
                )

                try:
                    with patch(
                        "classbuild.llm.groq_client.Groq",
                        side_effect=lambda **kwargs: SDKGroq(
                            **kwargs,
                            http_client=http_client,
                        ),
                    ):
                        client = GroqClient(
                            api_key="gsk_test_key",
                            model="llama-3.3-70b-versatile",
                            max_retries=1,
                        )

                        with self.assertRaises(expected_error):
                            client.generate("Hello")

                    self.assertEqual(calls, 1)

                finally:
                    http_client.close()

        
    def test_combined_retry_budget_is_four_requests(self):
        calls = 0

        responses = [
            httpx.Response(
                503,
                json={"error": {"message": "Temporary error."}},
            ),
            completion_response("not valid json"),
            httpx.Response(
                503,
                json={"error": {"message": "Temporary error."}},
            ),
            completion_response('{"success": true}'),
        ]

        def handler(request):
            nonlocal calls
            response = responses[calls]
            calls += 1
            return response

        http_client = httpx.Client(
            transport=httpx.MockTransport(handler)
        )

        try:
            with patch(
                "classbuild.llm.groq_client.Groq",
                side_effect=lambda **kwargs: SDKGroq(
                    **kwargs,
                    http_client=http_client,
                ),
            ):
                client = GroqClient(
                    api_key="gsk_test_key",
                    model="llama-3.3-70b-versatile",
                    max_retries=1,
                )

                result = request_structured_json(
                    client,
                    prompt="Return a JSON object.",
                    schema={
                        "type": "object",
                        "properties": {
                            "success": {"type": "boolean"}
                        },
                        "required": ["success"],
                    },
                    schema_name="test_response",
                    system_prompts=[
                        "Return valid JSON.",
                        "Try again and return valid JSON.",
                    ],
                    max_completion_tokens=100,
                    reasoning_effort="low",
                )

            self.assertEqual(result, {"success": True})
            self.assertEqual(calls, 4)

        finally:
            http_client.close()
    def test_timeout_error_has_clear_message(self):
        def handler(request):
            raise httpx.ReadTimeout("Request timed out.")

        http_client = httpx.Client(
            transport=httpx.MockTransport(handler)
        )

        try:
            with patch(
                "classbuild.llm.groq_client.Groq",
                side_effect=lambda **kwargs: SDKGroq(
                    **kwargs,
                    http_client=http_client,
                ),
            ):
                client = GroqClient(
                    api_key="gsk_test_key",
                    model="llama-3.3-70b-versatile",
                    max_retries=0,
                )

                from classbuild.llm.exceptions import GroqTimeoutError

                with self.assertRaises(GroqTimeoutError) as context:
                    client.generate("Hello")

                self.assertIn("timed out", str(context.exception).lower())

        finally:
            http_client.close()
class SecretRedactionTests(unittest.TestCase):

    def test_api_key_is_redacted(self):
        message = "Authentication failed: gsk_123456789abcdef"

        result = redact_secrets(message)

        self.assertNotIn("gsk_123456789abcdef", result)
        self.assertIn("[redacted]", result)

if __name__ == "__main__":
    unittest.main()
