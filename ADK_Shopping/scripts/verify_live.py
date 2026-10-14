"""Verify real ADK tools and handoffs with synthetic data; uses OpenAI tokens."""
import argparse
import json
from pathlib import Path
import time
import uuid

import httpx
import redis

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import PROJECT_DIR, get_settings
from rate_limit import RateLimiter, RateLimitExceeded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    report = {"model": get_settings().model, "checks": {}, "turns": []}
    user = "verification-" + uuid.uuid4().hex[:8]
    with httpx.Client(base_url=args.base_url, timeout=90) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").json()["redis"] == "connected"
        assert client.get("/list-apps").json() == ["ecommerce_agent"]
        report["checks"]["health_and_redis"] = "PASS"
        created = client.post(f"/apps/ecommerce_agent/users/{user}/sessions", json={})
        created.raise_for_status()
        session_id = created.json()["id"]
        session_path = f"/apps/ecommerce_agent/users/{user}/sessions/{session_id}"
        report["session_id"] = session_id
        report["user_id"] = user
        messages = [
            "Hi, I want to shop.",
            "My name is Demo Shopper.",
            "My email is demo@example.com.",
            "My mobile number is +919876543210. I want to browse smartphones.",
            "Add 2 Pixel 9 smartphones to my cart.",
            "Yes, proceed to checkout.",
            "Ship to 123 Demo Road, Mumbai, Maharashtra, 400001. Please show my order summary now.",
        ]
        tools, authors = set(), set()
        for index, message in enumerate(messages):
            payload = {"app_name": "ecommerce_agent", "user_id": user, "session_id": session_id,
                       "new_message": {"role": "user", "parts": [{"text": message}]}}
            streaming = index == len(messages) - 1
            payload["streaming"] = streaming
            response = client.post("/run_sse" if streaming else "/run", json=payload)
            response.raise_for_status()
            if streaming:
                events = [json.loads(line[5:].strip()) for line in response.text.splitlines() if line.startswith("data:")]
            else:
                events = response.json()
            text_parts = []
            for event in events:
                assert "error" not in event, "Agent emitted an error"
                authors.add(event.get("author"))
                for part in (event.get("content") or {}).get("parts", []):
                    if "functionCall" in part:
                        tools.add(part["functionCall"]["name"])
                    if part.get("text") and not event.get("partial"):
                        text_parts.append(part["text"])
            report["turns"].append({"user": message, "response": "".join(text_parts), "streaming": streaming})
            print(f"Turn {index + 1}: HTTP {response.status_code}; authors={sorted(a for a in authors if a)}", flush=True)
        saved = client.get(session_path).json()
        state = saved["state"]
        expected = {"name": "Demo Shopper", "email": "demo@example.com", "mobile": "+919876543210",
                    "item": "Pixel 9", "quantity": "2", "price": 70000, "total": 140000,
                    "shipping_address": "123 Demo Road, Mumbai, Maharashtra, 400001"}
        assert all(state.get(k) == v for k, v in expected.items()), f"Missing or incorrect state fields: {[k for k,v in expected.items() if state.get(k)!=v]}"
        assert {"save_user_info", "save_cart", "save_shipping_address", "transfer_to_agent"} <= tools
        assert {"ecommerce_agent", "catalog_agent", "checkout_agent", "order_summary_agent"} <= authors
        summary = report["turns"][-1]["response"].replace(",", "")
        assert "140000" in summary and "Pixel 9" in summary
        report["checks"]["live_shopping_and_streaming"] = "PASS"
        report["tools"] = sorted(tools)
        report["agents"] = sorted(a for a in authors if a)
        report["state"] = {k: state[k] for k in expected}
        report["checks"]["session_state_saved"] = "PASS"

    # Use a separate loopback client IP so verification does not consume the UI's quota.
    with httpx.Client(base_url=args.base_url, transport=httpx.HTTPTransport(local_address="127.0.0.2"), timeout=10) as quota_client:
        responses = [quota_client.post("/run", json={}) for _ in range(get_settings().request_limit + 1)]
        assert responses[0].status_code == 422  # Invalid payload never calls a model.
        assert responses[-1].status_code == 429
        assert int(responses[-1].headers["Retry-After"]) > 0
        streamed = quota_client.post("/run_sse", json={})
        assert streamed.status_code == 429
        report["checks"]["http_and_sse_429"] = "PASS"

    # A unique expiring key in this project's dedicated Redis tests real recovery.
    redis_client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    limiter = RateLimiter(redis_client, 2)
    identity = uuid.uuid4().hex
    assert limiter.check_sync("verification", identity, 2).remaining == 1
    assert limiter.check_sync("verification", identity, 2).remaining == 0
    try:
        limiter.check_sync("verification", identity, 2)
    except RateLimitExceeded as exc:
        assert 1 <= exc.retry_after <= 2
    else:
        raise AssertionError("Redis did not enforce the quota")
    time.sleep(2.1)
    assert limiter.check_sync("verification", identity, 2).remaining == 1
    report["checks"]["real_redis_quota_and_recovery"] = "PASS"
    output = PROJECT_DIR / "output"
    output.mkdir(exist_ok=True)
    (output / "live-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["checks"], indent=2))


if __name__ == "__main__":
    main()
