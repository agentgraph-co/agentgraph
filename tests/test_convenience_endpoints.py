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

USER = {
    "email": "conv_ep@example.com",
    "password": "Str0ngP@ss",
    "display_name": "ConvUser",
}
ADMIN = {
    "email": "conv_admin@example.com",
    "password": "Str0ngP@ss",
    "display_name": "ConvAdmin",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


async def _make_admin(db, email: str):
    from sqlalchemy import select

    from src.models import Entity

    result = await db.execute(select(Entity).where(Entity.email == email))
    entity = result.scalar_one()
    entity.is_admin = True
    await db.flush()


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


# --- Notification Pagination ---


@pytest.mark.asyncio
async def test_notifications_pagination_offset(client: AsyncClient, db):
    """Notifications endpoint supports offset for pagination."""
    token, entity_id = await _setup(client, USER)

    # Get with offset=0
    resp = await client.get(
        "/api/v1/notifications",
        params={"offset": 0, "limit": 10},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "notifications" in data
    assert "total" in data


# --- My Listings ---


@pytest.mark.asyncio
async def test_my_listings(client: AsyncClient, db):
    """Authenticated user can see their own listings."""
    token, entity_id = await _setup(client, USER)
    await _grant_trust(db, entity_id)

    # Create a listing
    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "My Bot Service",
            "description": "I do things",
            "category": "service",
            "pricing_model": "free",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201

    # Get my listings
    resp = await client.get(
        "/api/v1/marketplace/my-listings",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(item["title"] == "My Bot Service" for item in data["listings"])


@pytest.mark.asyncio
async def test_my_listings_requires_auth(client: AsyncClient, db):
    """My listings endpoint requires authentication."""
    resp = await client.get("/api/v1/marketplace/my-listings")
    assert resp.status_code in (401, 403)


# --- Admin Force Verify Email ---


@pytest.mark.asyncio
async def test_admin_verify_email(client: AsyncClient, db):
    """Admin can force-verify an entity's email."""
    admin_token, _ = await _setup(client, ADMIN)
    await _make_admin(db, ADMIN["email"])
    user_token, user_id = await _setup(client, USER)

    # User email is not verified
    resp = await client.get(
        f"/api/v1/profiles/{user_id}", headers=_auth(user_token)
    )
    assert resp.json()["email_verified"] is False

    # Admin force-verifies
    resp = await client.post(
        f"/api/v1/admin/entities/{user_id}/verify-email",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert "verified" in resp.json()["message"].lower()

    # Check it's now verified
    resp = await client.get(
        f"/api/v1/profiles/{user_id}", headers=_auth(user_token)
    )
    assert resp.json()["email_verified"] is True


@pytest.mark.asyncio
async def test_admin_verify_already_verified(client: AsyncClient, db):
    """Admin verifying already-verified email returns appropriate message."""
    admin_token, _ = await _setup(client, ADMIN)
    await _make_admin(db, ADMIN["email"])
    _, user_id = await _setup(client, USER)

    # Verify once
    await client.post(
        f"/api/v1/admin/entities/{user_id}/verify-email",
        headers=_auth(admin_token),
    )

    # Verify again — should note already verified
    resp = await client.post(
        f"/api/v1/admin/entities/{user_id}/verify-email",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert "already" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_non_admin_cannot_verify_email(client: AsyncClient, db):
    """Non-admin cannot force-verify email."""
    token_a, id_a = await _setup(client, USER)
    _, id_b = await _setup(client, ADMIN)

    resp = await client.post(
        f"/api/v1/admin/entities/{id_b}/verify-email",
        headers=_auth(token_a),
    )
    assert resp.status_code == 403
