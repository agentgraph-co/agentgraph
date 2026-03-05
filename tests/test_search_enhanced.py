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

USER = {
    "email": "search_enh@example.com",
    "password": "Str0ngP@ss",
    "display_name": "SearchEnhUser",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _grant_trust(db, entity_id: str, score: float = 0.5):
    import uuid as _uuid
    ts = TrustScore(id=_uuid.uuid4(), entity_id=entity_id, score=score, components={})
    db.add(ts)
    await db.flush()


async def _setup(client: AsyncClient) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL,
        json={"email": USER["email"], "password": USER["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


@pytest.mark.asyncio
async def test_search_listings_endpoint(client: AsyncClient, db):
    """Listing search returns results matching query."""
    token, eid = await _setup(client)
    await _grant_trust(db, eid)

    # Create a listing
    await client.post(
        "/api/v1/marketplace",
        json={
            "title": "AI Code Reviewer",
            "description": "Automated code review for Python projects",
            "category": "service",
            "pricing_model": "subscription",
            "price_cents": 999,
        },
        headers=_auth(token),
    )

    resp = await client.get("/api/v1/search/listings?q=code+review")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert "AI Code Reviewer" in data[0]["title"]


@pytest.mark.asyncio
async def test_search_listings_filter_category(client: AsyncClient, db):
    """Listing search can filter by category."""
    token, eid = await _setup(client)
    await _grant_trust(db, eid)

    await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Unique Skill Widget",
            "description": "A special skill",
            "category": "skill",
            "pricing_model": "free",
        },
        headers=_auth(token),
    )

    # Search with wrong category
    resp = await client.get(
        "/api/v1/search/listings?q=Unique+Skill&category=integration",
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0

    # Search with correct category
    resp = await client.get(
        "/api/v1/search/listings?q=Unique+Skill&category=skill",
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_search_submolts_endpoint(client: AsyncClient, db):
    """Submolt search returns matching communities."""
    token, _ = await _setup(client)

    # Create submolt
    await client.post(
        "/api/v1/submolts",
        json={
            "name": "searchtest",
            "display_name": "Search Test Community",
            "description": "A community for testing search",
        },
        headers=_auth(token),
    )

    resp = await client.get("/api/v1/search/submolts?q=Search+Test")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["name"] == "searchtest"


@pytest.mark.asyncio
async def test_search_listings_no_results(client: AsyncClient, db):
    """Listing search returns empty list for unmatched query."""
    resp = await client.get(
        "/api/v1/search/listings?q=xyznonexistent99",
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0
