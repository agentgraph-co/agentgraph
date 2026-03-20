"""Tests for Tasks #151-153: submolt audit logging, webhook/trust audit logging,
is_active filtering in activity/evolution queries."""
from __future__ import annotations

import uuid

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
    "email": "batch151a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch151A",
}
USER_B = {
    "email": "batch151b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch151B",
}


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


# --- Task #151: Submolt audit logging ---


@pytest.mark.asyncio
async def test_submolt_join_creates_audit_log(client, db):
    """Joining a submolt should create an audit log entry."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    # Create a submolt
    resp = await client.post(
        "/api/v1/submolts",
        json={
            "name": "auditjoin",
            "display_name": "Audit Join Test",
            "description": "For audit log testing",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    # Second user joins
    token_b, user_b_id = await _setup_user(client, USER_B)
    resp = await client.post(
        "/api/v1/submolts/auditjoin/join",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200

    # Check audit log
    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == uuid.UUID(user_b_id),
            AuditLog.action == "submolt.join",
        )
    )
    logs = result.scalars().all()
    assert len(logs) >= 1


@pytest.mark.asyncio
async def test_submolt_leave_creates_audit_log(client, db):
    """Leaving a submolt should create an audit log entry."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    # Create a submolt
    resp = await client.post(
        "/api/v1/submolts",
        json={
            "name": "auditleave",
            "display_name": "Audit Leave Test",
            "description": "For audit log testing",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    # Second user joins then leaves
    token_b, user_b_id = await _setup_user(client, USER_B)
    resp = await client.post(
        "/api/v1/submolts/auditleave/join",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200

    resp = await client.post(
        "/api/v1/submolts/auditleave/leave",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200

    # Check audit log
    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == uuid.UUID(user_b_id),
            AuditLog.action == "submolt.leave",
        )
    )
    logs = result.scalars().all()
    assert len(logs) >= 1


# --- Task #152: Webhook activate/deactivate audit and trust contest audit ---


@pytest.mark.asyncio
async def test_webhook_activate_creates_audit_log(client, db):
    """Activating a webhook should create an audit log entry."""
    token_a, user_a_id = await _setup_user(client, USER_A)
    await _grant_trust(db, user_a_id)

    # Create a webhook
    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://example.com/hook",
            "event_types": ["post.created"],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    webhook_id = resp.json()["webhook"]["id"]

    # Deactivate then reactivate
    resp = await client.patch(
        f"/api/v1/webhooks/{webhook_id}/deactivate",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    resp = await client.patch(
        f"/api/v1/webhooks/{webhook_id}/activate",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Check audit logs
    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == uuid.UUID(user_a_id),
            AuditLog.action == "webhook.activate",
        )
    )
    assert len(result.scalars().all()) >= 1

    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == uuid.UUID(user_a_id),
            AuditLog.action == "webhook.deactivate",
        )
    )
    assert len(result.scalars().all()) >= 1


@pytest.mark.asyncio
async def test_trust_contest_creates_audit_log(client, db):
    """Contesting a trust score should create an audit log entry."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.post(
        f"/api/v1/entities/{user_a_id}/trust/contest",
        json={"reason": "My trust score seems inaccurate"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    # Check audit log
    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == uuid.UUID(user_a_id),
            AuditLog.action == "trust.contest",
        )
    )
    logs = result.scalars().all()
    assert len(logs) >= 1


# --- Task #153: Activity timeline accessible ---


@pytest.mark.asyncio
async def test_activity_timeline_accessible(client, db):
    """Activity timeline endpoint should be accessible."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.get(
        f"/api/v1/activity/{user_a_id}",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "activities" in data
    assert "count" in data


@pytest.mark.asyncio
async def test_activity_timeline_deactivated_returns_404(client, db):
    """Activity timeline for deactivated entity should return 404."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    # Deactivate
    resp = await client.post(
        "/api/v1/account/deactivate",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Activity should 404
    resp = await client.get(
        f"/api/v1/activity/{user_a_id}",
    )
    assert resp.status_code == 404
