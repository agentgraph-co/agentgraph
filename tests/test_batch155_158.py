"""Tests for Tasks #155-157: submolt display_name content filtering,
listing review deletion audit logging, moderation resolution webhooks."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.database import get_db
from src.main import app
from src.models import AuditLog


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
ME_URL = "/api/v1/auth/me"
FEED_URL = "/api/v1/feed/posts"
FLAG_URL = "/api/v1/moderation/flag"
FLAGS_URL = "/api/v1/moderation/flags"

USER_A = {
    "email": "batch155a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch155A",
}
USER_B = {
    "email": "batch155b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch155B",
}
ADMIN_USER = {
    "email": "batch155admin@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch155Admin",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


async def _make_admin(db, entity_id: str):
    from src.models import Entity

    entity = await db.get(Entity, uuid.UUID(entity_id))
    entity.is_admin = True
    await db.flush()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _grant_trust(db, entity_id: str, score: float = 0.5):
    """Give an entity a trust score so trust-gated endpoints work."""
    import uuid as _uuid

    from src.models import TrustScore

    ts = TrustScore(
        id=_uuid.uuid4(),
        entity_id=entity_id,
        score=score,
        components={},
    )
    db.add(ts)
    await db.flush()


# --- Task #155: Submolt display_name content filtering ---


@pytest.mark.asyncio
async def test_submolt_create_spam_display_name_rejected(client, db):
    """Creating a submolt with a spammy display name should be rejected."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/submolts",
        json={
            "name": "spamtest155",
            "display_name": "Buy cheap viagra click here",
            "description": "Legitimate description",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "display name rejected" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_submolt_create_clean_display_name_accepted(client, db):
    """Creating a submolt with a clean display name should succeed."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/submolts",
        json={
            "name": "cleantest155",
            "display_name": "Clean Community Name",
            "description": "A normal community",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    assert resp.json()["display_name"] == "Clean Community Name"


@pytest.mark.asyncio
async def test_submolt_update_spam_display_name_rejected(client, db):
    """Updating a submolt with a spammy display name should be rejected."""
    token_a, _ = await _setup_user(client, USER_A)

    # Create submolt first
    resp = await client.post(
        "/api/v1/submolts",
        json={
            "name": "updatespam155",
            "display_name": "Original Name",
            "description": "For update testing",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    # Try to update with spam display name
    resp = await client.patch(
        "/api/v1/submolts/updatespam155",
        json={"display_name": "Earn $5000 fast"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "display name rejected" in resp.json()["detail"].lower()


# --- Task #156: Listing review deletion audit logging ---


@pytest.mark.asyncio
async def test_delete_listing_review_creates_audit_log(client, db):
    """Deleting a listing review should create an audit log entry."""
    token_a, user_a_id = await _setup_user(client, USER_A)
    await _grant_trust(db, user_a_id)
    token_b, user_b_id = await _setup_user(client, USER_B)

    # Create a listing as user A
    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Audit Review Test",
            "description": "For testing review deletion audit",
            "category": "service",
            "pricing_model": "free",
            "tags": ["test"],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    # User B reviews the listing
    resp = await client.post(
        f"/api/v1/marketplace/{listing_id}/reviews",
        json={"rating": 4, "text": "Good service"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201

    # User B deletes the review
    resp = await client.delete(
        f"/api/v1/marketplace/{listing_id}/reviews",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200

    # Check audit log
    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == uuid.UUID(user_b_id),
            AuditLog.action == "marketplace.review_delete",
        )
    )
    logs = result.scalars().all()
    assert len(logs) >= 1
    assert str(listing_id) in str(logs[0].details)


# --- Task #157: Moderation resolution webhook dispatches ---


@pytest.mark.asyncio
async def test_webhook_accepts_moderation_resolved_event_type(client, db):
    """Webhooks should accept moderation.resolved as a valid event type."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)

    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://example.com/mod-hook",
            "event_types": ["moderation.resolved"],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    assert "moderation.resolved" in resp.json()["webhook"]["event_types"]


@pytest.mark.asyncio
async def test_webhook_accepts_appeal_resolved_event_type(client, db):
    """Webhooks should accept moderation.appeal_resolved as a valid event type."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)

    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://example.com/appeal-hook",
            "event_types": ["moderation.appeal_resolved"],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    assert "moderation.appeal_resolved" in resp.json()["webhook"]["event_types"]


@pytest.mark.asyncio
async def test_resolve_flag_dispatches_webhook(client, db):
    """Resolving a moderation flag should dispatch a moderation.resolved webhook."""
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    # Create a flag
    flag_resp = await client.post(
        FLAG_URL,
        json={"target_type": "entity", "target_id": id_b, "reason": "spam"},
        headers=_auth(token_a),
    )
    assert flag_resp.status_code == 201
    flag_id = flag_resp.json()["id"]

    # Resolve it and verify webhook dispatch was called
    with patch("src.events.dispatch_webhooks", new_callable=AsyncMock) as mock_dispatch:
        resp = await client.patch(
            f"{FLAGS_URL}/{flag_id}/resolve",
            json={"status": "dismissed", "resolution_note": "Not actually spam"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200

        mock_dispatch.assert_called_once()
        call_args = mock_dispatch.call_args
        assert call_args[0][1] == "moderation.resolved"
        payload = call_args[0][2]
        assert payload["flag_id"] == flag_id
        assert payload["resolution_status"] == "dismissed"


@pytest.mark.asyncio
async def test_resolve_appeal_dispatches_webhook(client, db):
    """Resolving a moderation appeal should dispatch moderation.appeal_resolved webhook."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    # Create a post, flag it, resolve it
    post_resp = await client.post(
        FEED_URL, json={"content": "Test appeal post"},
        headers=_auth(token_b),
    )
    assert post_resp.status_code == 201
    post_id = post_resp.json()["id"]

    flag_resp = await client.post(
        FLAG_URL,
        json={
            "target_type": "post",
            "target_id": post_id,
            "reason": "spam",
            "details": "Testing appeal webhook",
        },
        headers=_auth(token_a),
    )
    assert flag_resp.status_code == 201
    flag_id = flag_resp.json()["id"]

    # Admin resolves it
    resp = await client.patch(
        f"{FLAGS_URL}/{flag_id}/resolve",
        json={"status": "removed"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200

    # User B files appeal
    resp = await client.post(
        f"/api/v1/moderation/flags/{flag_id}/appeal",
        json={"reason": "This was not spam"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201
    appeal_id = resp.json()["id"]

    # Admin resolves appeal - verify webhook dispatched
    with patch("src.events.dispatch_webhooks", new_callable=AsyncMock) as mock_dispatch:
        resp = await client.patch(
            f"/api/v1/moderation/appeals/{appeal_id}",
            json={"action": "overturn", "note": "Reversed on appeal"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200

        # May be called multiple times (appeal webhook + notification webhook)
        assert mock_dispatch.call_count >= 1
        appeal_calls = [
            c for c in mock_dispatch.call_args_list
            if c[0][1] == "moderation.appeal_resolved"
        ]
        assert len(appeal_calls) == 1
        payload = appeal_calls[0][0][2]
        assert payload["appeal_id"] == str(appeal_id)
        assert payload["action"] == "overturn"
