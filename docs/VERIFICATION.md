# Recorded local verification

Date: **14 October 2026**. Environment: Windows, Python 3.12, OpenAI `gpt-4o-mini`, and a dedicated Redis 7.4 Docker container on loopback port 6381.

These results describe the local development build tested before publication. They are not production load-test results or a guarantee of future provider availability. Live requests used synthetic customer details; credentials and session databases are excluded from the repository.

| Check | Observed result |
| --- | --- |
| Automated tests | 26 passed, 0 failed |
| Dependency consistency | `pip check`: no broken requirements |
| OpenAI connection | A real completion succeeded using the configured key and requested model |
| Redis connection | PING succeeded; dedicated container was healthy |
| Full agent conversation | All four agents ran; profile, cart, address, and transfers completed |
| Cart arithmetic | Two Pixel 9 phones at INR 70,000 each produced INR 140,000 |
| Streamed summary | `/run_sse` returned a summary containing the saved product and total |
| HTTP quotas | `/run` and `/run_sse` returned HTTP 429 and `Retry-After` after exhaustion |
| Redis expiry and recovery | An isolated two-second test counter rejected the over-quota request and accepted a request after expiry |
| Browser flow | Profile, catalog, cart, checkout, and summary completed; two Boat Rockerz units produced INR 4,000 |
| Persistence | The browser session's saved cart and address remained available after a controlled server restart |
| Health configuration | `/health` reported `gpt-4o-mini` and rate limiting enabled; `/ready` reported Redis connected |
| Credential checks | Configured keys were absent from source, documentation, and evidence outputs |

Automated tests additionally cover invalid profiles, quantities and catalog entries; checkout prerequisites; missing summary state; concurrent quota enforcement; rejection during Redis failures; provider error redaction; and the configured health response.

## Reproduce

Follow the root README, then run the tests from `ADK_Shopping`:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

With your own `.env`, running Redis, and the app server:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\check_connections.py
.\.venv\Scripts\python.exe -X utf8 -u scripts\verify_live.py
```

Live verification spends OpenAI tokens, uses synthetic session data, and creates local JSON evidence under `output/`. Repeat the HTTP quota verification only after the configured rate-limit window expires. Model output is nondeterministic; the assertions check actual tool participation, saved fields, totals, and endpoint behavior.

The project supports a fixed educational catalog and one cart line. It does not submit real orders, process payments, query live inventory, or track deliveries. Hosted Redis and public application deployment were not part of the recorded local checks.
