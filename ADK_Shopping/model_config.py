"""One model factory and quota callback for every agent, including CLI runs."""
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from config import get_settings
from rate_limit import get_limiter, RateLimitExceeded, RateLimitUnavailable


def create_model():
    settings = get_settings()
    return LiteLlm(
        model=f"openai/{settings.model}", api_key=settings.openai_api_key,
        timeout=settings.timeout_seconds, num_retries=0, max_tokens=800,
    )


async def before_model(callback_context, llm_request):
    """Count each actual model call, including tool and handoff continuations."""
    settings = get_settings()
    if settings.rate_limit_enabled:
        try:
            await get_limiter().check("llm", "openai-project", settings.llm_limit)
        except (RateLimitExceeded, RateLimitUnavailable) as exc:
            # Returning a response stops this provider call, also in adk run/web.
            return LlmResponse(content=types.Content(
                role="model", parts=[types.Part(text=str(exc))],
            ))
    return None


async def on_model_error(callback_context, llm_request, error):
    """Report actionable provider failures without exposing exception strings."""
    status = getattr(error, "status_code", None)
    messages = {
        401: "OpenAI authentication failed. Check OPENAI_API_KEY in the local .env.",
        403: "OpenAI access was denied. Check project and model permissions.",
        404: "The configured OpenAI model is unavailable. Check LLM_MODEL and project access.",
        429: "OpenAI quota or rate limit reached. Check project usage and billing, then retry later.",
    }
    message = messages.get(status, "The model service is temporarily unavailable. Please try again later.")
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=message)]))
