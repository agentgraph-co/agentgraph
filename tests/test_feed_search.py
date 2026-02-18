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
    "email": "feed_search@example.com",
    "password": "Str0ngP@ss",
    "display_name": "FeedSearcher",
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


@pytest.mark.asyncio
async def test_search_by_content(client: AsyncClient, db):
    """Search finds posts matching content."""
    token, _ = await _setup_user(client, USER)

    # Create posts
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Python is great for AI agents"},
        headers=_auth(token),
    )
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Rust is fast and safe"},
        headers=_auth(token),
    )

    # Search for "Python"
    resp = await client.get(
        "/api/v1/feed/search?q=Python",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["posts"]) == 1
    assert "Python" in data["posts"][0]["content"]


@pytest.mark.asyncio
async def test_search_no_results(client: AsyncClient, db):
    """Search returns empty when no match."""
    token, _ = await _setup_user(client, USER)

    resp = await client.get(
        "/api/v1/feed/search?q=xyznonexistent",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert len(resp.json()["posts"]) == 0


@pytest.mark.asyncio
async def test_search_min_votes_filter(client: AsyncClient, db):
    """Search can filter by minimum votes."""
    token, _ = await _setup_user(client, USER)

    await client.post(
        "/api/v1/feed/posts",
        json={"content": "A lowvote topic post"},
        headers=_auth(token),
    )

    # Search with min_votes=5 should return nothing
    resp = await client.get(
        "/api/v1/feed/search?q=lowvote&min_votes=5",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert len(resp.json()["posts"]) == 0

    # min_votes=0 should include it
    resp = await client.get(
        "/api/v1/feed/search?q=lowvote&min_votes=0",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert len(resp.json()["posts"]) == 1


@pytest.mark.asyncio
async def test_search_case_insensitive(client: AsyncClient, db):
    """Search is case-insensitive."""
    token, _ = await _setup_user(client, USER)

    await client.post(
        "/api/v1/feed/posts",
        json={"content": "AgentGraph Platform Discussion"},
        headers=_auth(token),
    )

    resp = await client.get(
        "/api/v1/feed/search?q=agentgraph",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert len(resp.json()["posts"]) == 1


@pytest.mark.asyncio
async def test_search_pagination(client: AsyncClient, db):
    """Search supports cursor-based pagination."""
    token, _ = await _setup_user(client, USER)

    for i in range(3):
        await client.post(
            "/api/v1/feed/posts",
            json={"content": f"Searchable topic number {i}"},
            headers=_auth(token),
        )

    resp = await client.get(
        "/api/v1/feed/search?q=Searchable&limit=2",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["posts"]) == 2
    assert data["next_cursor"] is not None

    # Get next page
    resp2 = await client.get(
        f"/api/v1/feed/search?q=Searchable&limit=2&cursor={data['next_cursor']}",
        headers=_auth(token),
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert len(data2["posts"]) == 1


@pytest.mark.asyncio
async def test_search_requires_query(client: AsyncClient, db):
    """Search requires q parameter."""
    token, _ = await _setup_user(client, USER)

    resp = await client.get(
        "/api/v1/feed/search",
        headers=_auth(token),
    )
    assert resp.status_code == 422
