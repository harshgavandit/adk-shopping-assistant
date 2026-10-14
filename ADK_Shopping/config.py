"""Load this project's environment regardless of the launching directory."""
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env", override=False)


def positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} must be a positive integer") from None
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(repr=False)
    model: str
    redis_url: str = field(repr=False)
    rate_limit_enabled: bool
    request_limit: int
    window_seconds: int
    llm_limit: int
    timeout_seconds: int
    max_llm_calls: int


@lru_cache
def get_settings() -> Settings:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key or key == "replace-with-your-openai-key":
        raise ValueError("Set OPENAI_API_KEY in ADK_Shopping/.env")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
    model = model.removeprefix("openai/")
    if not model or "/" in model:
        raise ValueError("LLM_MODEL must be an OpenAI model name")
    enabled = os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower()
    if enabled not in {"true", "false"}:
        raise ValueError("RATE_LIMIT_ENABLED must be true or false")
    url = os.getenv("REDIS_URL", "").strip()
    if enabled == "true":
        try:
            parsed = urlsplit(url)
            valid = parsed.scheme in {"redis", "rediss"} and parsed.hostname and parsed.port
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("Set REDIS_URL to redis://host:port/db or rediss://user:password@host:port/db")
    return Settings(
        key, model, url, enabled == "true",
        positive_int("RATE_LIMIT_REQUESTS", 20),
        positive_int("RATE_LIMIT_WINDOW_SECONDS", 60),
        positive_int("LLM_RATE_LIMIT_REQUESTS", 120),
        positive_int("LLM_TIMEOUT_SECONDS", 30),
        positive_int("LLM_MAX_CALLS", 12),
    )
