# ADK Shopping Assistant

**Live demo: [adk-shopping-assistant.vercel.app](https://adk-shopping-assistant.vercel.app)**

A conversational shopping demo built with **Google Agent Development Kit (ADK)**, **OpenAI GPT-4o mini**, and **Redis**. Four specialized agents guide a shopper from profile collection to a validated cart, shipping details, and an order summary, sharing state throughout the conversation.

The project includes an ADK browser interface, a FastAPI server, Redis rate limiting, persistent local sessions, and automated tests.

## Hosted application

The Vercel deployment uses a dedicated public chat interface, preserving the same four agents and catalog. The ADK developer console remains available only through the original local server. Hosted conversations use opaque, HTTP-only browser cookies and persist in a dedicated Redis database for 24 hours after the last completed chat turn. A fresh chat receives a new identity; another visitor cannot list or choose someone else's session.

The root `app.py` exports `ADK_Shopping/cloud_server.py` for Vercel's Python/FastAPI runtime. The original `ADK_Shopping/server.py` and `start.ps1` continue to provide the local ADK development UI and SQLite sessions. No running desktop or local Docker instance is needed by the hosted app.

For Vercel, import this repository at its root, select FastAPI, and configure server-side production variables `OPENAI_API_KEY`, `LLM_MODEL`, `REDIS_URL`, and `RATE_LIMIT_ENABLED`. Use a hosted TLS Redis URL (`rediss://...`), not the local Docker address. `PUBLIC_DAILY_CHAT_LIMIT` defaults to 300 submissions across visitors per rolling 24-hour counter window; the original per-IP request and shared model-call limits also apply. The deployment's credentials are not included in this repository.

Public endpoints are `/`, `/assets/*`, `/api/session`, `/api/chat`, `/api/reset`, `/health`, and `/ready`. The hosted application does not expose the developer console or ADK session-management APIs. Chat replies use server-sent events, same-origin request checks, per-conversation locks, and plain-text rendering of model output.

To run the hosted interface locally using your configured Redis connection:

```powershell
cd ADK_Shopping
.\.venv\Scripts\python.exe -X utf8 -m uvicorn cloud_server:app --host 127.0.0.1 --port 8002 --no-proxy-headers
```

To verify a deployment with synthetic data and real model calls:

```powershell
.\.venv\Scripts\python.exe -X utf8 -u scripts\verify_cloud.py https://adk-shopping-assistant.vercel.app
```

## What it does

- Collects and validates a shopper's name, email, and mobile number.
- Offers a fixed demo catalog of smartphones, laptops, and headphones.
- Validates product names, categories, quantities, and unit prices before saving a cart.
- Calculates totals in Python rather than asking the model to calculate them.
- Collects a shipping address and presents a summary from saved session data.
- Streams assistant responses through the ADK development UI.
- Limits chat requests and model calls using atomic Redis counters.
- Preserves session history and state across local server restarts.

**Scope:** this is an educational demo with illustrative prices and one product line per cart. Payments, actual order placement, live inventory, and order tracking are not implemented.

## Architecture

```mermaid
flowchart LR
    U[Shopper / ADK Web UI] --> S[FastAPI server]
    S --> R[Redis request quota]
    S --> E[Ecommerce agent]
    E --> C[Catalog agent]
    C --> X[Checkout agent]
    X --> O[Order summary agent]
    E -. shared session state .-> DB[(Local SQLite)]
    C -.-> DB
    X -.-> DB
    O -. reads .-> DB
    E --> M[Shared model configuration and call quota]
    C --> M
    X --> M
    O --> M
    M --> R
    M --> API[OpenAI GPT-4o mini]
```

| Agent | Responsibility | Tool |
| --- | --- | --- |
| `ecommerce_agent` | Collect the profile and route shopping requests | `save_user_info` |
| `catalog_agent` | Explain the catalog and validate the cart | `save_cart` |
| `checkout_agent` | Collect and save the shipping address | `save_shipping_address` |
| `order_summary_agent` | Present saved information without changing it | Read-only |

All four agents use the model selected by `LLM_MODEL` through ADK's LiteLLM adapter. Redis counters are shared across agents and server processes; SQLite stores the local conversation state.

## Prerequisites

- Python **3.12** (the locally tested version).
- Docker Desktop on Windows, or Docker Engine with Compose on Linux/macOS, for the included local Redis service.
- An OpenAI API key with access to `gpt-4o-mini` and available API quota.
- Git to clone this repository.

## Quick start: Windows PowerShell

```powershell
git clone https://github.com/harshgavandit/adk-shopping-assistant.git
cd adk-shopping-assistant\ADK_Shopping

py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Edit `.env` and replace `OPENAI_API_KEY=replace-with-your-openai-key` with your own key. Keep `LLM_MODEL=gpt-4o-mini` to use the tested model. Start Docker Desktop, then run:

```powershell
.\start.ps1
```

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** and select `ecommerce_agent`. The startup script starts the dedicated Redis container, waits for its health check, and launches the server. Use `.\start.ps1 -Port 8001` if port 8000 is occupied.

Runtime-only installation can use `requirements.txt`; `requirements-dev.txt` also installs the test dependencies. Direct dependency versions are pinned.

## Linux/macOS startup

These are the equivalent commands; the interactive local verification recorded for this project was performed on Windows.

```bash
git clone https://github.com/harshgavandit/adk-shopping-assistant.git
cd adk-shopping-assistant/ADK_Shopping
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
# Edit .env and supply your own OpenAI key.
docker compose up -d --wait redis
python -m uvicorn server:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

## Configuration

Use [ADK_Shopping/.env.example](ADK_Shopping/.env.example) as the template. The app loads `.env` from its own directory; process environment variables take precedence. Restart the server after changing configuration.

| Variable | Purpose | Default/example |
| --- | --- | --- |
| `OPENAI_API_KEY` | Your OpenAI project key | Required; never committed |
| `LLM_MODEL` | OpenAI model name | `gpt-4o-mini` |
| `REDIS_URL` | Redis connection string | `redis://127.0.0.1:6381/0` |
| `RATE_LIMIT_ENABLED` | Enable Redis protection | `true` |
| `RATE_LIMIT_REQUESTS` | Chat HTTP requests per client IP per window | `20` |
| `RATE_LIMIT_WINDOW_SECONDS` | Counter lifetime from the first request | `60` |
| `LLM_RATE_LIMIT_REQUESTS` | Shared model calls per window | `120` |
| `LLM_TIMEOUT_SECONDS` | Provider request timeout | `30` |
| `LLM_MAX_CALLS` | Maximum model calls in one server invocation | `12` |

The included Redis service binds to **`127.0.0.1:6381`** under Compose project `adk-shopping`. It is intended for local development and needs no hosted credentials. For a hosted Redis service, set the provider's `rediss://username:password@hostname:port/0` URL and start Uvicorn directly instead of using the local Redis startup script.

## Example conversation

1. Tell the assistant you want to shop. Supply a name, email, and mobile number when asked.
2. Browse smartphones and select **two Pixel 9 phones**.
3. Proceed to checkout and provide a complete shipping address.
4. Ask for the order summary.

The saved demo cart contains a unit price of **INR 70,000**, quantity **2**, and a total of **INR 140,000**. The summary includes those values and the saved shipping address. A new product selection replaces the current single product line.

## Rate limiting and failure behavior

`server.py` protects both `POST /run` and `POST /run_sse` before the agent starts:

- Requests are counted by the socket client IP. Forwarded headers and user-supplied IDs do not determine the quota.
- Accepted requests include `X-RateLimit-Limit` and `X-RateLimit-Remaining` headers.
- Exhausted quotas return **HTTP 429** with `Retry-After`.
- An unavailable Redis connection returns **HTTP 503** and blocks the model call.
- Every agent also checks a shared model-call quota before each provider request, including tool continuations and handoffs. A blocked call returns a clear assistant message.

A Redis Lua script increments the counter and sets its expiry atomically. Counter keys hash the identity and do not contain names, emails, mobile numbers, or addresses. The algorithm uses a fixed window beginning at the first request; it does not implement a token-per-minute or concurrent-request limit.

Provider authentication, quota, and service errors produce safe messages without exposing exception details or credentials.

## Verification

Run from `ADK_Shopping`:

```powershell
# Automated tests: use a test key and fake Redis; no paid provider calls.
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -m pip check

# Live provider completion and Redis ping; uses your configured key.
.\.venv\Scripts\python.exe -X utf8 scripts\check_connections.py

# With the server running: real agent flow, SSE, saved state and rate limits.
# Uses OpenAI tokens and synthetic customer data.
.\.venv\Scripts\python.exe -X utf8 -u scripts\verify_live.py
```

On Linux/macOS, use `python` in the activated virtual environment. The live verifier writes local evidence under `ADK_Shopping/output/`, which is ignored by Git. It uses a separate loopback client IP for HTTP quota tests; allow the configured rate-limit window to expire before repeating them.

The recorded local verification on **14 October 2026** included **26 passing automated tests**, a complete conversation through all four agents, streamed summaries, real Redis quota rejection and recovery, browser checkout, and session persistence after restart. See [docs/VERIFICATION.md](docs/VERIFICATION.md) for the scope and limits of these results.

GitHub Actions runs the automated tests and dependency check on pushes and pull requests. Live OpenAI checks are intentionally manual and need your own local configuration.

## Health endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | App liveness, selected model, and rate-limit setting |
| `GET /ready` | Redis connectivity; HTTP 503 when unavailable |
| `GET /list-apps` | Lists the supported `ecommerce_agent` entry point |

Readiness does not make a paid provider call or claim OpenAI availability. Use `scripts/check_connections.py` for a real provider check.

## Project structure

```text
.
├── README.md
├── .github/workflows/tests.yml
├── docs/VERIFICATION.md
└── ADK_Shopping/
    ├── .env.example
    ├── catalog.py
    ├── config.py
    ├── model_config.py
    ├── rate_limit.py
    ├── server.py
    ├── compose.yaml
    ├── start.ps1
    ├── requirements.txt
    ├── requirements-dev.txt
    ├── ecommerce_agent/
    ├── catalog_agent/
    ├── checkout_agent/
    ├── order_summary_agent/
    ├── scripts/
    ├── tests/
    └── DOCUMENTATION.pdf
```

The original PDF describes the earlier Gemini-based demo. The root README and [application guide](ADK_Shopping/README.md) describe the current OpenAI and Redis integration.

## Local operation and troubleshooting

- **Redis unavailable:** start Docker Desktop and run `docker compose -f compose.yaml up -d --wait redis` from the app directory. Check that port 6381 is free.
- **OpenAI authentication or quota error:** check your local key, project permissions, model access, and API usage. Do not paste credentials into issues or commit them.
- **Rate limit reached:** wait for the indicated `Retry-After` period. Limits are configurable in `.env`.
- **Unexpected configuration:** check process environment variables, which override `.env`, then restart the server.
- **Port 8000 occupied:** choose another port with `start.ps1 -Port 8001` or Uvicorn's `--port` option.

Stop the server with `Ctrl+C`. Stop this project's local Redis with:

```powershell
docker compose -f compose.yaml down
```

This uses the ADK development UI, whose APIs and developer features have no application login. Keep the server bound to loopback for local use. Authentication and deployment controls are required before public hosting. `.env`, virtual environments, SQLite session data, local reports, caches, and extracted macOS metadata are excluded by `.gitignore`.

## References

- [Google ADK documentation](https://adk.dev/)
- [ADK LiteLLM adapter](https://adk.dev/agents/models/litellm/)
- [OpenAI GPT-4o mini](https://developers.openai.com/api/docs/models/gpt-4o-mini)
- [Redis atomic counter pattern](https://redis.io/docs/latest/commands/incr/)
