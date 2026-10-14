"""Explicit live checks. Output contains statuses, never credential values."""
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai import AsyncOpenAI, APIConnectionError, APIStatusError
from config import get_settings
from rate_limit import get_limiter, RateLimitUnavailable


async def main():
    settings = get_settings()
    result = {"model": settings.model}
    if settings.rate_limit_enabled:
        try:
            await get_limiter().ping()
            result["redis"] = "PASS"
        except RateLimitUnavailable:
            result["redis"] = "FAIL: unavailable"
    else:
        result["redis"] = "DISABLED"
    try:
        async with AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.timeout_seconds, max_retries=0) as client:
            response = await client.chat.completions.create(
                model=settings.model, messages=[{"role": "user", "content": "Reply with the single word OK."}],
                max_tokens=5, temperature=0,
            )
            result["openai"] = "PASS" if response.choices[0].message.content else "FAIL: empty response"
    except APIStatusError as exc:
        code = exc.body.get("code") if isinstance(exc.body, dict) else None
        # Whitelist known codes; provider error messages can contain key fragments.
        known = {"invalid_api_key", "insufficient_quota", "model_not_found", "rate_limit_exceeded"}
        result["openai"] = f"FAIL: HTTP {exc.status_code}" + (f" ({code})" if code in known else "")
    except APIConnectionError:
        result["openai"] = "FAIL: connection unavailable"
    print(json.dumps(result, indent=2))
    return 0 if result.get("redis") == "PASS" and result.get("openai") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
