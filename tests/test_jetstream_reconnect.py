"""Reconnect damping for the Jetstream subscriber (Sentry AGENTGRAPH-BACKEND-1F/1G).

Transient connect failures must log WARNING (no Sentry page); only a sustained
outage escalates to ERROR — same policy as the Anthropic-client fix (8b62902).
"""
from __future__ import annotations

from src.feeds.bluesky.subscriber import SUSTAINED_ERROR_THRESHOLD, _reconnect_plan


def test_first_failure_is_warning_short_delay():
    level, delay = _reconnect_plan(1)
    assert level == "warning"
    assert delay == 5


def test_blips_below_threshold_never_error():
    for n in range(1, SUSTAINED_ERROR_THRESHOLD):
        level, _ = _reconnect_plan(n)
        assert level == "warning", f"attempt {n} must not page"


def test_backoff_grows_and_caps_at_60():
    delays = [_reconnect_plan(n)[1] for n in range(1, 10)]
    assert delays[:5] == [5, 10, 20, 40, 60]
    assert all(d == 60 for d in delays[5:])


def test_sustained_outage_escalates_once_at_threshold():
    level, _ = _reconnect_plan(SUSTAINED_ERROR_THRESHOLD)
    assert level == "error"
    # The attempt right after the threshold goes back to warning (no per-attempt spam)
    level_next, _ = _reconnect_plan(SUSTAINED_ERROR_THRESHOLD + 1)
    assert level_next == "warning"


def test_periodic_reescalation_every_10th():
    assert _reconnect_plan(10)[0] == "error"
    assert _reconnect_plan(20)[0] == "error"
    assert _reconnect_plan(11)[0] == "warning"
