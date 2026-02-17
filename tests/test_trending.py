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
POSTS_URL = "/api/v1/feed/posts"
TRENDING_URL = "/api/v1/feed/trending"

USER = {
    "email": "trend@test.com",
    "password": "Str0ngP@ss",
    "display_name": "TrendUser",
}


async def _setup_user(client: AsyncClient, user: dict) -> str:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_trending_empty(client: AsyncClient):
    resp = await client.get(TRENDING_URL)
    assert resp.status_code == 200
    assert resp.json()["posts"] is not None


@pytest.mark.asyncio
async def test_trending_with_posts(client: AsyncClient):
    token = await _setup_user(client, USER)

    # Create posts
    await client.post(
        POSTS_URL,
        json={"content": "Popular post"},
        headers=_auth(token),
    )
    resp = await client.post(
        POSTS_URL,
        json={"content": "Another post"},
        headers=_auth(token),
    )
    post_id = resp.json()["id"]

    # Upvote the second post
    await client.post(
        f"{POSTS_URL}/{post_id}/vote",
        json={"direction": "up"},
        headers=_auth(token),
    )

    resp = await client.get(TRENDING_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["posts"]) >= 2
    # Most voted should be first
    assert data["posts"][0]["vote_count"] >= data["posts"][-1]["vote_count"]


@pytest.mark.asyncio
async def test_trending_time_window(client: AsyncClient):
    token = await _setup_user(client, USER)

    await client.post(
        POSTS_URL,
        json={"content": "Recent post"},
        headers=_auth(token),
    )

    # 1 hour window
    resp = await client.get(TRENDING_URL, params={"hours": 1})
    assert resp.status_code == 200

    # 7 day window
    resp = await client.get(TRENDING_URL, params={"hours": 168})
    assert resp.status_code == 200
