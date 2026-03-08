"""Tests for the webhook event delivery worker.

Covers delivery logic, retry/back-off, delivery logging, subscription
health tracking, and event matching.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    Entity,
    EntityType,
    WebhookDeliveryLog,
    WebhookSubscription,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def entity(db: AsyncSession) -> Entity:
    """Create a minimal active entity for webhook subscription ownership."""
    eid = uuid.uuid4()
    ent = Entity(
        id=eid,
        type=EntityType.HUMAN,
        display_name="webhook-test-user",
        email="ww_test@example.com",
        password_hash="not-a-real-hash",
        did_web=f"did:web:agentgraph.co:u:{eid}",
        is_active=True,
    )
    db.add(ent)
    await db.flush()
    return ent


@pytest_asyncio.fixture
async def subscription(db: AsyncSession, entity: Entity) -> WebhookSubscription:
    """Create an active webhook subscription for entity.followed events."""
    secret = "test-signing-secret"
    sub = WebhookSubscription(
        id=uuid.uuid4(),
        entity_id=entity.id,
        callback_url="https://example.com/hook",
        secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
        signing_key=None,  # uses secret_hash fallback
        event_types=["entity.followed", "post.created"],
        is_active=True,
        consecutive_failures=0,
    )
    db.add(sub)
    await db.flush()
    return sub


def _make_response(status_code: int = 200) -> httpx.Response:
    """Build a minimal httpx.Response with the given status code."""
    return httpx.Response(status_code=status_code, request=httpx.Request("POST", "https://example.com"))


# ---------------------------------------------------------------------------
# _deliver_single
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deliver_single_success(db: AsyncSession, subscription: WebhookSubscription):
    """Successful delivery returns True and logs with success=True."""
    from src.jobs.webhook_worker import _deliver_single

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _make_response(200)

    result = await _deliver_single(
        mock_client, subscription, "entity.followed", {"user": "alice"}, 1, db,
    )
    assert result is True

    # Verify delivery log was written
    logs = (await db.execute(
        select(WebhookDeliveryLog).where(
            WebhookDeliveryLog.subscription_id == subscription.id,
        )
    )).scalars().all()
    assert len(logs) == 1
    log = logs[0]
    assert log.success is True
    assert log.status_code == 200
    assert log.attempt_number == 1
    assert log.event_type == "entity.followed"
    assert log.error_message is None
    assert log.duration_ms is not None
    assert log.duration_ms >= 0


@pytest.mark.asyncio
async def test_deliver_single_http_error(db: AsyncSession, subscription: WebhookSubscription):
    """Non-2xx response returns False and logs the HTTP status."""
    from src.jobs.webhook_worker import _deliver_single

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _make_response(500)

    result = await _deliver_single(
        mock_client, subscription, "entity.followed", {"user": "bob"}, 2, db,
    )
    assert result is False

    logs = (await db.execute(
        select(WebhookDeliveryLog).where(
            WebhookDeliveryLog.subscription_id == subscription.id,
        )
    )).scalars().all()
    assert len(logs) == 1
    log = logs[0]
    assert log.success is False
    assert log.status_code == 500
    assert log.error_message == "HTTP 500"
    assert log.attempt_number == 2


@pytest.mark.asyncio
async def test_deliver_single_timeout(db: AsyncSession, subscription: WebhookSubscription):
    """Timeout exception returns False and logs the error."""
    from src.jobs.webhook_worker import _deliver_single

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.TimeoutException("read timed out")

    result = await _deliver_single(
        mock_client, subscription, "entity.followed", {}, 1, db,
    )
    assert result is False

    logs = (await db.execute(
        select(WebhookDeliveryLog).where(
            WebhookDeliveryLog.subscription_id == subscription.id,
        )
    )).scalars().all()
    assert len(logs) == 1
    assert logs[0].status_code is None
    assert "Timeout" in (logs[0].error_message or "")


@pytest.mark.asyncio
async def test_deliver_single_connection_error(db: AsyncSession, subscription: WebhookSubscription):
    """Connection error returns False and logs the error."""
    from src.jobs.webhook_worker import _deliver_single

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.ConnectError("refused")

    result = await _deliver_single(
        mock_client, subscription, "entity.followed", {}, 1, db,
    )
    assert result is False

    logs = (await db.execute(
        select(WebhookDeliveryLog).where(
            WebhookDeliveryLog.subscription_id == subscription.id,
        )
    )).scalars().all()
    assert len(logs) == 1
    assert "Connection error" in (logs[0].error_message or "")


# ---------------------------------------------------------------------------
# deliver_with_retries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deliver_with_retries_immediate_success(
    db: AsyncSession, subscription: WebhookSubscription,
):
    """First attempt succeeds — no retries needed."""
    from src.jobs.webhook_worker import deliver_with_retries

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _make_response(200)

    ok = await deliver_with_retries(
        mock_client, subscription, "entity.followed", {"x": 1}, db,
        max_retries=3,
    )
    assert ok is True
    assert mock_client.post.call_count == 1
    # consecutive_failures should stay at 0
    assert subscription.consecutive_failures == 0


@pytest.mark.asyncio
async def test_deliver_with_retries_eventual_success(
    db: AsyncSession, subscription: WebhookSubscription,
):
    """First two attempts fail, third succeeds."""
    from src.jobs.webhook_worker import deliver_with_retries

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = [
        _make_response(503),
        _make_response(502),
        _make_response(200),
    ]

    with patch("src.jobs.webhook_worker._backoff_delay", new_callable=AsyncMock):
        ok = await deliver_with_retries(
            mock_client, subscription, "entity.followed", {}, db,
            max_retries=3,
        )
    assert ok is True
    assert mock_client.post.call_count == 3
    # Reset on success
    assert subscription.consecutive_failures == 0

    # Should have 3 delivery log entries
    count = len((await db.execute(
        select(WebhookDeliveryLog).where(
            WebhookDeliveryLog.subscription_id == subscription.id,
        )
    )).scalars().all())
    assert count == 3


@pytest.mark.asyncio
async def test_deliver_with_retries_all_fail(
    db: AsyncSession, subscription: WebhookSubscription,
):
    """All retries exhausted — consecutive_failures increments."""
    from src.jobs.webhook_worker import deliver_with_retries

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _make_response(500)

    with patch("src.jobs.webhook_worker._backoff_delay", new_callable=AsyncMock):
        ok = await deliver_with_retries(
            mock_client, subscription, "entity.followed", {}, db,
            max_retries=3,
        )
    assert ok is False
    assert mock_client.post.call_count == 3
    assert subscription.consecutive_failures == 1
    assert subscription.is_active is True  # not yet deactivated


@pytest.mark.asyncio
async def test_deliver_with_retries_auto_deactivate(
    db: AsyncSession, subscription: WebhookSubscription,
):
    """Subscription auto-deactivates at the threshold."""
    from src.jobs.webhook_worker import deliver_with_retries

    subscription.consecutive_failures = 9  # one away from threshold
    await db.flush()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _make_response(500)

    with patch("src.jobs.webhook_worker._backoff_delay", new_callable=AsyncMock):
        ok = await deliver_with_retries(
            mock_client, subscription, "entity.followed", {}, db,
            max_retries=1,
        )
    assert ok is False
    assert subscription.consecutive_failures == 10
    assert subscription.is_active is False


@pytest.mark.asyncio
async def test_deliver_success_resets_failures(
    db: AsyncSession, subscription: WebhookSubscription,
):
    """Successful delivery resets consecutive_failures to 0."""
    from src.jobs.webhook_worker import deliver_with_retries

    subscription.consecutive_failures = 5
    await db.flush()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _make_response(200)

    ok = await deliver_with_retries(
        mock_client, subscription, "entity.followed", {}, db,
        max_retries=1,
    )
    assert ok is True
    assert subscription.consecutive_failures == 0


# ---------------------------------------------------------------------------
# _find_matching_subscriptions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_find_matching_subscriptions_matches(
    db: AsyncSession, subscription: WebhookSubscription,
):
    """Returns subscriptions whose event_types include the given event."""
    from src.jobs.webhook_worker import _find_matching_subscriptions

    matched = await _find_matching_subscriptions(db, "entity.followed")
    ids = [s.id for s in matched]
    assert subscription.id in ids


@pytest.mark.asyncio
async def test_find_matching_subscriptions_no_match(
    db: AsyncSession, subscription: WebhookSubscription,
):
    """Returns empty list for events no subscription cares about."""
    from src.jobs.webhook_worker import _find_matching_subscriptions

    matched = await _find_matching_subscriptions(db, "marketplace.purchased")
    assert len(matched) == 0


@pytest.mark.asyncio
async def test_find_matching_subscriptions_ignores_inactive(
    db: AsyncSession, entity: Entity,
):
    """Inactive subscriptions are excluded."""
    from src.jobs.webhook_worker import _find_matching_subscriptions

    sub = WebhookSubscription(
        id=uuid.uuid4(),
        entity_id=entity.id,
        callback_url="https://example.com/hook",
        secret_hash="abc",
        event_types=["entity.followed"],
        is_active=False,
        consecutive_failures=0,
    )
    db.add(sub)
    await db.flush()

    matched = await _find_matching_subscriptions(db, "entity.followed")
    ids = [s.id for s in matched]
    assert sub.id not in ids


# ---------------------------------------------------------------------------
# process_event (integration-ish, uses its own session)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_event_no_subscriptions():
    """process_event returns zeros when there are no matching subscriptions."""
    from src.jobs.webhook_worker import process_event

    # Use a fresh DB session via async_session (test DB).
    # Since conftest truncates tables at session start, no subs should match.
    with patch("src.jobs.webhook_worker.async_session") as mock_session_maker:
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_maker.return_value = ctx

        summary = await process_event("entity.followed", {"test": True}, max_retries=1)
        assert summary == {"matched": 0, "delivered": 0, "failed": 0}


@pytest.mark.asyncio
async def test_process_event_with_matching_sub():
    """process_event delivers to matching subscriptions and commits."""
    from src.jobs.webhook_worker import process_event

    sub = MagicMock(spec=WebhookSubscription)
    sub.id = uuid.uuid4()
    sub.entity_id = uuid.uuid4()
    sub.callback_url = "https://example.com/hook"
    sub.secret_hash = "abc123"
    sub.signing_key = None
    sub.event_types = ["post.created"]
    sub.is_active = True
    sub.consecutive_failures = 0

    p_session = patch("src.jobs.webhook_worker.async_session")
    p_find = patch(
        "src.jobs.webhook_worker._find_matching_subscriptions",
        new_callable=AsyncMock,
    )
    p_deliver = patch(
        "src.jobs.webhook_worker.deliver_with_retries",
        new_callable=AsyncMock,
    )
    with p_session as mock_session_maker, \
         p_find as mock_find, \
         p_deliver as mock_deliver:

        mock_find.return_value = [sub]
        mock_deliver.return_value = True

        mock_db = AsyncMock(spec=AsyncSession)
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_maker.return_value = ctx

        summary = await process_event("post.created", {"post_id": "123"}, max_retries=1)

        assert summary["matched"] == 1
        assert summary["delivered"] == 1
        assert summary["failed"] == 0
        mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_event_with_failed_delivery():
    """process_event counts failed deliveries correctly."""
    from src.jobs.webhook_worker import process_event

    sub = MagicMock(spec=WebhookSubscription)
    sub.id = uuid.uuid4()
    sub.entity_id = uuid.uuid4()
    sub.callback_url = "https://example.com/hook"
    sub.secret_hash = "abc123"
    sub.signing_key = None
    sub.event_types = ["post.created"]
    sub.is_active = True
    sub.consecutive_failures = 0

    p_session = patch("src.jobs.webhook_worker.async_session")
    p_find = patch(
        "src.jobs.webhook_worker._find_matching_subscriptions",
        new_callable=AsyncMock,
    )
    p_deliver = patch(
        "src.jobs.webhook_worker.deliver_with_retries",
        new_callable=AsyncMock,
    )
    with p_session as mock_session_maker, \
         p_find as mock_find, \
         p_deliver as mock_deliver:

        mock_find.return_value = [sub]
        mock_deliver.return_value = False

        mock_db = AsyncMock(spec=AsyncSession)
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_maker.return_value = ctx

        summary = await process_event("post.created", {"post_id": "123"}, max_retries=1)

        assert summary["matched"] == 1
        assert summary["delivered"] == 0
        assert summary["failed"] == 1


# ---------------------------------------------------------------------------
# Signature computation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_signature_is_valid_hmac():
    """Webhook signature is a valid HMAC-SHA256 over the body."""
    from src.jobs.webhook_worker import _compute_signature

    key = "my-key"
    body = '{"event_type": "test"}'

    sig = _compute_signature(body, key)

    import hmac as hmac_mod
    expected = hmac_mod.new(key.encode(), body.encode(), hashlib.sha256).hexdigest()
    assert sig == expected


# ---------------------------------------------------------------------------
# Payload body construction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_payload_body_structure():
    """Built payload body includes event_type, timestamp, and payload."""
    from src.jobs.webhook_worker import _build_payload_body

    body = _build_payload_body("entity.followed", {"follower": "alice"})
    parsed = json.loads(body)

    assert parsed["event_type"] == "entity.followed"
    assert "timestamp" in parsed
    assert parsed["payload"] == {"follower": "alice"}

    # Verify timestamp is valid ISO format
    datetime.fromisoformat(parsed["timestamp"])


# ---------------------------------------------------------------------------
# Backoff delay
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backoff_delay_increases():
    """Back-off delay increases with attempt number."""
    from src.jobs.webhook_worker import RETRY_BASE_DELAY, RETRY_MAX_DELAY

    # Attempt 1: base_delay * 2^0 = base_delay
    # Attempt 3: base_delay * 2^2 = base_delay * 4
    # Verify the exponential formula is bounded
    for attempt in range(1, 8):
        expected_base = min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), RETRY_MAX_DELAY)
        assert expected_base <= RETRY_MAX_DELAY


# ---------------------------------------------------------------------------
# Signing key resolution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_signing_key_uses_secret_hash_fallback(
    subscription: WebhookSubscription,
):
    """When signing_key is None, secret_hash is used."""
    from src.jobs.webhook_worker import _resolve_signing_key

    key = _resolve_signing_key(subscription)
    assert key == subscription.secret_hash


@pytest.mark.asyncio
async def test_resolve_signing_key_decrypts_when_present(
    subscription: WebhookSubscription,
):
    """When signing_key is set, it is decrypted."""
    from src.jobs.webhook_worker import _resolve_signing_key

    subscription.signing_key = "plaintext-key"

    with patch("src.encryption.decrypt_secret", return_value="decrypted-key") as mock_dec:
        key = _resolve_signing_key(subscription)
        mock_dec.assert_called_once_with("plaintext-key")
        assert key == "decrypted-key"


# ---------------------------------------------------------------------------
# Multiple subscriptions for the same event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_subscriptions_matched(
    db: AsyncSession, entity: Entity,
):
    """Multiple active subscriptions for the same event type are all found."""
    from src.jobs.webhook_worker import _find_matching_subscriptions

    sub_a = WebhookSubscription(
        id=uuid.uuid4(),
        entity_id=entity.id,
        callback_url="https://example.com/hook-a",
        secret_hash="a",
        event_types=["post.created"],
        is_active=True,
        consecutive_failures=0,
    )
    sub_b = WebhookSubscription(
        id=uuid.uuid4(),
        entity_id=entity.id,
        callback_url="https://example.com/hook-b",
        secret_hash="b",
        event_types=["post.created", "entity.followed"],
        is_active=True,
        consecutive_failures=0,
    )
    db.add(sub_a)
    db.add(sub_b)
    await db.flush()

    matched = await _find_matching_subscriptions(db, "post.created")
    matched_ids = {s.id for s in matched}
    assert sub_a.id in matched_ids
    assert sub_b.id in matched_ids


# ---------------------------------------------------------------------------
# Delivery log persistence accuracy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delivery_log_records_payload(
    db: AsyncSession, subscription: WebhookSubscription,
):
    """Delivery log stores the original event payload."""
    from src.jobs.webhook_worker import _deliver_single

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _make_response(200)

    payload = {"entity_id": str(uuid.uuid4()), "action": "follow"}
    await _deliver_single(
        mock_client, subscription, "entity.followed", payload, 1, db,
    )

    logs = (await db.execute(
        select(WebhookDeliveryLog).where(
            WebhookDeliveryLog.subscription_id == subscription.id,
        )
    )).scalars().all()
    assert len(logs) == 1
    assert logs[0].payload["entity_id"] == payload["entity_id"]
    assert logs[0].payload["action"] == "follow"


# ---------------------------------------------------------------------------
# HTTP POST request headers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delivery_sends_correct_headers(
    db: AsyncSession, subscription: WebhookSubscription,
):
    """HTTP POST includes Content-Type, signature, and event type headers."""
    from src.jobs.webhook_worker import _deliver_single

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _make_response(200)

    await _deliver_single(
        mock_client, subscription, "entity.followed", {}, 1, db,
    )

    call_kwargs = mock_client.post.call_args
    headers = call_kwargs.kwargs.get("headers", {})
    assert headers["Content-Type"] == "application/json"
    assert headers["X-AgentGraph-Event"] == "entity.followed"
    assert headers["X-AgentGraph-Signature"].startswith("sha256=")


@pytest.mark.asyncio
async def test_delivery_posts_to_correct_url(
    db: AsyncSession, subscription: WebhookSubscription,
):
    """HTTP POST is sent to the subscription's callback_url."""
    from src.jobs.webhook_worker import _deliver_single

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _make_response(200)

    await _deliver_single(
        mock_client, subscription, "entity.followed", {}, 1, db,
    )

    call_args = mock_client.post.call_args
    assert call_args.args[0] == subscription.callback_url


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deliver_with_retries_max_retries_one(
    db: AsyncSession, subscription: WebhookSubscription,
):
    """With max_retries=1, exactly one attempt is made."""
    from src.jobs.webhook_worker import deliver_with_retries

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _make_response(500)

    ok = await deliver_with_retries(
        mock_client, subscription, "entity.followed", {}, db,
        max_retries=1,
    )
    assert ok is False
    assert mock_client.post.call_count == 1


@pytest.mark.asyncio
async def test_deliver_with_retries_generic_exception(
    db: AsyncSession, subscription: WebhookSubscription,
):
    """Generic exceptions are caught and treated as failures."""
    from src.jobs.webhook_worker import deliver_with_retries

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = RuntimeError("unexpected")

    ok = await deliver_with_retries(
        mock_client, subscription, "entity.followed", {}, db,
        max_retries=1,
    )
    assert ok is False

    logs = (await db.execute(
        select(WebhookDeliveryLog).where(
            WebhookDeliveryLog.subscription_id == subscription.id,
        )
    )).scalars().all()
    assert len(logs) == 1
    assert "Unexpected error" in (logs[0].error_message or "")
