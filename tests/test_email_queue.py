"""Tests for email rate limiting, retry, and overflow queue."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.email_queue import (
    _reset_for_testing,
    flush_email_queue,
    queue_depth,
    send_email_rated,
)

_SEND = "src.email_queue._raw_send"
_RATE = "src.email_queue._check_rate_limit_redis"
_SETT = "src.email_queue.settings"


@pytest.fixture(autouse=True)
def _clean_queue():
    """Reset internal queue state before each test."""
    _reset_for_testing()
    yield
    _reset_for_testing()


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_retries_on_failure():
    """Email send retries up to max_attempts with exponential backoff."""
    with (
        patch(_SEND, new_callable=AsyncMock) as mock_send,
        patch(_RATE, new_callable=AsyncMock, return_value=True),
        patch(_SETT) as ms,
    ):
        ms.email_retry_max_attempts = 3
        ms.email_retry_base_delay = 0.01
        mock_send.side_effect = [False, False, True]

        result = await send_email_rated("a@b.com", "Test", "<p>hi</p>")

        assert result is True
        assert mock_send.call_count == 3


@pytest.mark.asyncio
async def test_send_fails_after_max_retries():
    """Returns False after exhausting all retry attempts."""
    with (
        patch(_SEND, new_callable=AsyncMock, return_value=False) as ms,
        patch(_RATE, new_callable=AsyncMock, return_value=True),
        patch(_SETT) as cfg,
    ):
        cfg.email_retry_max_attempts = 2
        cfg.email_retry_base_delay = 0.01

        result = await send_email_rated("a@b.com", "Test", "<p>hi</p>")

        assert result is False
        assert ms.call_count == 2


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_queues_overflow():
    """When rate limit is hit, email is queued instead of sent."""
    with (
        patch(_SEND, new_callable=AsyncMock, return_value=True) as ms,
        patch(_RATE, new_callable=AsyncMock, return_value=False),
    ):
        result = await send_email_rated("a@b.com", "Test", "<p>hi</p>")

        assert result is True  # queued counts as success
        assert ms.call_count == 0
        assert queue_depth() == 1


@pytest.mark.asyncio
async def test_rate_limit_allows_under_limit():
    """Emails are sent immediately when under rate limit."""
    with (
        patch(_SEND, new_callable=AsyncMock, return_value=True) as ms,
        patch(_RATE, new_callable=AsyncMock, return_value=True),
        patch(_SETT) as cfg,
    ):
        cfg.email_retry_max_attempts = 1
        cfg.email_retry_base_delay = 0.01

        result = await send_email_rated("a@b.com", "Test", "<p>hi</p>")

        assert result is True
        assert ms.call_count == 1
        assert queue_depth() == 0


# ---------------------------------------------------------------------------
# Queue flush
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flush_drains_queue():
    """flush_email_queue sends queued emails when rate limit clears."""
    with (
        patch(_SEND, new_callable=AsyncMock, return_value=True) as ms,
        patch(_RATE, new_callable=AsyncMock) as mock_rate,
    ):
        # First call: rate limited -> queue
        mock_rate.return_value = False
        await send_email_rated("a@b.com", "Queued1", "<p>1</p>")
        await send_email_rated("b@b.com", "Queued2", "<p>2</p>")
        assert queue_depth() == 2
        assert ms.call_count == 0

        # Now rate limit clears
        mock_rate.return_value = True
        with patch(_SETT) as cfg:
            cfg.email_retry_max_attempts = 1
            cfg.email_retry_base_delay = 0.01
            sent = await flush_email_queue()

        assert sent == 2
        assert queue_depth() == 0
        assert ms.call_count == 2


@pytest.mark.asyncio
async def test_flush_stops_at_rate_limit():
    """flush_email_queue stops draining when rate limit is hit again."""
    with (
        patch(_SEND, new_callable=AsyncMock, return_value=True),
        patch(_RATE, new_callable=AsyncMock) as mock_rate,
    ):
        # Queue 3 emails
        mock_rate.return_value = False
        for i in range(3):
            await send_email_rated(f"{i}@b.com", f"Q{i}", "<p></p>")
        assert queue_depth() == 3

        # Allow 1 send then rate-limit again
        call_count = 0

        async def rate_toggle():
            nonlocal call_count
            call_count += 1
            return call_count <= 1

        mock_rate.side_effect = rate_toggle
        with patch(_SETT) as cfg:
            cfg.email_retry_max_attempts = 1
            cfg.email_retry_base_delay = 0.01
            sent = await flush_email_queue()

        assert sent == 1
        assert queue_depth() == 2


# ---------------------------------------------------------------------------
# In-memory fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_fallback_when_redis_unavailable():
    """Falls back to in-memory rate limiter if Redis raises."""
    with (
        patch(_SEND, new_callable=AsyncMock, return_value=True),
        patch(_SETT) as cfg,
    ):
        cfg.email_rate_limit_per_minute = 2
        cfg.email_retry_max_attempts = 1
        cfg.email_retry_base_delay = 0.01
        cfg.resend_api_key = None
        cfg.smtp_host = None

        # Make Redis fail so it falls through to memory
        with patch(
            "src.email_queue.get_redis",
            side_effect=Exception("no redis"),
        ):
            r1 = await send_email_rated("a@b.com", "T1", "<p></p>")
            r2 = await send_email_rated("b@b.com", "T2", "<p></p>")
            r3 = await send_email_rated("c@b.com", "T3", "<p></p>")

        assert r1 is True
        assert r2 is True
        assert r3 is True  # queued
        assert queue_depth() == 1
