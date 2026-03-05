#!/usr/bin/env python3
"""AgentGraph load testing script.

Self-contained load tester using httpx + asyncio. No external dependencies
beyond httpx (already in the project).

Usage examples:
    python3 scripts/load_test.py --scenario auth_flow --users 100 --concurrency 20
    python3 scripts/load_test.py --scenario mixed --users 200 --duration 60
    python3 scripts/load_test.py --all --users 50 --concurrency 10
    python3 scripts/load_test.py --scenario feed_crud --base-url http://***REMOVED***:8001
"""
from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import string
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------

BASE_URL: str = "http://localhost:8000"
API_PREFIX: str = "/api/v1"
NUM_USERS: int = 50
REQUESTS_PER_USER: int = 20
CONCURRENCY: int = 10
DURATION: int = 0  # seconds; 0 = run REQUESTS_PER_USER per user instead


# ---------------------------------------------------------------------------
# Metrics collector
# ---------------------------------------------------------------------------


@dataclass
class RequestMetric:
    """Single request timing and result."""

    scenario: str
    endpoint: str
    method: str
    status_code: int
    latency_ms: float
    success: bool
    error: str | None = None


@dataclass
class MetricsCollector:
    """Thread-safe metrics aggregator."""

    metrics: list[RequestMetric] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    start_time: float = field(default_factory=time.monotonic)

    async def record(self, metric: RequestMetric) -> None:
        async with self._lock:
            self.metrics.append(metric)

    @property
    def total_requests(self) -> int:
        return len(self.metrics)

    @property
    def successes(self) -> int:
        return sum(1 for m in self.metrics if m.success)

    @property
    def failures(self) -> int:
        return sum(1 for m in self.metrics if not m.success)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.start_time

    @property
    def throughput(self) -> float:
        elapsed = self.elapsed_seconds
        if elapsed <= 0:
            return 0.0
        return self.total_requests / elapsed

    def latencies(self, scenario: str | None = None) -> list[float]:
        if scenario:
            return [m.latency_ms for m in self.metrics if m.scenario == scenario]
        return [m.latency_ms for m in self.metrics]

    def percentile(
        self, p: float, scenario: str | None = None,
    ) -> float:
        lats = sorted(self.latencies(scenario))
        if not lats:
            return 0.0
        k = (len(lats) - 1) * (p / 100.0)
        f_idx = int(k)
        c_idx = min(f_idx + 1, len(lats) - 1)
        d = k - f_idx
        return lats[f_idx] + d * (lats[c_idx] - lats[f_idx])

    def scenarios_seen(self) -> list[str]:
        return sorted(set(m.scenario for m in self.metrics))

    def status_code_counts(
        self, scenario: str | None = None,
    ) -> dict[int, int]:
        counts: dict[int, int] = {}
        for m in self.metrics:
            if scenario and m.scenario != scenario:
                continue
            counts[m.status_code] = counts.get(m.status_code, 0) + 1
        return counts

    def summary_row(self, scenario: str | None = None) -> dict[str, Any]:
        lats = self.latencies(scenario)
        subset = [m for m in self.metrics if (not scenario or m.scenario == scenario)]
        ok = sum(1 for m in subset if m.success)
        fail = sum(1 for m in subset if not m.success)
        return {
            "scenario": scenario or "ALL",
            "total": len(subset),
            "success": ok,
            "fail": fail,
            "p50_ms": round(self.percentile(50, scenario), 1),
            "p95_ms": round(self.percentile(95, scenario), 1),
            "p99_ms": round(self.percentile(99, scenario), 1),
            "mean_ms": round(statistics.mean(lats), 1) if lats else 0.0,
            "min_ms": round(min(lats), 1) if lats else 0.0,
            "max_ms": round(max(lats), 1) if lats else 0.0,
        }


# ---------------------------------------------------------------------------
# Result formatting
# ---------------------------------------------------------------------------


def format_results_table(collector: MetricsCollector) -> str:
    """Build a pretty ASCII table from collected metrics."""
    rows: list[dict[str, Any]] = []
    for scen in collector.scenarios_seen():
        rows.append(collector.summary_row(scen))
    if len(rows) > 1:
        rows.append(collector.summary_row(None))

    if not rows:
        return "No requests were recorded."

    headers = [
        ("Scenario", "scenario", 20),
        ("Total", "total", 7),
        ("OK", "success", 7),
        ("Fail", "fail", 7),
        ("p50(ms)", "p50_ms", 10),
        ("p95(ms)", "p95_ms", 10),
        ("p99(ms)", "p99_ms", 10),
        ("Mean(ms)", "mean_ms", 10),
        ("Min(ms)", "min_ms", 10),
        ("Max(ms)", "max_ms", 10),
    ]

    # Header line
    header_line = " | ".join(h[0].ljust(h[2]) for h in headers)
    sep_line = "-+-".join("-" * h[2] for h in headers)

    lines = [
        "",
        "=" * len(sep_line),
        "  LOAD TEST RESULTS",
        "=" * len(sep_line),
        header_line,
        sep_line,
    ]

    for row in rows:
        cells = []
        for _label, key, width in headers:
            val = str(row.get(key, ""))
            cells.append(val.ljust(width))
        lines.append(" | ".join(cells))

    lines.append(sep_line)
    lines.append(
        f"  Elapsed: {collector.elapsed_seconds:.1f}s"
        f"  |  Throughput: {collector.throughput:.1f} req/s"
        f"  |  Total: {collector.total_requests}"
        f"  |  Errors: {collector.failures}",
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

try:
    import httpx  # noqa: E402
except ImportError:
    print("ERROR: httpx is required. Install with: pip install httpx")
    sys.exit(1)


def _random_email() -> str:
    tag = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"loadtest_{tag}@example.com"


def _random_display_name() -> str:
    adjectives = ["Fast", "Smart", "Bold", "Quick", "Keen", "Sharp", "Calm"]
    nouns = ["Agent", "Runner", "Tester", "Bot", "Node", "Relay", "Proxy"]
    return f"{random.choice(adjectives)}{random.choice(nouns)}{random.randint(1, 9999)}"


def _random_content() -> str:
    phrases = [
        "Testing the feed under load.",
        "Exploring agent trust networks at scale.",
        "How does the system handle concurrent writes?",
        "Load test post — measuring p99 latency.",
        "Decentralized identity verification at speed.",
        "Benchmarking the social graph API.",
        "Stress testing trust score computations.",
        "AgentGraph performance evaluation in progress.",
    ]
    return random.choice(phrases) + f" [{uuid.uuid4().hex[:8]}]"


def _random_search_term() -> str:
    terms = ["agent", "trust", "test", "smart", "bold", "fast", "runner", "node"]
    return random.choice(terms)


async def _timed_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    collector: MetricsCollector,
    scenario: str,
    **kwargs: Any,
) -> tuple[int, Any]:
    """Execute an HTTP request and record metrics."""
    start = time.monotonic()
    status_code = 0
    body: Any = None
    error_msg: str | None = None
    success = False

    try:
        resp = await client.request(method, url, **kwargs)
        status_code = resp.status_code
        success = 200 <= status_code < 400
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        if not success:
            error_msg = str(body)[:200] if body else f"HTTP {status_code}"
    except httpx.TimeoutException:
        error_msg = "timeout"
    except httpx.ConnectError:
        error_msg = "connection_refused"
    except Exception as exc:
        error_msg = str(exc)[:200]

    latency_ms = (time.monotonic() - start) * 1000.0

    await collector.record(RequestMetric(
        scenario=scenario,
        endpoint=url,
        method=method.upper(),
        status_code=status_code,
        latency_ms=latency_ms,
        success=success,
        error=error_msg,
    ))

    return status_code, body


# ---------------------------------------------------------------------------
# Scenario implementations
# ---------------------------------------------------------------------------


async def scenario_auth_flow(
    client: httpx.AsyncClient,
    collector: MetricsCollector,
    _iteration: int,
) -> None:
    """Register -> login -> /me flow."""
    email = _random_email()
    password = "LoadTest123!"
    display_name = _random_display_name()

    # Register
    await _timed_request(
        client, "POST", f"{API_PREFIX}/auth/register",
        collector, "auth_flow",
        json={"email": email, "password": password, "display_name": display_name},
    )

    # Login
    status_code, body = await _timed_request(
        client, "POST", f"{API_PREFIX}/auth/login",
        collector, "auth_flow",
        json={"email": email, "password": password},
    )

    if status_code != 200 or not isinstance(body, dict):
        return

    token = body.get("access_token", "")
    if not token:
        return

    # Get /me
    await _timed_request(
        client, "GET", f"{API_PREFIX}/auth/me",
        collector, "auth_flow",
        headers={"Authorization": f"Bearer {token}"},
    )


