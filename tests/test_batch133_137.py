"""Tests for Tasks #133-136: agent content filtering, submolt is_active,
notification/trust audit logging, moderation/marketplace audit logging."""
from __future__ import annotations

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

USER_A = {
    "email": "batch133a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch133A",
}
USER_B = {
    "email": "batch133b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch133B",
}

SPAM_TEXT = "buy cheap discount click here visit http://spam.com"


async def _grant_trust(db, entity_id: str, score: float = 0.5):
    """Give an entity a trust score so trust-gated endpoints work."""
    import uuid as _uuid

    from sqlalchemy import update as _sa_update

    from src.models import TrustScore

    await db.execute(
        _sa_update(TrustScore)
        .where(TrustScore.entity_id == _uuid.UUID(entity_id))
        .values(score=score, components={})
    )
    await db.flush()


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Task #133: Agent content filtering ---


@pytest.mark.asyncio
async def test_agent_create_rejects_spam_name(client, db):
    """Agent creation should reject spam display_name."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": SPAM_TEXT,
            "description": "Test agent",
            "capabilities": ["testing"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "rejected" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_agent_create_valid_succeeds(client, db):
    """Agent creation with valid name should succeed."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "Valid Agent Name",
            "description": "Test agent",
            "capabilities": ["testing"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_agent_update_rejects_spam_bio(client, db):
    """Agent update should reject spam bio_markdown."""
    token_a, _ = await _setup_user(client, USER_A)

    # Create agent
    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "Update Test Agent",
            "description": "For update test",
            "capabilities": ["testing"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    agent_id = resp.json()["agent"]["id"]

    # Update with spam bio
    resp = await client.patch(
        f"/api/v1/agents/{agent_id}",
        json={"bio_markdown": SPAM_TEXT},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "rejected" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_agent_update_creates_audit_log(client, db):
    """Agent update should create an audit log entry."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "Audit Agent",
            "description": "For audit test",
            "capabilities": ["testing"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    agent_id = resp.json()["agent"]["id"]

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}",
        json={"display_name": "Updated Audit Agent"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "agent.update")
    )
    logs = result.scalars().all()
    assert len(logs) >= 1


# --- Task #134: Submolt is_active checks ---


@pytest.mark.asyncio
async def test_submolt_members_accessible(client, db):
    """Submolt members endpoint should return list."""
    token_a, _ = await _setup_user(client, USER_A)

    # Create submolt
    resp = await client.post(
        "/api/v1/submolts",
        json={
            "name": "isactivetest",
            "display_name": "Is Active Test",
            "description": "Testing is_active",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    # List members
    resp = await client.get(
        "/api/v1/submolts/isactivetest/members",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert "members" in resp.json()


# --- Task #135: Notification audit logging ---


@pytest.mark.asyncio
async def test_notification_read_all_creates_audit_log(client, db):
    """Mark-all-as-read should create an audit log entry."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/notifications/read-all",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "notification.read_all")
    )
    logs = result.scalars().all()
    assert len(logs) >= 1


@pytest.mark.asyncio
async def test_trust_refresh_creates_audit_log(client, db):
    """Trust refresh should create an audit log entry."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.post(
        f"/api/v1/entities/{user_a_id}/trust/refresh",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "trust.refresh")
    )
    logs = result.scalars().all()
    assert len(logs) >= 1


# --- Task #136: Moderation and marketplace audit logging ---


@pytest.mark.asyncio
async def test_moderation_flag_creates_audit_log(client, db):
    """Creating a moderation flag should create an audit log entry."""
    token_a, user_a_id = await _setup_user(client, USER_A)
    token_b, user_b_id = await _setup_user(client, USER_B)

    # User A flags User B
    resp = await client.post(
        "/api/v1/moderation/flag",
        json={
            "target_type": "entity",
            "target_id": user_b_id,
            "reason": "spam",
            "details": "test flag",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "moderation.flag_created")
    )
    logs = result.scalars().all()
    assert len(logs) >= 1


@pytest.mark.asyncio
async def test_marketplace_create_listing_audit_log(client, db):
    """Creating a marketplace listing should create an audit log entry."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)

    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Audit Test Listing",
            "description": "For audit log test",
            "category": "service",
            "pricing_model": "free",
            "price_cents": 0,
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "marketplace.listing_create")
    )
    logs = result.scalars().all()
    assert len(logs) >= 1


@pytest.mark.asyncio
async def test_marketplace_purchase_audit_log(client, db):
    """Purchasing a listing should create an audit log entry."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)
    token_b, _ = await _setup_user(client, USER_B)

    # Create listing
    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Purchase Audit Listing",
            "description": "For purchase audit test",
            "category": "service",
            "pricing_model": "free",
            "price_cents": 0,
        },
        headers=_auth(token_a),
    )
    listing_id = resp.json()["id"]

    # Purchase
    resp = await client.post(
        f"/api/v1/marketplace/{listing_id}/purchase",
        json={"notes": "audit test"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "marketplace.purchase")
    )
    logs = result.scalars().all()
    assert len(logs) >= 1
