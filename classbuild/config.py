
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "openai/gpt-oss-20b"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_RETRIES = 1
MAX_ALLOWED_RETRIES = 3


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    groq_model: str
    request_timeout_seconds: int
    max_retries: int


def get_settings() -> Settings:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "").strip()
    timeout = os.getenv("GROQ_TIMEOUT_SECONDS", "").strip()
    retries = os.getenv("GROQ_MAX_RETRIES", "").strip()

    if not model:
        model = DEFAULT_MODEL

    try:
        timeout_seconds = int(timeout) if timeout else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        timeout_seconds = DEFAULT_TIMEOUT_SECONDS

    try:
        max_retries = int(retries) if retries else DEFAULT_MAX_RETRIES
    except ValueError:
        max_retries = DEFAULT_MAX_RETRIES

    max_retries = max(0, min(max_retries, MAX_ALLOWED_RETRIES))

    return Settings(
        groq_api_key=api_key,
        groq_model=model,
        request_timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )
