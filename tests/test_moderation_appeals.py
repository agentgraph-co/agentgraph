from __future__ import annotations

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

ADMIN = {
    "email": "appeal_admin@example.com",
    "password": "Str0ngP@ss",
    "display_name": "AppealAdmin",
}
USER_A = {
    "email": "appeal_a@example.com",
    "password": "Str0ngP@ss",
    "display_name": "AppealUserA",
}
USER_B = {
    "email": "appeal_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "AppealUserB",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL,
        json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


async def _make_admin(db, entity_id: str) -> None:
    from src.models import Entity
    entity = await db.get(Entity, uuid.UUID(entity_id))
    entity.is_admin = True
    await db.flush()


@pytest.mark.asyncio
async def test_appeal_resolved_flag(client: AsyncClient, db):
    """User can appeal a resolved moderation flag against their post."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)

    # A creates a post
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Perfectly fine content"},
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    # B flags the post
    resp = await client.post(
        "/api/v1/moderation/flag",
        json={
            "target_type": "post",
            "target_id": post_id,
            "reason": "spam",
            "details": "Looks spammy",
        },
        headers=_auth(token_b),
    )
    flag_id = resp.json()["id"]

    # Admin resolves (removes)
    await client.patch(
        f"/api/v1/moderation/flags/{flag_id}/resolve",
        json={"status": "removed", "resolution_note": "Spam confirmed"},
        headers=_auth(admin_token),
    )

    # A appeals
    resp = await client.post(
        f"/api/v1/moderation/flags/{flag_id}/appeal",
        json={"reason": "This was not spam, it was a legitimate post"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"
    appeal_id = resp.json()["id"]

    # Admin sees appeal
    resp = await client.get(
        "/api/v1/moderation/appeals",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1

    # Admin overturns
    resp = await client.patch(
        f"/api/v1/moderation/appeals/{appeal_id}",
        json={"action": "overturn", "note": "Review found content is fine"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "overturned"


@pytest.mark.asyncio
async def test_cannot_appeal_pending_flag(client: AsyncClient, db):
    """Cannot appeal a flag that is still pending."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # A creates a post
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Some content"},
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    # B flags
    resp = await client.post(
        "/api/v1/moderation/flag",
        json={"target_type": "post", "target_id": post_id, "reason": "spam"},
        headers=_auth(token_b),
    )
    flag_id = resp.json()["id"]

    # A tries to appeal pending flag
    resp = await client.post(
        f"/api/v1/moderation/flags/{flag_id}/appeal",
        json={"reason": "Not spam"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_non_target_cannot_appeal(client: AsyncClient, db):
    """Only the flagged entity/author can appeal."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)

    # A creates a post
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Content to flag"},
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    # B flags
    resp = await client.post(
        "/api/v1/moderation/flag",
        json={"target_type": "post", "target_id": post_id, "reason": "spam"},
        headers=_auth(token_b),
    )
    flag_id = resp.json()["id"]

    # Admin resolves
    await client.patch(
        f"/api/v1/moderation/flags/{flag_id}/resolve",
        json={"status": "removed"},
        headers=_auth(admin_token),
    )

    # B (not the author) tries to appeal
    resp = await client.post(
        f"/api/v1/moderation/flags/{flag_id}/appeal",
        json={"reason": "Unfair"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_uphold_appeal(client: AsyncClient, db):
    """Admin can uphold a moderation decision (deny appeal)."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)

    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Flaggable content"},
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    resp = await client.post(
        "/api/v1/moderation/flag",
        json={"target_type": "post", "target_id": post_id, "reason": "spam"},
        headers=_auth(token_b),
    )
    flag_id = resp.json()["id"]

    await client.patch(
        f"/api/v1/moderation/flags/{flag_id}/resolve",
        json={"status": "removed"},
        headers=_auth(admin_token),
    )

    resp = await client.post(
        f"/api/v1/moderation/flags/{flag_id}/appeal",
        json={"reason": "I disagree"},
        headers=_auth(token_a),
    )
    appeal_id = resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/moderation/appeals/{appeal_id}",
        json={"action": "uphold", "note": "Original decision stands"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "upheld"


@pytest.mark.asyncio
async def test_duplicate_appeal_rejected(client: AsyncClient, db):
    """Cannot submit duplicate pending appeal."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)

    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Dup appeal test"},
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    resp = await client.post(
        "/api/v1/moderation/flag",
        json={"target_type": "post", "target_id": post_id, "reason": "spam"},
        headers=_auth(token_b),
    )
    flag_id = resp.json()["id"]

    await client.patch(
        f"/api/v1/moderation/flags/{flag_id}/resolve",
        json={"status": "warned"},
        headers=_auth(admin_token),
    )

    # First appeal
    resp = await client.post(
        f"/api/v1/moderation/flags/{flag_id}/appeal",
        json={"reason": "First appeal"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    # Second appeal should be rejected
    resp = await client.post(
        f"/api/v1/moderation/flags/{flag_id}/appeal",
        json={"reason": "Second appeal"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 409
