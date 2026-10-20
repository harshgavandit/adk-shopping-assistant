"""Verify the deployed public app with synthetic data. Makes real model requests."""
import argparse
import json
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    args = parser.parse_args()
    checks = {}
    turns = []
    with httpx.Client(base_url=args.base_url, timeout=120, follow_redirects=True) as client:
        assert client.get("/").status_code == 200
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/health").json()["model"] == "gpt-4o-mini"
        assert client.get("/ready").json()["sessions"] == "redis"
        assert client.get("/dev-ui/").status_code == 404
        checks["website_and_readiness"] = "PASS"
        assert client.get("/api/session").json()["messages"] == []
        messages = [
            "Hi, I want to shop.", "My name is Cloud Demo.", "My email is cloud-demo@example.com.",
            "My mobile is +919876543210. I would like to browse smartphones.",
            "Add 2 Pixel 9 smartphones to my cart.", "Yes, proceed to checkout.",
            "Ship to 123 Demo Road, Mumbai, Maharashtra, 400001. Please show my order summary now.",
        ]
        authors = set()
        for index, message in enumerate(messages):
            response = client.post("/api/chat", json={"message": message})
            assert response.status_code == 200, f"Chat HTTP {response.status_code}"
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            assert not any(event["type"] == "error" for event in events), "Streamed reply failed"
            done = next(event for event in events if event["type"] == "done")
            authors.update(done["agents"])
            turns.append({"user": message, "response": done["messages"][-1]["text"]})
            print(f"Cloud turn {index + 1}: PASS", flush=True)
        assert done["cart"] == {"item": "Pixel 9", "quantity": "2", "price": 70000, "total": 140000}
        summary = done["messages"][-1]["text"].replace(",", "")
        assert "140000" in summary and "123 Demo Road" in summary
        assert {"ecommerce_agent", "catalog_agent", "checkout_agent", "order_summary_agent"} <= authors
        checks["four_agent_shopping_flow"] = "PASS"
        checks["summary_and_cart_total"] = "PASS"
        # A new HTTP client and request restores the same session using only its cookie.
        cookies = client.cookies
    with httpx.Client(base_url=args.base_url, cookies=cookies, timeout=30) as restored:
        snapshot = restored.get("/api/session").json()
        assert snapshot["cart"]["total"] == 140000
        assert len(snapshot["messages"]) >= 14
        checks["hosted_session_recovery"] = "PASS"
    with httpx.Client(base_url=args.base_url, timeout=30) as other:
        assert other.get("/api/session").json()["messages"] == []
        checks["visitor_isolation"] = "PASS"
        assert other.post("/api/chat", json={"message": "hello"}, headers={"Origin": "https://untrusted.example"}).status_code == 403
        assert other.post("/api/chat", json={"message": "x" * 1501}).status_code == 422
        checks["origin_and_input_guards"] = "PASS"
    output = Path(__file__).resolve().parents[1] / "output"
    output.mkdir(exist_ok=True)
    report = {"url": args.base_url, "checks": checks, "agents": sorted(authors), "turns": turns}
    (output / "cloud-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
