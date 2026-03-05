from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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

USER = {
    "email": "mktsort@example.com",
    "password": "Str0ngP@ss",
    "display_name": "MktSortUser",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: AsyncClient, db: AsyncSession) -> str:
    await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL,
        json={"email": USER["email"], "password": USER["password"]},
    )
    token = resp.json()["access_token"]
    # Grant sufficient trust for marketplace listing creation (threshold 0.15)
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    eid = uuid.UUID(me.json()["id"])
    ts = TrustScore(
        id=uuid.uuid4(), entity_id=eid, score=0.5,
        components={"verification": 0.3, "age": 0.1, "activity": 0.1},
    )
    db.add(ts)
    await db.flush()
    return token


@pytest.mark.asyncio
async def test_browse_sort_newest(client: AsyncClient, db):
    """Default sort is newest."""
    token = await _setup(client, db)

    # Create two listings
    await client.post(
        "/api/v1/marketplace",
        json={
            "title": "First Listing",
            "description": "Created first",
            "category": "service",
            "pricing_model": "free",
        },
        headers=_auth(token),
    )
    await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Second Listing",
            "description": "Created second",
            "category": "service",
            "pricing_model": "free",
        },
        headers=_auth(token),
    )

    resp = await client.get("/api/v1/marketplace?sort=newest")
    assert resp.status_code == 200
    listings = resp.json()["listings"]
    assert len(listings) >= 2
    titles = {item["title"] for item in listings}
    assert "First Listing" in titles
    assert "Second Listing" in titles


@pytest.mark.asyncio
async def test_browse_sort_price_asc(client: AsyncClient, db):
    """Sort by price ascending."""
    token = await _setup(client, db)

    await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Expensive",
            "description": "Costly",
            "category": "tool",
            "pricing_model": "one_time",
            "price_cents": 5000,
        },
        headers=_auth(token),
    )
    await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Cheap",
            "description": "Affordable",
            "category": "tool",
            "pricing_model": "one_time",
            "price_cents": 100,
        },
        headers=_auth(token),
    )

    resp = await client.get("/api/v1/marketplace?sort=price_asc")
    assert resp.status_code == 200
    listings = resp.json()["listings"]
    assert len(listings) >= 2
    prices = [item["price_cents"] for item in listings]
    assert prices == sorted(prices)


@pytest.mark.asyncio
async def test_browse_sort_price_desc(client: AsyncClient, db):
    """Sort by price descending."""
    token = await _setup(client, db)

    await client.post(
        "/api/v1/marketplace",
        json={
            "title": "DescExp",
            "description": "Costly",
            "category": "tool",
            "pricing_model": "one_time",
            "price_cents": 9000,
        },
        headers=_auth(token),
    )
    await client.post(
        "/api/v1/marketplace",
        json={
            "title": "DescCheap",
            "description": "Cheap",
            "category": "tool",
            "pricing_model": "one_time",
            "price_cents": 200,
        },
        headers=_auth(token),
    )

    resp = await client.get("/api/v1/marketplace?sort=price_desc")
    assert resp.status_code == 200
    listings = resp.json()["listings"]
    prices = [item["price_cents"] for item in listings]
    assert prices == sorted(prices, reverse=True)
