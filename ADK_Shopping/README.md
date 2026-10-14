# ADK Shopping

A local demo shopping assistant built with Google ADK. Four agents share session state:

`ecommerce_agent -> catalog_agent -> checkout_agent -> order_summary_agent`

All four use the OpenAI model named by `LLM_MODEL`, through ADK's LiteLLM adapter. The configured model is `gpt-4o-mini`. This remains a demo: the catalog is illustrative, there is one product line per cart, and there are no real orders, payments, inventory checks, or tracking integrations.

## Run on Windows

Open PowerShell in the `ADK_Shopping` directory of your checkout. After creating the virtual environment and configuring `.env` as described below, start Docker Desktop and run:

```powershell
.\start.ps1
```

Open <http://127.0.0.1:8000>. The server supplies the ADK development web UI and API. The local Redis container is isolated under Compose project `adk-shopping` and bound to `127.0.0.1:6381`; other projects' Redis instances are not used. Session history and state are stored locally in `.adk/` using SQLite, and survive application restarts.

For a new checkout, use Python 3.12, install dependencies, and create your local configuration:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Edit .env to set your own OPENAI_API_KEY before starting.
```

Runtime-only installation uses `requirements.txt`. The tested direct dependency versions are pinned. Run `start.ps1` with `-Port 8001` if port 8000 is occupied.

## Configuration

Configuration is loaded from the `.env` beside `config.py`, independently of the current directory. Process environment variables take precedence; restart the server after editing `.env`.

| Variable | Purpose | Local setting |
| --- | --- | --- |
| `OPENAI_API_KEY` | OpenAI project key; required | Set privately in `.env` |
| `LLM_MODEL` | OpenAI model name | `gpt-4o-mini` |
| `REDIS_URL` | Redis connection, including hosted credentials if applicable | `redis://127.0.0.1:6381/0` |
| `RATE_LIMIT_ENABLED` | Explicitly enable/disable Redis protection | `true` |
| `RATE_LIMIT_REQUESTS` | Chat HTTP requests per client IP per window | `20` |
| `RATE_LIMIT_WINDOW_SECONDS` | Counter lifetime from the first request | `60` |
| `LLM_RATE_LIMIT_REQUESTS` | Model calls across all four agents per window | `120` |
| `LLM_TIMEOUT_SECONDS` | Provider request timeout | `30` |
| `LLM_MAX_CALLS` | Maximum model calls in one server invocation | `12` |

The OpenAI-configured agents do not require a Google API key. The included local Redis service needs no hosted credentials because it binds only to loopback. For hosted Redis, replace `REDIS_URL` with the provider's `rediss://username:password@hostname:port/0` connection string, and start the server directly rather than starting the local Redis container:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m uvicorn server:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

`.env`, SQLite session data, virtual environments, verification outputs, and extracted macOS metadata are ignored by the root `.gitignore`. `.env.example` contains no credentials. See the [repository README](../README.md) for architecture, cloning instructions, and verification scope.

## Rate limiting

`server.py` protects both `POST /run` and `POST /run_sse` before the agent starts. Requests are counted by the actual socket IP, ignoring client-supplied user IDs and forwarded headers. Successful requests return `X-RateLimit-Limit` and `X-RateLimit-Remaining`. Exhausted quotas return HTTP `429` and `Retry-After`. Redis failure returns HTTP `503`; requests do not proceed to OpenAI.

Each agent also checks a shared model-call quota before every provider call, including tool continuations and handoffs. This callback protects direct ADK CLI usage too. A blocked model call returns a clear assistant message without contacting OpenAI. Provider errors are converted to credential-safe messages. Redis Lua scripts atomically increment the counter and set its expiration; counters are shared across server processes and do not store customer details in key names. This is a fixed window beginning at the first request, not a token-per-minute or concurrent-request limit.

Use this development UI locally. The ADK API has no application login; its session APIs and developer features are intended for local use. Add authentication and deployment controls before making it publicly accessible.

## Shopping behavior

1. Supply a name, valid email, and mobile number. The root agent asks for one missing detail at a time.
2. Browse Smartphones, Laptops, or Headphones.
3. Select an item and a whole-number quantity from 1 to 99. The cart tool validates the catalog item, category, and unit price, then computes the total itself.
4. Proceed to checkout and provide a shipping address.
5. View a summary drawn only from saved state. Missing fields do not cause template errors. A new product selection replaces the single cart line.

Example: two Pixel 9 phones cost INR 140,000 in this illustrative catalog. No order is actually submitted.

## Verification

```powershell
# Unit and middleware checks; do not call OpenAI or the local Redis instance.
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -m pip check

# Minimal live provider request and Redis ping.
.\.venv\Scripts\python.exe -X utf8 scripts\check_connections.py

# With the server running: real tools/handoffs, saved state, SSE summary,
# real Redis rejection/recovery, and HTTP/SSE 429. Uses a few OpenAI calls.
.\.venv\Scripts\python.exe -X utf8 -u scripts\verify_live.py
```

The live verification uses synthetic customer data and saves evidence to `output/live-verification.json`. It uses a separate loopback IP for HTTP quota tests so it does not exhaust the browser's quota. Allow the configured window to expire before repeating those quota tests.

`GET /health` reports app liveness and the configured model. `GET /ready` verifies Redis connectivity, returning `503` when unavailable; it does not spend OpenAI tokens or claim OpenAI availability. `check_connections.py` performs the actual provider check.

To stop this project's Redis when it is no longer needed:

```powershell
docker compose -f compose.yaml down
```

## Changes from the supplied code

The initial source hard-coded Gemini in all four agents, had only a Google key in `.env`, did not implement Redis limiting, and referenced an absent tracking agent. Cart tools accepted arbitrary prices/quantities, returned no explicit result, and the summary required template fields that could be absent. The integration now centralizes configuration, uses the requested OpenAI model, validates tool inputs, computes totals, handles missing state and provider failures, supplies a rate-limited local web/API entry point, and includes reproducible setup and verification scripts. The original PDF remains the historical description of the Gemini demo; this README describes the current configuration.

Integration references: [OpenAI GPT-4o mini](https://developers.openai.com/api/docs/models/gpt-4o-mini), [ADK LiteLLM adapter](https://adk.dev/agents/models/litellm/), [Redis atomic counter pattern](https://redis.io/docs/latest/commands/incr/).
