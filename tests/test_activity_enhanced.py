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

USER_A = {
    "email": "activity_a@example.com",
    "password": "Str0ngP@ss",
    "display_name": "ActivityA",
}
USER_B = {
    "email": "activity_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "ActivityB",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL,
        json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


@pytest.mark.asyncio
async def test_activity_includes_posts(client: AsyncClient, db):
    """Activity timeline includes post events."""
    token, entity_id = await _setup_user(client, USER_A)

    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Activity test post"},
        headers=_auth(token),
    )

    resp = await client.get(f"/api/v1/activity/{entity_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    types = {a["type"] for a in data["activities"]}
    assert "post" in types


@pytest.mark.asyncio
async def test_activity_includes_follows(client: AsyncClient, db):
    """Activity timeline includes follow events."""
    token_a, id_a = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    await client.post(
        f"/api/v1/social/follow/{id_b}",
        headers=_auth(token_a),
    )

    resp = await client.get(f"/api/v1/activity/{id_a}")
    assert resp.status_code == 200
    types = {a["type"] for a in resp.json()["activities"]}
    assert "follow" in types


@pytest.mark.asyncio
async def test_activity_cursor_pagination(client: AsyncClient, db):
    """Activity supports cursor-based pagination via 'before' param."""
    token, entity_id = await _setup_user(client, USER_A)

    # Create multiple posts
    for i in range(5):
        await client.post(
            "/api/v1/feed/posts",
            json={"content": f"Post number {i}"},
            headers=_auth(token),
        )

    # First page with limit
    resp = await client.get(f"/api/v1/activity/{entity_id}?limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["activities"]) == 2
    assert "next_cursor" in data

    # Use a future cursor — should return all activities
    resp2 = await client.get(
        f"/api/v1/activity/{entity_id}?limit=10&before=2099-01-01T00:00:00Z",
    )
    assert resp2.status_code == 200
    assert resp2.json()["count"] >= 5

    # Use a past cursor — should return nothing
    resp3 = await client.get(
        f"/api/v1/activity/{entity_id}?limit=10&before=2000-01-01T00:00:00Z",
    )
    assert resp3.status_code == 200
    assert resp3.json()["count"] == 0


@pytest.mark.asyncio
async def test_activity_response_has_next_cursor(client: AsyncClient, db):
    """Response includes next_cursor field."""
    token, entity_id = await _setup_user(client, USER_A)

    resp = await client.get(f"/api/v1/activity/{entity_id}")
    assert resp.status_code == 200
    assert "next_cursor" in resp.json()
