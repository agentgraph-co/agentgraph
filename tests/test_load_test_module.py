"""Unit tests for the load test module.

Tests the scenario registry, metrics collector, and result formatting
without making any actual HTTP calls.
"""
from __future__ import annotations

import asyncio

from scripts.load_test import (
    SCENARIOS,
    MetricsCollector,
    RequestMetric,
    format_results_table,
)

# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------


class TestScenarioRegistry:
    """Verify the SCENARIOS dict is well-formed."""

    def test_scenarios_dict_is_non_empty(self) -> None:
        assert len(SCENARIOS) > 0

    def test_expected_scenarios_present(self) -> None:
        expected = {
            "auth_flow",
            "feed_crud",
            "search",
            "trust_scoring",
            "profile_browsing",
            "mixed",
        }
        assert expected == set(SCENARIOS.keys())

    def test_all_scenarios_are_callable(self) -> None:
        for name, fn in SCENARIOS.items():
            assert callable(fn), f"Scenario {name!r} is not callable"

    def test_scenario_functions_are_coroutines(self) -> None:
        for name, fn in SCENARIOS.items():
            assert asyncio.iscoroutinefunction(fn), (
                f"Scenario {name!r} is not an async function"
            )


# ---------------------------------------------------------------------------
# MetricsCollector
# ---------------------------------------------------------------------------


def _make_metric(
    scenario: str = "test",
    endpoint: str = "/api/v1/test",
    method: str = "GET",
    status_code: int = 200,
    latency_ms: float = 10.0,
    success: bool = True,
    error: str | None = None,
) -> RequestMetric:
    return RequestMetric(
        scenario=scenario,
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        latency_ms=latency_ms,
        success=success,
        error=error,
    )


class TestMetricsCollector:
    """Test the MetricsCollector aggregation logic."""

    def test_empty_collector_counts(self) -> None:
        c = MetricsCollector()
        assert c.total_requests == 0
        assert c.successes == 0
        assert c.failures == 0

    def test_record_and_count(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(c.record(_make_metric(success=True)))
            loop.run_until_complete(c.record(_make_metric(success=True)))
            loop.run_until_complete(c.record(_make_metric(success=False, status_code=500)))
        finally:
            loop.close()

        assert c.total_requests == 3
        assert c.successes == 2
        assert c.failures == 1

    def test_latencies_all(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(c.record(_make_metric(latency_ms=10.0)))
            loop.run_until_complete(c.record(_make_metric(latency_ms=20.0)))
            loop.run_until_complete(c.record(_make_metric(latency_ms=30.0)))
        finally:
            loop.close()

        lats = c.latencies()
        assert lats == [10.0, 20.0, 30.0]

    def test_latencies_filtered_by_scenario(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(c.record(_make_metric(scenario="a", latency_ms=5.0)))
            loop.run_until_complete(c.record(_make_metric(scenario="b", latency_ms=50.0)))
            loop.run_until_complete(c.record(_make_metric(scenario="a", latency_ms=15.0)))
        finally:
            loop.close()

        assert c.latencies("a") == [5.0, 15.0]
        assert c.latencies("b") == [50.0]

    def test_percentile_on_empty(self) -> None:
        c = MetricsCollector()
        assert c.percentile(50) == 0.0
        assert c.percentile(99) == 0.0

    def test_percentile_p50_single_value(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(c.record(_make_metric(latency_ms=42.0)))
        finally:
            loop.close()

        assert c.percentile(50) == 42.0

    def test_percentile_p50_multiple(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            for lat in [10.0, 20.0, 30.0, 40.0, 50.0]:
                loop.run_until_complete(c.record(_make_metric(latency_ms=lat)))
        finally:
            loop.close()

        p50 = c.percentile(50)
        assert 29.0 <= p50 <= 31.0  # should be 30.0

    def test_percentile_p99(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            for lat in range(1, 101):
                loop.run_until_complete(
                    c.record(_make_metric(latency_ms=float(lat))),
                )
        finally:
            loop.close()

        p99 = c.percentile(99)
        assert p99 >= 99.0  # close to max

    def test_scenarios_seen(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(c.record(_make_metric(scenario="z_last")))
            loop.run_until_complete(c.record(_make_metric(scenario="a_first")))
            loop.run_until_complete(c.record(_make_metric(scenario="a_first")))
        finally:
            loop.close()

        assert c.scenarios_seen() == ["a_first", "z_last"]

    def test_status_code_counts(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(c.record(_make_metric(status_code=200)))
            loop.run_until_complete(c.record(_make_metric(status_code=200)))
            loop.run_until_complete(
                c.record(_make_metric(status_code=429, success=False)),
            )
            loop.run_until_complete(
                c.record(_make_metric(status_code=500, success=False)),
            )
        finally:
            loop.close()

        counts = c.status_code_counts()
        assert counts == {200: 2, 429: 1, 500: 1}

    def test_status_code_counts_filtered(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                c.record(_make_metric(scenario="auth", status_code=200)),
            )
            loop.run_until_complete(
                c.record(_make_metric(scenario="feed", status_code=201)),
            )
        finally:
            loop.close()

        assert c.status_code_counts("auth") == {200: 1}
        assert c.status_code_counts("feed") == {201: 1}

    def test_summary_row_structure(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(c.record(_make_metric(latency_ms=10.0)))
        finally:
            loop.close()

        row = c.summary_row()
        expected_keys = {
            "scenario", "total", "success", "fail",
            "p50_ms", "p95_ms", "p99_ms",
            "mean_ms", "min_ms", "max_ms",
        }
        assert set(row.keys()) == expected_keys

    def test_summary_row_with_scenario_filter(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(c.record(_make_metric(scenario="auth")))
            loop.run_until_complete(c.record(_make_metric(scenario="feed")))
        finally:
            loop.close()

        row = c.summary_row("auth")
        assert row["scenario"] == "auth"
        assert row["total"] == 1

    def test_throughput_positive(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(c.record(_make_metric()))
        finally:
            loop.close()

        assert c.throughput >= 0.0


# ---------------------------------------------------------------------------
# Result formatting
# ---------------------------------------------------------------------------


class TestFormatResultsTable:
    """Test the ASCII table formatter."""

    def test_empty_collector_produces_message(self) -> None:
        c = MetricsCollector()
        output = format_results_table(c)
        assert "No requests" in output

    def test_single_scenario_table(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(c.record(_make_metric(scenario="auth")))
            loop.run_until_complete(c.record(_make_metric(scenario="auth")))
        finally:
            loop.close()

        output = format_results_table(c)
        assert "LOAD TEST RESULTS" in output
        assert "auth" in output
        assert "Throughput" in output

    def test_multiple_scenarios_include_all_row(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(c.record(_make_metric(scenario="auth")))
            loop.run_until_complete(c.record(_make_metric(scenario="feed")))
        finally:
            loop.close()

        output = format_results_table(c)
        assert "auth" in output
        assert "feed" in output
        assert "ALL" in output

    def test_table_contains_percentile_headers(self) -> None:
        c = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(c.record(_make_metric()))
        finally:
            loop.close()

        output = format_results_table(c)
        assert "p50" in output
        assert "p95" in output
        assert "p99" in output


# ---------------------------------------------------------------------------
# RequestMetric dataclass
# ---------------------------------------------------------------------------


class TestRequestMetric:
    """Test the RequestMetric data structure."""

    def test_default_error_is_none(self) -> None:
        m = _make_metric()
        assert m.error is None

    def test_all_fields_set(self) -> None:
        m = _make_metric(
            scenario="auth",
            endpoint="/api/v1/auth/login",
            method="POST",
            status_code=200,
            latency_ms=15.5,
            success=True,
            error=None,
        )
        assert m.scenario == "auth"
        assert m.endpoint == "/api/v1/auth/login"
        assert m.method == "POST"
        assert m.status_code == 200
        assert m.latency_ms == 15.5
        assert m.success is True

    def test_error_field(self) -> None:
        m = _make_metric(success=False, error="connection_refused")
        assert m.error == "connection_refused"
        assert m.success is False
