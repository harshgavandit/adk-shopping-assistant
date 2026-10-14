"""ADK's development web UI/API with request limits and durable local sessions."""
from fastapi.responses import JSONResponse
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.cli.utils.base_agent_loader import BaseAgentLoader

from config import PROJECT_DIR, get_settings
from ecommerce_agent.agent import root_agent
from rate_limit import get_limiter, RateLimitExceeded, RateLimitUnavailable


class ShoppingAgentLoader(BaseAgentLoader):
    def list_agents(self):
        return ["ecommerce_agent"]

    def load_agent(self, agent_name):
        if agent_name != "ecommerce_agent":
            raise ValueError("Unknown shopping app")
        return root_agent


def create_app():
    settings = get_settings()
    app = get_fast_api_app(
        agents_dir=str(PROJECT_DIR), agent_loader=ShoppingAgentLoader(),
        web=True, bind_host="127.0.0.1", reload_agents=False,
        max_llm_calls=settings.max_llm_calls,
    )
    # ADK already registers /health. Replace it so our configuration-aware
    # handler is reachable rather than shadowed by the earlier route.
    app.router.routes[:] = [route for route in app.router.routes if getattr(route, "path", None) != "/health"]

    @app.middleware("http")
    async def limit_chat_requests(request, call_next):
        if request.method != "POST" or request.url.path not in {"/run", "/run_sse"}:
            return await call_next(request)
        decision = None
        if settings.rate_limit_enabled:
            # IP comes from the socket, never an untrusted body or forwarded header.
            identity = request.client.host if request.client else "local"
            try:
                decision = await get_limiter().check("http", identity, settings.request_limit)
            except RateLimitExceeded as exc:
                return JSONResponse(
                    {"error": "rate_limit_exceeded", "retry_after": exc.retry_after},
                    status_code=429, headers={"Retry-After": str(exc.retry_after)},
                )
            except RateLimitUnavailable:
                return JSONResponse({"error": "rate_limit_unavailable"}, status_code=503)
        response = await call_next(request)
        if decision:
            response.headers["X-RateLimit-Limit"] = str(decision.limit)
            response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        return response

    @app.get("/health")
    async def health():
        return {"status": "ok", "model": settings.model, "rate_limit_enabled": settings.rate_limit_enabled}

    @app.get("/ready")
    async def ready():
        if settings.rate_limit_enabled:
            try:
                await get_limiter().ping()
            except RateLimitUnavailable:
                return JSONResponse({"status": "not_ready", "redis": "unavailable"}, status_code=503)
        return {"status": "ready", "redis": "connected" if settings.rate_limit_enabled else "disabled"}

    return app


app = create_app()
