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
    "email": "discover_user@example.com",
    "password": "Str0ngP@ss",
    "display_name": "DiscoverUser",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: AsyncClient) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL, json={"email": USER["email"], "password": USER["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


@pytest.mark.asyncio
async def test_discover_submolts_by_popularity(client: AsyncClient, db):
    """Discover endpoint sorts by popularity (member count) by default."""
    token, _ = await _setup(client)

    # Create two submolts
    await client.post(
        "/api/v1/submolts",
        json={
            "name": "popular-sub",
            "display_name": "Popular Sub",
            "tags": ["ai"],
        },
        headers=_auth(token),
    )
    await client.post(
        "/api/v1/submolts",
        json={
            "name": "quiet-sub",
            "display_name": "Quiet Sub",
            "tags": ["ai"],
        },
        headers=_auth(token),
    )

    resp = await client.get(
        "/api/v1/submolts/discover",
        params={"sort": "popular"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_discover_submolts_by_tag(client: AsyncClient, db):
    """Discover endpoint filters by tag."""
    token, _ = await _setup(client)

    await client.post(
        "/api/v1/submolts",
        json={
            "name": "ai-agents-sub",
            "display_name": "AI Agents",
            "tags": ["ai", "agents"],
        },
        headers=_auth(token),
    )
    await client.post(
        "/api/v1/submolts",
        json={
            "name": "cooking-sub",
            "display_name": "Cooking",
            "tags": ["food"],
        },
        headers=_auth(token),
    )

    # Filter by "ai" tag
    resp = await client.get(
        "/api/v1/submolts/discover",
        params={"tag": "ai"},
    )
    assert resp.status_code == 200
    data = resp.json()
    names = [s["name"] for s in data["submolts"]]
    assert "ai-agents-sub" in names
    assert "cooking-sub" not in names


@pytest.mark.asyncio
async def test_discover_submolts_alphabetical(client: AsyncClient, db):
    """Discover endpoint sorts alphabetically."""
    token, _ = await _setup(client)

    await client.post(
        "/api/v1/submolts",
        json={"name": "zebra-sub", "display_name": "Zebra"},
        headers=_auth(token),
    )
    await client.post(
        "/api/v1/submolts",
        json={"name": "alpha-sub", "display_name": "Alpha"},
        headers=_auth(token),
    )

    resp = await client.get(
        "/api/v1/submolts/discover",
        params={"sort": "alphabetical"},
    )
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()["submolts"]]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_trending_submolts_empty(client: AsyncClient, db):
    """Trending endpoint returns empty when no recent posts."""
    resp = await client.get("/api/v1/submolts/trending")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_trending_submolts_with_activity(client: AsyncClient, db):
    """Trending submolts reflect recent posting activity."""
    token, _ = await _setup(client)

    # Create a submolt and post in it
    resp = await client.post(
        "/api/v1/submolts",
        json={"name": "trend-sub", "display_name": "Trending Sub"},
        headers=_auth(token),
    )
    submolt_id = resp.json()["id"]

    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Trending post 1", "submolt_id": submolt_id},
        headers=_auth(token),
    )
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Trending post 2", "submolt_id": submolt_id},
        headers=_auth(token),
    )

    resp = await client.get("/api/v1/submolts/trending")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(s["name"] == "trend-sub" for s in data["submolts"])
