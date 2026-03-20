from __future__ import annotations

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

USER_A = {
    "email": "crud_a@example.com",
    "password": "Str0ngP@ss",
    "display_name": "CrudA",
}
USER_B = {
    "email": "crud_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "CrudB",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


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


# --- Feed author_id filter ---


@pytest.mark.asyncio
async def test_feed_filter_by_author(client: AsyncClient, db):
    """Feed can be filtered by author_id."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # A creates a post
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Post by A"},
        headers=_auth(token_a),
    )
    # B creates a post
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Post by B"},
        headers=_auth(token_b),
    )

    # Filter by A
    resp = await client.get(f"/api/v1/feed/posts?author_id={id_a}")
    assert resp.status_code == 200
    posts = resp.json()["posts"]
    assert len(posts) == 1
    assert posts[0]["content"] == "Post by A"


# --- Submolt ownership transfer ---


@pytest.mark.asyncio
async def test_transfer_ownership(client: AsyncClient, db):
    """Owner can transfer ownership to another member."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # Create submolt
    resp = await client.post(
        "/api/v1/submolts",
        json={"name": "transfertest", "display_name": "Transfer Test"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    # B joins
    await client.post(
        "/api/v1/submolts/transfertest/join", headers=_auth(token_b),
    )

    # Transfer ownership to B
    resp = await client.post(
        f"/api/v1/submolts/transfertest/transfer-owner/{id_b}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert "transferred" in resp.json()["message"].lower()

    # A should now be a moderator, B should be owner
    # A can no longer transfer (not owner)
    resp = await client.post(
        f"/api/v1/submolts/transfertest/transfer-owner/{id_b}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 403

    # A can now leave (no longer owner)
    resp = await client.post(
        "/api/v1/submolts/transfertest/leave", headers=_auth(token_a),
    )
    assert resp.status_code == 200


# --- Webhook update ---


@pytest.mark.asyncio
async def test_update_webhook(client: AsyncClient, db):
    """Webhook event types and URL can be updated."""
    token, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)

    # Create webhook
    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://example.com/hook",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    webhook_id = resp.json()["webhook"]["id"]

    # Update event types
    resp = await client.patch(
        f"/api/v1/webhooks/{webhook_id}",
        json={"event_types": ["entity.followed", "post.created"]},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert "post.created" in resp.json()["event_types"]

    # Update URL
    resp = await client.patch(
        f"/api/v1/webhooks/{webhook_id}",
        json={"callback_url": "https://new.example.com/hook"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert "new.example.com" in resp.json()["callback_url"]


# --- Notification delete ---


@pytest.mark.asyncio
async def test_delete_notification(client: AsyncClient, db):
    """Notification can be deleted."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # B follows A to trigger notification
    await client.post(
        f"/api/v1/social/follow/{id_a}", headers=_auth(token_b),
    )

    # A's notifications
    resp = await client.get(
        "/api/v1/notifications", headers=_auth(token_a),
    )
    assert resp.status_code == 200
    notifs = resp.json()["notifications"]
    assert len(notifs) >= 1
    notif_id = notifs[0]["id"]

    # Delete it
    resp = await client.delete(
        f"/api/v1/notifications/{notif_id}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Verify it's gone
    resp = await client.get(
        "/api/v1/notifications", headers=_auth(token_a),
    )
    ids = [n["id"] for n in resp.json()["notifications"]]
    assert notif_id not in ids


# --- Admin demote ---


@pytest.mark.asyncio
async def test_demote_admin(client: AsyncClient, db):
    """Admin can demote another admin."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # Make A admin directly
    from src.models import Entity
    entity_a = await db.get(Entity, id_a)
    entity_a.is_admin = True
    entity_b = await db.get(Entity, id_b)
    entity_b.is_admin = True
    await db.flush()

    # A demotes B
    resp = await client.patch(
        f"/api/v1/admin/entities/{id_b}/demote",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert "demoted" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_cannot_demote_self(client: AsyncClient, db):
    """Admin cannot demote themselves."""
    token_a, id_a = await _setup_user(client, USER_A)

    from src.models import Entity
    entity_a = await db.get(Entity, id_a)
    entity_a.is_admin = True
    await db.flush()

    resp = await client.patch(
        f"/api/v1/admin/entities/{id_a}/demote",
        headers=_auth(token_a),
    )
    assert resp.status_code == 400


# --- Marketplace tag filter ---


@pytest.mark.asyncio
async def test_marketplace_tag_filter(client: AsyncClient, db):
    """Marketplace listings can be filtered by tag."""
    token, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)

    # Create listings with different tags
    await client.post(
        "/api/v1/marketplace",
        json={
            "title": "NLP Service",
            "description": "Natural language processing",
            "category": "service",
            "pricing_model": "free",
            "tags": ["nlp", "ai"],
        },
        headers=_auth(token),
    )
    await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Image Service",
            "description": "Image processing",
            "category": "service",
            "pricing_model": "free",
            "tags": ["vision", "ai"],
        },
        headers=_auth(token),
    )

    # Filter by nlp tag
    resp = await client.get("/api/v1/marketplace?tag=nlp")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["listings"][0]["title"] == "NLP Service"

    # Filter by ai tag — both
    resp = await client.get("/api/v1/marketplace?tag=ai")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2
