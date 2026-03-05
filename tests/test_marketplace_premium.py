from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import TrustScore


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
    "email": "mkt_admin@example.com",
    "password": "Str0ngP@ss",
    "display_name": "MktAdmin",
}
USER = {
    "email": "mkt_user@example.com",
    "password": "Str0ngP@ss",
    "display_name": "MktUser",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _grant_trust(db, entity_id: str, score: float = 0.5):
    import uuid as _uuid
    ts = TrustScore(id=_uuid.uuid4(), entity_id=entity_id, score=score, components={})
    db.add(ts)
    await db.flush()


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


# --- Featured Listings ---


@pytest.mark.asyncio
async def test_featured_listings_endpoint(client: AsyncClient, db):
    """Featured endpoint returns featured listings."""
    admin_token, _ = await _setup(client, ADMIN)
    await _make_admin(db, ADMIN["email"])
    user_token, user_id = await _setup(client, USER)
    await _grant_trust(db, user_id)

    # Create a listing
    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Premium Bot",
            "description": "A premium bot service",
            "category": "service",
            "pricing_model": "subscription",
            "price_cents": 999,
        },
        headers=_auth(user_token),
    )
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    # Initially no featured listings
    resp = await client.get("/api/v1/marketplace/featured")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # Admin features the listing
    resp = await client.patch(
        f"/api/v1/admin/listings/{listing_id}/feature",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_featured"] is True

    # Now featured endpoint returns it
    resp = await client.get("/api/v1/marketplace/featured")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["listings"][0]["id"] == listing_id


@pytest.mark.asyncio
async def test_non_admin_cannot_feature(client: AsyncClient, db):
    """Non-admin cannot toggle featured status."""
    user_token, user_id = await _setup(client, USER)
    await _grant_trust(db, user_id)

    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "My Bot",
            "description": "A bot",
            "category": "tool",
            "pricing_model": "free",
        },
        headers=_auth(user_token),
    )
    listing_id = resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/listings/{listing_id}/feature",
        headers=_auth(user_token),
    )
    assert resp.status_code == 403


# --- Category Stats ---


@pytest.mark.asyncio
async def test_category_stats(client: AsyncClient, db):
    """Category stats returns breakdown of listings by category."""
    user_token, user_id = await _setup(client, USER)
    await _grant_trust(db, user_id)

    # Create listings in different categories
    for cat in ["service", "tool"]:
        await client.post(
            "/api/v1/marketplace",
            json={
                "title": f"A {cat}",
                "description": f"Test {cat}",
                "category": cat,
                "pricing_model": "free",
            },
            headers=_auth(user_token),
        )

    resp = await client.get("/api/v1/marketplace/categories/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_active_listings"] >= 2
    cats = {c["category"] for c in data["categories"]}
    assert "service" in cats
    assert "tool" in cats


# --- Featured Filter by Category ---


@pytest.mark.asyncio
async def test_featured_filter_by_category(client: AsyncClient, db):
    """Featured endpoint supports category filtering."""
    admin_token, _ = await _setup(client, ADMIN)
    await _make_admin(db, ADMIN["email"])
    user_token, user_id = await _setup(client, USER)
    await _grant_trust(db, user_id)

    # Create two featured listings in different categories
    for cat in ["service", "tool"]:
        resp = await client.post(
            "/api/v1/marketplace",
            json={
                "title": f"Featured {cat}",
                "description": f"A featured {cat}",
                "category": cat,
                "pricing_model": "free",
            },
            headers=_auth(user_token),
        )
        lid = resp.json()["id"]
        await client.patch(
            f"/api/v1/admin/listings/{lid}/feature",
            headers=_auth(admin_token),
        )

    # Filter by service
    resp = await client.get(
        "/api/v1/marketplace/featured",
        params={"category": "service"},
    )
    assert resp.status_code == 200
    assert all(
        item["category"] == "service"
        for item in resp.json()["listings"]
    )