async def scenario_feed_crud(
    client: httpx.AsyncClient,
    collector: MetricsCollector,
    _iteration: int,
) -> None:
    """Create post -> read feed -> vote on a post."""
    # First get a token via quick registration + login
    email = _random_email()
    password = "LoadTest123!"
    display_name = _random_display_name()

    await _timed_request(
        client, "POST", f"{API_PREFIX}/auth/register",
        collector, "feed_crud",
        json={"email": email, "password": password, "display_name": display_name},
    )

    status_code, body = await _timed_request(
        client, "POST", f"{API_PREFIX}/auth/login",
        collector, "feed_crud",
        json={"email": email, "password": password},
    )

    if status_code != 200 or not isinstance(body, dict):
        return

    token = body.get("access_token", "")
    if not token:
        return

    auth_headers = {"Authorization": f"Bearer {token}"}

    # Create post
    status_code, post_body = await _timed_request(
        client, "POST", f"{API_PREFIX}/feed/posts",
        collector, "feed_crud",
        json={"content": _random_content()},
        headers=auth_headers,
    )

    # Read feed
    _, feed_body = await _timed_request(
        client, "GET", f"{API_PREFIX}/feed/posts?limit=20&sort=newest",
        collector, "feed_crud",
        headers=auth_headers,
    )

    # Vote on our own post (or first from feed)
    post_id = None
    if isinstance(post_body, dict) and "id" in post_body:
        post_id = post_body["id"]
    elif isinstance(feed_body, dict) and feed_body.get("posts"):
        post_id = feed_body["posts"][0].get("id")

    if post_id:
        await _timed_request(
            client, "POST", f"{API_PREFIX}/feed/posts/{post_id}/vote",
            collector, "feed_crud",
            json={"direction": "up"},
            headers=auth_headers,
        )


async def scenario_search(
    client: httpx.AsyncClient,
    collector: MetricsCollector,
    _iteration: int,
) -> None:
    """Search entities and posts."""
    term = _random_search_term()

    # Search all
    await _timed_request(
        client, "GET", f"{API_PREFIX}/search?q={term}",
        collector, "search",
    )

    # Search with type filter
    await _timed_request(
        client, "GET", f"{API_PREFIX}/search?q={term}&type=agent",
        collector, "search",
    )

    # Search posts only
    await _timed_request(
        client, "GET", f"{API_PREFIX}/search?q={term}&type=post",
        collector, "search",
    )


async def scenario_trust_scoring(
    client: httpx.AsyncClient,
    collector: MetricsCollector,
    _iteration: int,
) -> None:
    """Get trust scores for entities discovered via profiles."""
    # Browse profiles first to find entity IDs
    _, body = await _timed_request(
        client, "GET", f"{API_PREFIX}/profiles?limit=10",
        collector, "trust_scoring",
    )

    entity_ids: list[str] = []
    if isinstance(body, dict):
        profiles = body.get("profiles", body.get("entities", []))
        if isinstance(profiles, list):
            for p in profiles:
                if isinstance(p, dict) and "id" in p:
                    entity_ids.append(str(p["id"]))

    # Get trust score for up to 3 discovered entities
    for eid in entity_ids[:3]:
        await _timed_request(
            client, "GET", f"{API_PREFIX}/entities/{eid}/trust",
            collector, "trust_scoring",
        )


async def scenario_profile_browsing(
    client: httpx.AsyncClient,
    collector: MetricsCollector,
    _iteration: int,
) -> None:
    """Browse profiles with various filters and offsets."""
    # Browse all profiles
    await _timed_request(
        client, "GET", f"{API_PREFIX}/profiles?limit=20",
        collector, "profile_browsing",
    )

    # Browse with search
    await _timed_request(
        client, "GET", f"{API_PREFIX}/profiles?q=agent&limit=10",
        collector, "profile_browsing",
    )

    # Browse with type filter
    await _timed_request(
        client, "GET", f"{API_PREFIX}/profiles?entity_type=agent&limit=10",
        collector, "profile_browsing",
    )

    # Browse with offset (pagination)
    await _timed_request(
        client, "GET", f"{API_PREFIX}/profiles?limit=10&offset=10",
        collector, "profile_browsing",
    )


