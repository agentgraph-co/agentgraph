"""Tests for Tasks #119-122: audit logging on DM/endorsement/social/profile/DID,
WebSocket broadcasts for social events, rate limiting additions."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.main import app
from src.models import AuditLog, TrustScore


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

USER_A = {
    "email": "batch119a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch119A",
}
USER_B = {
    "email": "batch119b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch119B",
}


async def _setup_user(
    client: AsyncClient, user: dict, db: AsyncSession | None = None,
) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    eid = me.json()["id"]
    if db is not None:
        db.add(TrustScore(
            id=uuid.uuid4(), entity_id=uuid.UUID(eid), score=0.5,
            components={"verification": 0.3, "age": 0.1, "activity": 0.1},
        ))
        await db.flush()
    return token, eid


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Task #119: Audit logging on DM ---


@pytest.mark.asyncio
async def test_dm_send_creates_audit_log(client, db):
    """Sending a DM should create an audit log entry."""
    token_a, user_a_id = await _setup_user(client, USER_A, db)
    token_b, user_b_id = await _setup_user(client, USER_B, db)

    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": user_b_id, "content": "Hello there!"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "dm.send")
    )
    logs = result.scalars().all()
    assert len(logs) >= 1
    assert str(logs[-1].entity_id) == user_a_id


# --- Task #119: Audit logging on social ---


@pytest.mark.asyncio
async def test_follow_creates_audit_log(client, db):
    """Following an entity should create an audit log entry."""
    token_a, user_a_id = await _setup_user(client, USER_A)
    _, user_b_id = await _setup_user(client, USER_B)

    resp = await client.post(
        f"/api/v1/social/follow/{user_b_id}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "social.follow")
    )
    logs = result.scalars().all()
    assert len(logs) >= 1
    assert str(logs[-1].entity_id) == user_a_id


@pytest.mark.asyncio
async def test_block_creates_audit_log(client, db):
    """Blocking an entity should create an audit log entry."""
    token_a, _ = await _setup_user(client, USER_A)
    _, user_b_id = await _setup_user(client, USER_B)

    resp = await client.post(
        f"/api/v1/social/block/{user_b_id}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "social.block")
    )
    logs = result.scalars().all()
    assert len(logs) >= 1


# --- Task #119: Audit logging on endorsement ---


@pytest.mark.asyncio
async def test_endorsement_creates_audit_log(client, db):
    """Creating an endorsement should create an audit log entry."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # Create an agent
    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "Audit Agent",
            "description": "Testing audit logging",
            "capabilities": ["testing"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    agent_id = resp.json()["agent"]["id"]

    # Endorse as user B
    resp = await client.post(
        f"/api/v1/entities/{agent_id}/endorsements",
        json={"capability": "testing", "comment": "Endorsed!"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "endorsement.create")
    )
    logs = result.scalars().all()
    assert len(logs) >= 1


# --- Task #120: Audit logging on profile update ---


@pytest.mark.asyncio
async def test_profile_update_creates_audit_log(client, db):
    """Updating profile should create an audit log entry."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.patch(
        f"/api/v1/profiles/{user_a_id}",
        json={"bio_markdown": "Updated bio for audit test"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "profile.update")
    )
    logs = result.scalars().all()
    assert len(logs) >= 1
    assert str(logs[-1].entity_id) == user_a_id


# --- Task #121: WebSocket broadcasts for social ---


@pytest.mark.asyncio
async def test_follow_with_ws_broadcast_succeeds(client, db):
    """Follow endpoint should work with WebSocket broadcast code."""
    token_a, _ = await _setup_user(client, USER_A)
    _, user_b_id = await _setup_user(client, USER_B)

    resp = await client.post(
        f"/api/v1/social/follow/{user_b_id}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert "following" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_trust_refresh_with_ws_broadcast_succeeds(client, db):
    """Trust refresh should work with WebSocket broadcast code."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.post(
        f"/api/v1/entities/{user_a_id}/trust/refresh",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert "score" in resp.json()


# --- Task #122: Rate limiting on social GET endpoints ---


@pytest.mark.asyncio
async def test_social_following_accessible(client, db):
    """Social following endpoint should be accessible."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.get(
        f"/api/v1/social/following/{user_a_id}",
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_social_followers_accessible(client, db):
    """Social followers endpoint should be accessible."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.get(
        f"/api/v1/social/followers/{user_a_id}",
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_did_resolve_accessible(client, db):
    """DID resolve endpoint should be accessible with rate limiting."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.get(
        "/api/v1/did/resolve?uri=did:web:agentgraph.io:nonexistent",
    )
    # 404 is fine — we're testing the endpoint is reachable (not 500)
    assert resp.status_code in (200, 404)
