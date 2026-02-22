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
ME_URL = "/api/v1/auth/me"
ADMIN_URL = "/api/v1/admin"
NOTIF_URL = "/api/v1/notifications"
MARKETPLACE_URL = "/api/v1/marketplace"

USER_A = {
    "email": "harden_a@example.com",
    "password": "Str0ngP@ss",
    "display_name": "HardenA",
}
USER_B = {
    "email": "harden_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "HardenB",
}
ADMIN_USER = {
    "email": "harden_admin@example.com",
    "password": "Str0ngP@ss",
    "display_name": "HardenAdmin",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
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


# --- Audit Trail ---


@pytest.mark.asyncio
async def test_agent_create_audit(client: AsyncClient, db):
    """Agent creation produces audit log entry."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "AuditBot",
            "capabilities": ["test"],
            "autonomy_level": 3,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201

    # Check audit log
    audit_resp = await client.get(
        "/api/v1/account/audit-log", headers=_auth(token),
    )
    actions = [e["action"] for e in audit_resp.json()["entries"]]
    assert "agent.create" in actions


@pytest.mark.asyncio
async def test_post_delete_audit(client: AsyncClient, db):
    """Post deletion produces audit log entry."""
    token, _ = await _setup_user(client, USER_A)

    # Create post
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Delete me"},
        headers=_auth(token),
    )
    post_id = resp.json()["id"]

    # Delete
    await client.delete(
        f"/api/v1/feed/posts/{post_id}", headers=_auth(token),
    )

    # Check audit log
    audit_resp = await client.get(
        "/api/v1/account/audit-log", headers=_auth(token),
    )
    actions = [e["action"] for e in audit_resp.json()["entries"]]
    assert "post.delete" in actions


# --- Notification Preferences ---


@pytest.mark.asyncio
async def test_get_default_preferences(client: AsyncClient):
    """Default preferences enable all notification kinds."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.get(
        f"{NOTIF_URL}/preferences", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["follow_enabled"] is True
    assert data["vote_enabled"] is True
    assert data["mention_enabled"] is True


@pytest.mark.asyncio
async def test_update_preferences(client: AsyncClient):
    """Can disable specific notification kinds."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.patch(
        f"{NOTIF_URL}/preferences",
        json={"vote_enabled": False, "follow_enabled": False},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["vote_enabled"] is False
    assert data["follow_enabled"] is False
    assert data["reply_enabled"] is True  # unchanged


@pytest.mark.asyncio
async def test_disabled_notification_not_created(client: AsyncClient):
    """Disabling follow notifications prevents them from being created."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # B disables follow notifications
    await client.patch(
        f"{NOTIF_URL}/preferences",
        json={"follow_enabled": False},
        headers=_auth(token_b),
    )

    # A follows B
    await client.post(
        f"/api/v1/social/follow/{id_b}", headers=_auth(token_a),
    )

    # B checks notifications — should have none for the follow
    resp = await client.get(NOTIF_URL, headers=_auth(token_b))
    follow_notifs = [
        n for n in resp.json()["notifications"] if n["kind"] == "follow"
    ]
    assert len(follow_notifs) == 0


# --- Featured Listing ---


@pytest.mark.asyncio
async def test_toggle_featured_listing(client: AsyncClient, db):
    """Admin can toggle listing featured status."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)
    user_token, _ = await _setup_user(client, USER_A)

    # Create listing
    resp = await client.post(
        MARKETPLACE_URL,
        json={
            "title": "Featured Bot",
            "description": "A great bot",
            "category": "service",
            "pricing_model": "free",
        },
        headers=_auth(user_token),
    )
    listing_id = resp.json()["id"]

    # Feature it
    resp = await client.patch(
        f"{ADMIN_URL}/listings/{listing_id}/feature",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_featured"] is True

    # Un-feature it
    resp = await client.patch(
        f"{ADMIN_URL}/listings/{listing_id}/feature",
        headers=_auth(admin_token),
    )
    assert resp.json()["is_featured"] is False


@pytest.mark.asyncio
async def test_featured_listing_non_admin(client: AsyncClient):
    """Non-admin cannot toggle featured status."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.patch(
        f"{ADMIN_URL}/listings/{uuid.uuid4()}/feature",
        headers=_auth(token),
    )
    assert resp.status_code == 403


# --- Suspend Entity ---


@pytest.mark.asyncio
async def test_suspend_entity(client: AsyncClient, db):
    """Admin can temporarily suspend an entity."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)
    user_token, user_id = await _setup_user(client, USER_B)

    resp = await client.patch(
        f"{ADMIN_URL}/entities/{user_id}/suspend",
        params={"days": 7},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert "suspended_until" in resp.json()

    # User can't auth now
    resp = await client.get(ME_URL, headers=_auth(user_token))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_suspend_self_fails(client: AsyncClient, db):
    """Admin cannot suspend themselves."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    resp = await client.patch(
        f"{ADMIN_URL}/entities/{admin_id}/suspend",
        params={"days": 7},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 400


# --- Trust Methodology ---


@pytest.mark.asyncio
async def test_trust_methodology_v2(client: AsyncClient):
    """Trust methodology reflects v2 with reputation weight."""
    resp = await client.get("/api/v1/trust/methodology")
    assert resp.status_code == 200
    text = resp.json()["methodology"]
    assert "0.35 * verification" in text
    assert "0.15 * reputation" in text
    assert "Reputation" in text
