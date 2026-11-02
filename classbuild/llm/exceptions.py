class GroqClientError(Exception):
    """Base exception for Groq client errors."""

class MissingAPIKeyError(GroqClientError):
    """Raised when GROQ_API_KEY is missing."""

class AuthenticationError(GroqClientError):
    """Raised when the API key is invalid or unauthorized."""

class ModelNotFoundError(GroqClientError):
    """Raised when the requested model is not found."""

class RateLimitError(GroqClientError):
    """Raised when the API rate limit is exceeded."""


class GroqTimeoutError(GroqClientError):
    """Raised when the request exceeds the timeout."""


class GroqConnectionError(GroqClientError):
    """Raised when Groq cannot be reached."""


class GroqServerError(GroqClientError):
    """Raised when Groq encounters a server error."""


class EmptyResponseError(GroqClientError):
    """Raised when Groq returns no text."""


class InvalidJSONError(GroqClientError):
    """Raised when JSON generation fails."""

    def __init__(
        self,
        message,
        category=None,
        finish_reason=None,
        failed_generation=None,
    ):
        super().__init__(message)
        self.category = category
        self.finish_reason = finish_reason
        self.failed_generation = failed_generation


class GroqAPIError(GroqClientError):
    """Raised for other Groq API errors."""
