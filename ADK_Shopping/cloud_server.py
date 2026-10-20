"""Public chat API: opaque browser sessions persisted in Redis, no developer routes."""
import asyncio
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.sessions.session import Session
from google.genai import types
from pydantic import BaseModel, Field, ConfigDict
import redis

from config import get_settings
from ecommerce_agent.agent import root_agent
from rate_limit import get_limiter, RateLimiter, RateLimitExceeded, RateLimitUnavailable

APP_NAME = "ecommerce_agent"
COOKIE = "shopping_session"
TTL = 86400
WEB = Path(__file__).resolve().parent / "web"
UNLOCK = "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('DEL',KEYS[1]) else return 0 end"


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=1500)


def session_identity(request):
    value = request.cookies.get(COOKIE, "")
    return value if re.fullmatch(r"[a-f0-9]{64}", value) else secrets.token_hex(32)


def session_key(identity):
    return "adk-shopping:session:" + hashlib.sha256(identity.encode()).hexdigest()


def client_identity(request):
    # This header is overwritten by Vercel, and is trusted only on that platform.
    candidate = request.headers.get("x-forwarded-for", "").split(",")[0].strip() if os.getenv("VERCEL") == "1" else ""
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return request.client.host if request.client else "local"


def public_snapshot(session):
    messages = []
    if session:
        for event in session.events:
            if event.partial or not event.content:
                continue
            text = "".join(part.text or "" for part in event.content.parts or [] if not part.function_call and not part.function_response)
            if text:
                messages.append({"role": "user" if event.author == "user" else "assistant", "text": text})
    state = session.state if session else {}
    cart = {key: state[key] for key in ("item", "quantity", "price", "total") if key in state}
    if state.get("shipping_address"):
        stage = "Summary"
    elif state.get("item"):
        stage = "Checkout"
    elif state.get("name"):
        stage = "Catalog"
    else:
        stage = "Welcome"
    return {"messages": messages[-60:], "cart": cart, "stage": stage}


def event_data(kind, **values):
    return "data: " + json.dumps({"type": kind, **values}, ensure_ascii=False) + "\n\n"


def create_app():
    settings = get_settings()
    app = FastAPI(title="ADK Shopping", docs_url=None, redoc_url=None, openapi_url=None)

    def browser_cookie(response, request, identity):
        response.set_cookie(COOKIE, identity, max_age=TTL, httponly=True,
                            secure=os.getenv("VERCEL") == "1" or request.url.scheme == "https", samesite="lax")
        return response

    @app.middleware("http")
    async def browser_boundary(request, call_next):
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
            try:
                if int(request.headers.get("content-length", "0")) > 12000:
                    return JSONResponse({"detail": "Message is too large."}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid request."}, status_code=400)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    @app.exception_handler(redis.RedisError)
    async def storage_failure(request, exc):
        return JSONResponse({"detail": "Chat storage is temporarily unavailable. Please try again shortly."}, status_code=503)

    @app.get("/")
    async def home():
        return FileResponse(WEB / "index.html")

    @app.get("/health")
    async def health():
        return {"status": "ok", "model": settings.model, "rate_limit_enabled": settings.rate_limit_enabled}

    @app.get("/ready")
    async def ready():
        try:
            await get_limiter().ping()
        except RateLimitUnavailable:
            return JSONResponse({"status": "not_ready", "redis": "unavailable"}, status_code=503)
        return {"status": "ready", "redis": "connected", "sessions": "redis", "retention_hours": 24}

    @app.get("/api/session")
    async def current_session(request: Request):
        identity = session_identity(request)
        saved = await asyncio.to_thread(get_limiter().client.get, session_key(identity))
        session = Session.model_validate_json(saved) if saved else None
        return browser_cookie(JSONResponse(public_snapshot(session)), request, identity)

    @app.post("/api/reset")
    async def reset(request: Request):
        identity = session_identity(request)
        # Start a fresh, unguessable conversation; the old session expires automatically.
        response = JSONResponse(public_snapshot(None))
        return browser_cookie(response, request, secrets.token_hex(32))

    @app.post("/api/chat")
    async def chat(payload: ChatInput, request: Request):
        if not payload.message.strip():
            raise HTTPException(422, "Enter a message.")
        limiter = get_limiter()
        identity = session_identity(request)
        try:
            await limiter.check("cloud-http", client_identity(request), settings.request_limit)
            # Shared across visitors, limiting the public demo's daily chat invocations.
            await RateLimiter(limiter.client, 86400).check("cloud-daily", "demo", int(os.getenv("PUBLIC_DAILY_CHAT_LIMIT", "300")))
        except RateLimitExceeded as exc:
            return JSONResponse({"detail": str(exc)}, status_code=429, headers={"Retry-After": str(exc.retry_after)})
        except RateLimitUnavailable:
            return JSONResponse({"detail": "Chat is temporarily unavailable. Please try again shortly."}, status_code=503)
        key = session_key(identity)
        lock_key, lock_token = key + ":lock", secrets.token_hex(16)
        acquired = await asyncio.to_thread(limiter.client.set, lock_key, lock_token, nx=True, ex=150)
        if not acquired:
            raise HTTPException(409, "A reply is already in progress. Please wait for it to finish.")
        try:
            stored = await asyncio.to_thread(limiter.client.get, key)
            service = InMemorySessionService()
            if stored:
                restored = Session.model_validate_json(stored)
                service.sessions = {APP_NAME: {identity: {identity: restored}}}
            else:
                await service.create_session(app_name=APP_NAME, user_id=identity, session_id=identity)
        except Exception:
            await asyncio.to_thread(limiter.client.eval, UNLOCK, 1, lock_key, lock_token)
            raise

        async def reply():
            text = ""
            authors = set()
            try:
                runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=service)
                async with asyncio.timeout(100):
                    async for event in runner.run_async(
                        user_id=identity, session_id=identity,
                        new_message=types.Content(role="user", parts=[types.Part(text=payload.message.strip())]),
                        run_config=RunConfig(streaming_mode=StreamingMode.SSE, max_llm_calls=settings.max_llm_calls),
                    ):
                        if event.author != "user":
                            authors.add(event.author)
                        if event.content and not event.partial:
                            chunk = "".join(part.text or "" for part in event.content.parts or [] if not part.function_call and not part.function_response)
                            if chunk:
                                text += ("\n\n" if text else "") + chunk
                                yield event_data("message", text=text, agent=event.author)
                saved = await service.get_session(app_name=APP_NAME, user_id=identity, session_id=identity)
                await asyncio.to_thread(limiter.client.set, key, saved.model_dump_json(), ex=TTL)
                yield event_data("done", **public_snapshot(saved), agents=sorted(authors))
            except Exception:
                # Never put provider exceptions, URLs, or credentials in the event stream.
                yield event_data("error", message="The reply could not be completed. Please try again shortly.")
            finally:
                await asyncio.to_thread(limiter.client.eval, UNLOCK, 1, lock_key, lock_token)

        response = StreamingResponse(reply(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})
        return browser_cookie(response, request, identity)

    app.mount("/assets", StaticFiles(directory=WEB), name="assets")
    return app


app = create_app()
