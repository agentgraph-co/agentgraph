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
MARKET_URL = "/api/v1/marketplace"


async def _setup_user(client: AsyncClient, email: str, name: str) -> tuple[str, str]:
    await client.post(
        REGISTER_URL,
        json={"email": email, "password": "Str0ngP@ss", "display_name": name},
    )
    resp = await client.post(
        LOGIN_URL, json={"email": email, "password": "Str0ngP@ss"},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


LISTING = {
    "title": "Text Summarization Service",
    "description": "AI-powered text summarization for documents and articles",
    "category": "service",
    "tags": ["nlp", "summarization"],
    "pricing_model": "one_time",
    "price_cents": 500,
}


@pytest.mark.asyncio
async def test_create_listing(client: AsyncClient):
    token, entity_id = await _setup_user(client, "mk1@test.com", "Seller1")

    resp = await client.post(MARKET_URL, json=LISTING, headers=_auth(token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == LISTING["title"]
    assert data["category"] == "service"
    assert data["pricing_model"] == "one_time"
    assert data["price_cents"] == 500
    assert data["entity_id"] == entity_id


@pytest.mark.asyncio
async def test_browse_listings(client: AsyncClient):
    token, _ = await _setup_user(client, "mk2@test.com", "Seller2")

    await client.post(MARKET_URL, json=LISTING, headers=_auth(token))
    await client.post(
        MARKET_URL,
        json={**LISTING, "title": "Code Review Bot", "category": "tool"},
        headers=_auth(token),
    )

    resp = await client.get(MARKET_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_browse_filter_by_category(client: AsyncClient):
    token, _ = await _setup_user(client, "mk3@test.com", "Seller3")

    await client.post(MARKET_URL, json=LISTING, headers=_auth(token))
    await client.post(
        MARKET_URL,
        json={**LISTING, "title": "Tool X", "category": "tool"},
        headers=_auth(token),
    )

    resp = await client.get(MARKET_URL, params={"category": "service"})
    assert resp.status_code == 200
    for item in resp.json()["listings"]:
        assert item["category"] == "service"


@pytest.mark.asyncio
async def test_browse_search(client: AsyncClient):
    token, _ = await _setup_user(client, "mk4@test.com", "Seller4")

    await client.post(MARKET_URL, json=LISTING, headers=_auth(token))

    resp = await client.get(MARKET_URL, params={"search": "Summarization"})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_get_listing(client: AsyncClient):
    token, _ = await _setup_user(client, "mk5@test.com", "Seller5")

    create_resp = await client.post(MARKET_URL, json=LISTING, headers=_auth(token))
    listing_id = create_resp.json()["id"]

    resp = await client.get(f"{MARKET_URL}/{listing_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == LISTING["title"]


@pytest.mark.asyncio
async def test_get_listing_increments_views(client: AsyncClient):
    token, _ = await _setup_user(client, "mk6@test.com", "Seller6")

    create_resp = await client.post(MARKET_URL, json=LISTING, headers=_auth(token))
    listing_id = create_resp.json()["id"]

    # View as anonymous (no auth header)
    await client.get(f"{MARKET_URL}/{listing_id}")
    resp = await client.get(f"{MARKET_URL}/{listing_id}")
    assert resp.json()["view_count"] >= 2


@pytest.mark.asyncio
async def test_update_listing(client: AsyncClient):
    token, _ = await _setup_user(client, "mk7@test.com", "Seller7")

    create_resp = await client.post(MARKET_URL, json=LISTING, headers=_auth(token))
    listing_id = create_resp.json()["id"]

    resp = await client.patch(
        f"{MARKET_URL}/{listing_id}",
        json={"title": "Updated Title", "price_cents": 1000},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"
    assert resp.json()["price_cents"] == 1000


@pytest.mark.asyncio
async def test_update_listing_not_owner(client: AsyncClient):
    token_a, _ = await _setup_user(client, "mk8a@test.com", "SellerA")
    token_b, _ = await _setup_user(client, "mk8b@test.com", "SellerB")

    create_resp = await client.post(MARKET_URL, json=LISTING, headers=_auth(token_a))
    listing_id = create_resp.json()["id"]

    resp = await client.patch(
        f"{MARKET_URL}/{listing_id}",
        json={"title": "Hijacked"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_listing(client: AsyncClient):
    token, _ = await _setup_user(client, "mk9@test.com", "Seller9")

    create_resp = await client.post(MARKET_URL, json=LISTING, headers=_auth(token))
    listing_id = create_resp.json()["id"]

    resp = await client.delete(
        f"{MARKET_URL}/{listing_id}", headers=_auth(token),
    )
    assert resp.status_code == 200

    # Should not be visible anymore
    resp = await client.get(f"{MARKET_URL}/{listing_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_entity_listings(client: AsyncClient):
    token, entity_id = await _setup_user(client, "mk10@test.com", "Seller10")

    await client.post(MARKET_URL, json=LISTING, headers=_auth(token))
    await client.post(
        MARKET_URL,
        json={**LISTING, "title": "Service 2"},
        headers=_auth(token),
    )

    resp = await client.get(f"{MARKET_URL}/entity/{entity_id}")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


@pytest.mark.asyncio
async def test_free_listing(client: AsyncClient):
    token, _ = await _setup_user(client, "mk11@test.com", "FreeBot")

    resp = await client.post(
        MARKET_URL,
        json={
            "title": "Free Search Agent",
            "description": "Free-to-use search agent",
            "category": "skill",
            "pricing_model": "free",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert resp.json()["pricing_model"] == "free"
    assert resp.json()["price_cents"] == 0
