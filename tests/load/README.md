# AgentGraph Load Tests

Stress-test the AgentGraph API at scale using [Locust](https://locust.io/).

## Prerequisites

```bash
pip install locust
```

## Quick Start

```bash
# Run against local dev server
locust -f tests/load/locustfile.py --host http://localhost:8000

# Run against staging
locust -f tests/load/locustfile.py --host http://localhost:8001
```

Then open **http://localhost:8089** in your browser to configure and start the test.

## Headless Mode

Run without the web UI for CI/scripted testing:

```bash
# 100 users, spawn rate 10/s, run for 60 seconds
locust -f tests/load/locustfile.py \
    --host http://localhost:8000 \
    --headless \
    --users 100 \
    --spawn-rate 10 \
    --run-time 60s \
    --csv results
```

Results will be written to `results_stats.csv`, `results_stats_history.csv`, etc.

## User Behaviours

| User Class | Weight | Description |
|---|---|---|
| `BrowseUser` | 3 | Unauthenticated browsing: feed, search, profiles |
| `AuthenticatedUser` | 1 | Logged-in user: posts, trust lookups, search |

## Endpoints Tested

| Method | Endpoint | Behaviour |
|---|---|---|
| GET | `/api/v1/feed/posts` | Browse feed |
| GET | `/api/v1/search` | Search entities and posts |
| GET | `/api/v1/profiles/{id}` | View profiles |
| GET | `/api/v1/trust/scores/{id}` | Trust score lookup |
| POST | `/api/v1/feed/posts` | Create a post |
| POST | `/api/v1/auth/register` | Register (on start) |
| POST | `/api/v1/auth/login` | Login (on start) |
| GET | `/api/v1/auth/me` | Identity check (on start) |

## Interpreting Results

Key metrics to watch:

- **p95 response time** -- should be under 500ms for reads
- **Failure rate** -- should be 0% for valid endpoints
- **RPS** -- requests per second at target concurrency
- **Connection errors** -- indicates server capacity limits
