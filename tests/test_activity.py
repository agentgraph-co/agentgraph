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
ME_URL = "/api/v1/auth/me"
FEED_URL = "/api/v1/feed/posts"
ACTIVITY_URL = "/api/v1/activity"

USER_A = {
    "email": "active@test.com",
    "password": "Str0ngP@ss",
    "display_name": "ActiveUser",
}
USER_B = {
    "email": "target@test.com",
    "password": "Str0ngP@ss",
    "display_name": "TargetUser",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_empty_activity(client: AsyncClient):
    _, entity_id = await _setup_user(client, USER_A)

    resp = await client.get(f"{ACTIVITY_URL}/{entity_id}")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_activity_shows_posts(client: AsyncClient):
    token, entity_id = await _setup_user(client, USER_A)

    await client.post(
        FEED_URL, json={"content": "My first post"}, headers=_auth(token)
    )

    resp = await client.get(f"{ACTIVITY_URL}/{entity_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    types = {a["type"] for a in data["activities"]}
    assert "post" in types


@pytest.mark.asyncio
async def test_activity_shows_follows(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    await client.post(
        f"/api/v1/social/follow/{id_b}", headers=_auth(token_a)
    )

    resp = await client.get(f"{ACTIVITY_URL}/{id_a}")
    assert resp.status_code == 200
    data = resp.json()
    types = {a["type"] for a in data["activities"]}
    assert "follow" in types


@pytest.mark.asyncio
async def test_activity_shows_votes(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # B creates a post
    post_resp = await client.post(
        FEED_URL, json={"content": "Vote me"}, headers=_auth(token_b)
    )
    post_id = post_resp.json()["id"]

    # A votes on it
    await client.post(
        f"{FEED_URL}/{post_id}/vote",
        json={"direction": "up"},
        headers=_auth(token_a),
    )

    resp = await client.get(f"{ACTIVITY_URL}/{id_a}")
    data = resp.json()
    types = {a["type"] for a in data["activities"]}
    assert "vote" in types


@pytest.mark.asyncio
async def test_activity_mixed_timeline(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # Post
    await client.post(
        FEED_URL, json={"content": "Hello"}, headers=_auth(token_a)
    )

    # Follow
    await client.post(
        f"/api/v1/social/follow/{id_b}", headers=_auth(token_a)
    )

    resp = await client.get(f"{ACTIVITY_URL}/{id_a}")
    data = resp.json()
    assert data["count"] >= 2


@pytest.mark.asyncio
async def test_activity_entity_not_found(client: AsyncClient):
    resp = await client.get(
        f"{ACTIVITY_URL}/00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_activity_limit(client: AsyncClient):
    token, entity_id = await _setup_user(client, USER_A)

    # Create several posts
    for i in range(5):
        await client.post(
            FEED_URL, json={"content": f"Post {i}"}, headers=_auth(token)
        )

    resp = await client.get(
        f"{ACTIVITY_URL}/{entity_id}", params={"limit": 3}
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 3
