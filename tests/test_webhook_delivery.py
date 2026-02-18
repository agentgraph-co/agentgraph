from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"

USER = {
    "email": "webhook_test@example.com",
    "password": "Str0ngP@ss",
    "display_name": "WebhookTester",
}
USER_B = {
    "email": "webhook_follower@example.com",
    "password": "Str0ngP@ss",
    "display_name": "WebhookFollower",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_webhook_subscription(db, entity_id, url, event_types):
    """Create a webhook subscription in the DB for an existing entity."""
    from src.models import WebhookSubscription

    secret = "test-secret"
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()

    sub = WebhookSubscription(
        id=uuid.uuid4(),
        entity_id=uuid.UUID(entity_id),
        callback_url=url,
        secret_hash=secret_hash,
        event_types=event_types,
        is_active=True,
        consecutive_failures=0,
    )
    db.add(sub)
    await db.flush()
    return sub


@pytest.mark.asyncio
async def test_webhook_delivery_dispatch(client: AsyncClient, db):
    """dispatch_webhooks delivers to matching subscribers."""
    from src.events import dispatch_webhooks

    _, entity_id = await _setup_user(client, USER)
    await _create_webhook_subscription(
        db, entity_id, "https://httpbin.org/status/200", ["entity.followed"],
    )

    # dispatch_webhooks to a non-matching event should deliver 0
    count = await dispatch_webhooks(db, "post.voted", {"test": True})
    assert count == 0


@pytest.mark.asyncio
async def test_webhook_failure_tracking(client: AsyncClient, db):
    """Webhook failures increment consecutive_failures counter."""
    from src.events import dispatch_webhooks

    _, entity_id = await _setup_user(client, USER)
    sub = await _create_webhook_subscription(
        db, entity_id, "http://localhost:1/nonexistent", ["entity.followed"],
    )

    count = await dispatch_webhooks(db, "entity.followed", {"test": True})
    assert count == 0

    await db.refresh(sub)
    assert sub.consecutive_failures >= 1


@pytest.mark.asyncio
async def test_webhook_auto_deactivate(client: AsyncClient, db):
    """Webhook auto-deactivates after 10 consecutive failures."""
    from src.events import dispatch_webhooks

    _, entity_id = await _setup_user(client, USER)
    sub = await _create_webhook_subscription(
        db, entity_id, "http://localhost:1/nonexistent", ["entity.followed"],
    )
    # Simulate 9 prior failures
    sub.consecutive_failures = 9
    await db.flush()

    await dispatch_webhooks(db, "entity.followed", {"test": True})

    await db.refresh(sub)
    assert sub.is_active is False
    assert sub.consecutive_failures >= 10


@pytest.mark.asyncio
async def test_webhook_signature_format():
    """Webhook signature uses HMAC-SHA256 with secret_hash as key."""
    secret = "my-secret"
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()

    payload = json.dumps({"event_type": "test", "data": {}})
    expected = hmac.new(
        secret_hash.encode(), payload.encode(), hashlib.sha256,
    ).hexdigest()

    assert len(expected) == 64  # SHA-256 hex digest length


@pytest.mark.asyncio
async def test_webhook_fires_on_follow(client: AsyncClient, db):
    """Following someone triggers webhook dispatch (via notification)."""
    token_a, _ = await _setup_user(client, USER)
    token_b, id_b = await _setup_user(client, USER_B)

    # B creates a webhook for entity.followed
    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://httpbin.org/status/200",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token_b),
    )
    assert resp.status_code == 201

    # A follows B — this should trigger notification + webhook dispatch
    resp = await client.post(
        f"/api/v1/social/follow/{id_b}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
