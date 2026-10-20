import json
from dataclasses import replace
from types import SimpleNamespace

import fakeredis
from fastapi.testclient import TestClient
from google.adk.events import Event, EventActions
from google.genai import types
import pytest

import cloud_server
from config import get_settings
from rate_limit import RateLimiter


@pytest.fixture
def cloud(monkeypatch):
    client = fakeredis.FakeRedis(decode_responses=True)
    rate = RateLimiter(client, 60)
    monkeypatch.setattr(cloud_server, "get_limiter", lambda: rate)

    class FakeRunner:
        def __init__(self, **kwargs):
            self.service = kwargs["session_service"]

        async def run_async(self, *, user_id, session_id, new_message, **kwargs):
            session = await self.service.get_session(app_name="ecommerce_agent", user_id=user_id, session_id=session_id)
            await self.service.append_event(session, Event(author="user", content=new_message))
            event = Event(author="catalog_agent", content=types.Content(role="model", parts=[types.Part(text="Saved a demo cart.")]),
                          actions=EventActions(state_delta={"item": "Pixel 9", "quantity": "2", "price": 70000, "total": 140000}))
            await self.service.append_event(session, event)
            yield event

    monkeypatch.setattr(cloud_server, "Runner", FakeRunner)
    return client


def test_public_routes_and_no_developer_console(cloud):
    with TestClient(cloud_server.create_app()) as c:
        assert c.get("/").status_code == 200
        assert c.get("/assets/app.js").status_code == 200
        assert c.get("/dev-ui/").status_code == 404
        assert c.get("/apps/ecommerce_agent/users/user/sessions").status_code == 404
        assert c.get("/ready").json()["sessions"] == "redis"
        assert "frame-ancestors 'none'" in c.get("/").headers["Content-Security-Policy"]


def test_cloud_session_persists_between_app_instances_and_isolates_visitors(cloud):
    with TestClient(cloud_server.create_app()) as first:
        assert first.get("/api/session").json()["messages"] == []
        token = first.cookies.get(cloud_server.COOKIE)
        response = first.post("/api/chat", json={"message": "Add two Pixel 9 phones."})
        assert response.status_code == 200
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert events[-1]["type"] == "done"
        assert events[-1]["cart"]["total"] == 140000
        assert cloud.ttl(cloud_server.session_key(token)) > 0
    with TestClient(cloud_server.create_app()) as restored:
        restored.cookies.set(cloud_server.COOKIE, token)
        saved = restored.get("/api/session").json()
        assert saved["cart"]["total"] == 140000
        assert saved["messages"][0]["text"] == "Add two Pixel 9 phones."
    with TestClient(cloud_server.create_app()) as stranger:
        assert stranger.get("/api/session").json()["cart"] == {}


def test_cloud_rejects_cross_origin_and_invalid_messages(cloud):
    with TestClient(cloud_server.create_app()) as c:
        assert c.post("/api/chat", json={"message": "hello"}, headers={"origin": "https://evil.example"}).status_code == 403
        assert c.post("/api/chat", json={"message": "x" * 1501}).status_code == 422
        assert c.post("/api/chat", json={"message": "  "}).status_code == 422
        assert c.post("/api/chat", json={"message": "hello", "session_id": "someone-else"}).status_code == 422


def test_cloud_request_quota(cloud, monkeypatch):
    monkeypatch.setattr(cloud_server, "get_settings", lambda: replace(get_settings(), request_limit=1))
    with TestClient(cloud_server.create_app()) as c:
        assert c.post("/api/chat", json={"message": "hello"}).status_code == 200
        response = c.post("/api/chat", json={"message": "again"})
        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0


def test_cloud_session_lock_and_reset(cloud):
    with TestClient(cloud_server.create_app()) as c:
        c.get("/api/session")
        identity = c.cookies.get(cloud_server.COOKIE)
        key = cloud_server.session_key(identity)
        cloud.set(key + ":lock", "someone-running", ex=150)
        assert c.post("/api/chat", json={"message": "hello"}).status_code == 409
        c.post("/api/reset")
        assert c.cookies.get(cloud_server.COOKIE) != identity
        assert c.get("/api/session").json()["messages"] == []


def test_forwarded_ip_trusted_only_on_vercel(monkeypatch):
    request = SimpleNamespace(headers={"x-forwarded-for": "203.0.113.8"}, client=SimpleNamespace(host="127.0.0.1"))
    monkeypatch.delenv("VERCEL", raising=False)
    assert cloud_server.client_identity(request) == "127.0.0.1"
    monkeypatch.setenv("VERCEL", "1")
    assert cloud_server.client_identity(request) == "203.0.113.8"