async def scenario_mixed(
    client: httpx.AsyncClient,
    collector: MetricsCollector,
    iteration: int,
) -> None:
    """Randomly pick from the other scenarios to simulate realistic traffic."""
    choices = [
        scenario_auth_flow,
        scenario_feed_crud,
        scenario_search,
        scenario_trust_scoring,
        scenario_profile_browsing,
    ]
    fn = random.choice(choices)
    await fn(client, collector, iteration)


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, Callable[..., Any]] = {
    "auth_flow": scenario_auth_flow,
    "feed_crud": scenario_feed_crud,
    "search": scenario_search,
    "trust_scoring": scenario_trust_scoring,
    "profile_browsing": scenario_profile_browsing,
    "mixed": scenario_mixed,
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def _run_user(
    user_idx: int,
    scenario_fn: Callable[..., Any],
    client: httpx.AsyncClient,
    collector: MetricsCollector,
    semaphore: asyncio.Semaphore,
    requests_per_user: int,
    duration: int,
) -> None:
    """Simulate a single user running the scenario repeatedly."""
    if duration > 0:
        end_time = time.monotonic() + duration
        iteration = 0
        while time.monotonic() < end_time:
            async with semaphore:
                await scenario_fn(client, collector, iteration)
            iteration += 1
    else:
        for iteration in range(requests_per_user):
            async with semaphore:
                await scenario_fn(client, collector, iteration)


async def run_load_test(
    base_url: str,
    scenario_name: str,
    num_users: int,
    requests_per_user: int,
    concurrency: int,
    duration: int = 0,
    timeout_s: float = 30.0,
) -> MetricsCollector:
    """Execute a load test scenario and return collected metrics."""
    scenario_fn = SCENARIOS[scenario_name]
    collector = MetricsCollector()
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(timeout_s),
        follow_redirects=False,
    ) as client:
        tasks = [
            _run_user(
                i, scenario_fn, client, collector, semaphore,
                requests_per_user, duration,
            )
            for i in range(num_users)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    return collector


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AgentGraph load testing tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 scripts/load_test.py --scenario auth_flow --users 100\n"
            "  python3 scripts/load_test.py --scenario mixed --duration 60\n"
            "  python3 scripts/load_test.py --all --users 50 --concurrency 10\n"
        ),
    )

    parser.add_argument(
        "--scenario", "-s",
        choices=list(SCENARIOS.keys()),
        help="Scenario to run",
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Run all scenarios sequentially",
    )
    parser.add_argument(
        "--base-url", "-b",
        default=BASE_URL,
        help=f"Base URL of the API server (default: {BASE_URL})",
    )
    parser.add_argument(
        "--users", "-u",
        type=int, default=NUM_USERS,
        help=f"Number of simulated users (default: {NUM_USERS})",
    )
    parser.add_argument(
        "--rps", "-r",
        type=int, default=REQUESTS_PER_USER,
        help=f"Requests per user (default: {REQUESTS_PER_USER})",
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int, default=CONCURRENCY,
        help=f"Max concurrent requests (default: {CONCURRENCY})",
    )
    parser.add_argument(
        "--duration", "-d",
        type=int, default=DURATION,
        help="Run for N seconds instead of fixed request count (0=disabled)",
    )
    parser.add_argument(
        "--timeout",
        type=float, default=30.0,
        help="Per-request timeout in seconds (default: 30)",
    )

    return parser


async def _main(args: argparse.Namespace) -> None:
    scenarios_to_run: list[str] = []

    if args.all:
        scenarios_to_run = [
            name for name in SCENARIOS if name != "mixed"
        ]
    elif args.scenario:
        scenarios_to_run = [args.scenario]
    else:
        print("ERROR: Specify --scenario <name> or --all")
        sys.exit(1)

    print("\nAgentGraph Load Test")
    print(f"  Target:      {args.base_url}")
    print(f"  Users:       {args.users}")
    if args.duration > 0:
        print(f"  Duration:    {args.duration}s")
    else:
        print(f"  Requests/user: {args.rps}")
    print(f"  Concurrency: {args.concurrency}")
    print(f"  Scenarios:   {', '.join(scenarios_to_run)}")
    print()

    all_collectors: list[MetricsCollector] = []

    for scenario_name in scenarios_to_run:
        print(f"Running scenario: {scenario_name} ...")
        collector = await run_load_test(
            base_url=args.base_url,
            scenario_name=scenario_name,
            num_users=args.users,
            requests_per_user=args.rps,
            concurrency=args.concurrency,
            duration=args.duration,
            timeout_s=args.timeout,
        )
        all_collectors.append(collector)
        print(format_results_table(collector))

    # Combined summary if multiple scenarios
    if len(all_collectors) > 1:
        combined = MetricsCollector()
        combined.start_time = min(c.start_time for c in all_collectors)
        for c in all_collectors:
            combined.metrics.extend(c.metrics)
        print("\n--- COMBINED RESULTS ---")
        print(format_results_table(combined))


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
