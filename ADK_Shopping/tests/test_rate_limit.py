import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import fakeredis
import pytest
import redis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import get_settings
from rate_limit import RateLimiter, RateLimitExceeded, RateLimitUnavailable
import model_config
import server


def limiter(window=60):
    return RateLimiter(fakeredis.FakeRedis(), window)


def test_quota_ttl_and_isolation():
    rate = limiter()
    assert rate.check_sync("http", "a", 2).remaining == 1
    assert rate.check_sync("http", "a", 2).remaining == 0
    with pytest.raises(RateLimitExceeded) as exc:
        rate.check_sync("http", "a", 2)
    assert 1 <= exc.value.retry_after <= 60
    assert rate.check_sync("http", "b", 2).remaining == 1
    assert rate.check_sync("llm", "a", 2).remaining == 1
    assert all(rate.client.ttl(key) > 0 for key in rate.client.keys())


def test_atomic_concurrent_limit():
    rate = limiter()
    def request(_):
        try:
            rate.check_sync("http", "same-client", 10)
            return True
        except RateLimitExceeded:
            return False
    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sum(pool.map(request, range(40))) == 10


def test_redis_failure_is_closed_and_redacted():
    class Broken:
        def eval(self, *args):
            raise redis.ConnectionError("credential-must-not-escape")
    with pytest.raises(RateLimitUnavailable) as exc:
        RateLimiter(Broken(), 60).check_sync("http", "a", 1)
    assert "credential" not in str(exc.value)


@pytest.mark.parametrize("endpoint", ["/run", "/run_sse"])
def test_http_429_and_retry_after(monkeypatch, endpoint):
    rate = limiter()
    monkeypatch.setattr(server, "get_limiter", lambda: rate)
    monkeypatch.setattr(server, "get_settings", lambda: replace(get_settings(), request_limit=2))
    # Exercise the real middleware without spending tokens or creating sessions.
    def fake_adk(**kwargs):
        app = FastAPI()
        @app.post(endpoint)
        def run():
            return {"ok": True}
        return app
    monkeypatch.setattr(server, "get_fast_api_app", fake_adk)
    with TestClient(server.create_app()) as client:
        assert client.post(endpoint, json={}).status_code == 200
        response = client.post(endpoint, json={})
        assert response.headers["X-RateLimit-Remaining"] == "0"
        response = client.post(endpoint, json={})
        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0


def test_http_redis_outage_503(monkeypatch):
    class Broken:
        async def check(self, *args):
            raise RateLimitUnavailable()
    monkeypatch.setattr(server, "get_limiter", lambda: Broken())
    with TestClient(server.create_app()) as client:
        response = client.post("/run", json={})
        assert response.status_code == 503
        assert response.json() == {"error": "rate_limit_unavailable"}


def test_health_reports_configured_model():
    with TestClient(server.create_app(), base_url="http://127.0.0.1") as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "model": "gpt-4o-mini", "rate_limit_enabled": True}


def test_model_callback_blocks_provider(monkeypatch):
    rate = limiter()
    monkeypatch.setattr(model_config, "get_limiter", lambda: rate)
    monkeypatch.setattr(model_config, "get_settings", lambda: replace(get_settings(), llm_limit=1))
    assert asyncio.run(model_config.before_model(SimpleNamespace(), None)) is None
    response = asyncio.run(model_config.before_model(SimpleNamespace(), None))
    assert "Rate limit reached" in response.content.parts[0].text


@pytest.mark.parametrize("status,expected", [(401, "authentication failed"), (429, "quota or rate limit"), (500, "temporarily unavailable")])
def test_provider_errors_are_actionable_and_redacted(status, expected):
    error = SimpleNamespace(status_code=status, secret="must-not-escape")
    response = asyncio.run(model_config.on_model_error(None, None, error))
    assert expected in response.content.parts[0].text
    assert "must-not-escape" not in response.content.parts[0].text
