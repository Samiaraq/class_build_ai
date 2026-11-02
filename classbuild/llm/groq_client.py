
import json

from groq import (
    Groq,
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
)

from classbuild.config import get_settings
from classbuild.llm.exceptions import (
    MissingAPIKeyError,
    AuthenticationError,
    ModelNotFoundError,
    RateLimitError,
    GroqTimeoutError,
    GroqConnectionError,
    GroqServerError,
    EmptyResponseError,
    InvalidJSONError,
    GroqAPIError,
)


STRICT_SCHEMA_MODELS = {
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
}

REASONING_MODELS = {
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
}


class GroqClient:
    def __init__(self, api_key=None, model=None, timeout_seconds=None):
        settings = get_settings()

        api_key = api_key or settings.groq_api_key
        self.model = model or settings.groq_model
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.request_timeout_seconds
        )

        if not api_key:
            raise MissingAPIKeyError(
                "GROQ_API_KEY is missing. Check your .env file."
            )

        self.client = Groq(
            api_key=api_key,
            timeout=self.timeout_seconds,
        )

    def supports_strict_schema(self):
        return self.model in STRICT_SCHEMA_MODELS

    def generate(self, prompt):
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        response = self._chat(
            messages=[{"role": "user", "content": prompt}]
        )

        return self._extract_text(response)

    def generate_json(
        self,
        prompt,
        schema,
        schema_name="response",
        system_prompt=None,
        max_completion_tokens=3000,
        reasoning_effort="low",
    ):
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        if self.supports_strict_schema():
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            }
            messages = [
                {
                    "role": "system",
                    "content": system_prompt or "Return valid JSON.",
                },
                {"role": "user", "content": prompt},
            ]
        else:
            response_format = {"type": "json_object"}
            messages = [
                {
                    "role": "system",
                    "content": (
                        (system_prompt or "Return valid JSON.")
                        + "\nReturn JSON matching this JSON schema:\n"
                        + json.dumps(schema, ensure_ascii=False)
                    ),
                },
                {"role": "user", "content": prompt},
            ]

        extra = {
            "max_completion_tokens": max_completion_tokens,
        }

        if self.model in REASONING_MODELS:
            extra["reasoning_effort"] = reasoning_effort

        try:
            response = self._chat(
                messages=messages,
                response_format=response_format,
                **extra,
            )
        except APIStatusError as exc:
            self._translate_status_error(exc)

        return self._extract_json(response)

    @staticmethod
    def _extract_text(response):
        if not response.choices:
            raise EmptyResponseError("Groq returned no choices.")

        content = response.choices[0].message.content

        if not content or not content.strip():
            raise EmptyResponseError("Groq returned an empty response.")

        return content.strip()

    def _extract_json(self, response):
        if not response.choices:
            raise EmptyResponseError("Groq returned no choices.")

        choice = response.choices[0]
        content = choice.message.content
        finish_reason = choice.finish_reason

        if finish_reason == "length":
            raise InvalidJSONError(
                "Groq response was truncated.",
                category="truncated",
                finish_reason=finish_reason,
                failed_generation=content,
            )

        if not content or not content.strip():
            raise EmptyResponseError("Groq returned an empty response.")

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise InvalidJSONError(
                "Groq returned invalid JSON.",
                category="invalid_json",
                finish_reason=finish_reason,
                failed_generation=content,
            ) from exc

    def _chat(self, messages, response_format=None, **extra):
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "timeout": self.timeout_seconds,
                **extra,
            }

            if response_format is not None:
                kwargs["response_format"] = response_format

            return self.client.chat.completions.create(**kwargs)

        except APITimeoutError as exc:
            raise GroqTimeoutError(
                "The Groq request timed out."
            ) from exc

        except APIConnectionError as exc:
            raise GroqConnectionError(
                "Could not connect to Groq."
            ) from exc

        except APIStatusError as exc:
            self._translate_status_error(exc)

    def _translate_status_error(self, exc):
        status = exc.status_code
        detail = self._error_detail(exc)
        code = self._error_code(exc)
        

        if status in (401, 403):
            raise AuthenticationError(detail) from exc

        if status == 404:
            raise ModelNotFoundError(detail) from exc

        if status == 429:
            raise RateLimitError(detail) from exc

        if status in (500, 502, 503, 504):
            raise GroqServerError(detail) from exc

        if status == 400 and code == "json_validate_failed":
            raise InvalidJSONError(
                detail,
                category="json_validate_failed",
            ) from exc

        raise GroqAPIError(detail) from exc

    @staticmethod
    def _error_code(exc):

        try:
            body = exc.response.json()
        except (ValueError, AttributeError):
            body = getattr(exc, "body", None)
            print("ERROR BODY:", body)

        if not isinstance(body, dict):
            return None

        error = body.get("error", body)
        
        if isinstance(error, dict):
            return error.get("code")

        return None

    @staticmethod
    def _error_detail(exc):
        try:
            body = exc.response.json()
            error = body.get("error", {})
            if isinstance(error, dict):
                message = error.get("message")
                if message:
                    return message
        except (ValueError, AttributeError):
            pass

        return str(exc)
