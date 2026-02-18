"""Tests for Tasks #166-167: appeal content filtering/audit logging,
moderation endpoint rate limiting."""
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
ME_URL = "/api/v1/auth/me"
FEED_URL = "/api/v1/feed/posts"
FLAG_URL = "/api/v1/moderation/flag"
FLAGS_URL = "/api/v1/moderation/flags"

USER_A = {
    "email": "batch166a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch166A",
}
USER_B = {
    "email": "batch166b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch166B",
}
ADMIN_USER = {
    "email": "batch166admin@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch166Admin",
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


# --- Task #166: Appeal content filtering and audit logging ---


@pytest.mark.asyncio
async def test_appeal_spam_reason_rejected(client, db):
    """Filing an appeal with spam reason should be rejected."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    # Create a post, flag it, resolve it
    post_resp = await client.post(
        FEED_URL, json={"content": "Test appeal content filter"},
        headers=_auth(token_b),
    )
    assert post_resp.status_code == 201
    post_id = post_resp.json()["id"]

    flag_resp = await client.post(
        FLAG_URL,
        json={"target_type": "post", "target_id": post_id, "reason": "spam"},
        headers=_auth(token_a),
    )
    assert flag_resp.status_code == 201
    flag_id = flag_resp.json()["id"]

    resp = await client.patch(
        f"{FLAGS_URL}/{flag_id}/resolve",
        json={"status": "removed"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200

    # User B tries to appeal with spam reason
    resp = await client.post(
        f"/api/v1/moderation/flags/{flag_id}/appeal",
        json={"reason": "Buy cheap viagra click here now"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 400
    assert "appeal reason rejected" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_appeal_creates_audit_log(client, db):
    """Filing an appeal should create an audit log entry."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    # Create a post, flag it, resolve it
    post_resp = await client.post(
        FEED_URL, json={"content": "Test appeal audit log"},
        headers=_auth(token_b),
    )
    assert post_resp.status_code == 201
    post_id = post_resp.json()["id"]

    flag_resp = await client.post(
        FLAG_URL,
        json={"target_type": "post", "target_id": post_id, "reason": "spam"},
        headers=_auth(token_a),
    )
    assert flag_resp.status_code == 201
    flag_id = flag_resp.json()["id"]

    resp = await client.patch(
        f"{FLAGS_URL}/{flag_id}/resolve",
        json={"status": "removed"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200

    # User B files appeal
    resp = await client.post(
        f"/api/v1/moderation/flags/{flag_id}/appeal",
        json={"reason": "This was not spam, it was a legitimate post"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201

    # Check audit log
    result = await db.execute(
        select(AuditLog).where(
            AuditLog.entity_id == uuid.UUID(id_b),
            AuditLog.action == "moderation.appeal",
        )
    )
    logs = result.scalars().all()
    assert len(logs) >= 1


# --- Task #167: Rate limiting on moderation GET endpoints ---


@pytest.mark.asyncio
async def test_moderation_flags_list_has_rate_limit(client, db):
    """GET /moderation/flags should have rate limiting."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    resp = await client.get(
        "/api/v1/moderation/flags",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers


@pytest.mark.asyncio
async def test_moderation_stats_has_rate_limit(client, db):
    """GET /moderation/stats should have rate limiting."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    resp = await client.get(
        "/api/v1/moderation/stats",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers


@pytest.mark.asyncio
async def test_moderation_appeals_list_has_rate_limit(client, db):
    """GET /moderation/appeals should have rate limiting."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    resp = await client.get(
        "/api/v1/moderation/appeals",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers
