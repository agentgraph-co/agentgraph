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

USER_A = {
    "email": "alice@social.com",
    "password": "Str0ngP@ss",
    "display_name": "Alice",
}

USER_B = {
    "email": "bob@social.com",
    "password": "Str0ngP@ss",
    "display_name": "Bob",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register + login, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Follow tests ---


@pytest.mark.asyncio
async def test_follow(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    resp = await client.post(
        f"/api/v1/social/follow/{id_b}", headers=_auth(token_a)
    )
    assert resp.status_code == 200
    assert "Bob" in resp.json()["message"]


@pytest.mark.asyncio
async def test_follow_self_fails(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)

    resp = await client.post(
        f"/api/v1/social/follow/{id_a}", headers=_auth(token_a)
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_follow_duplicate_fails(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    await client.post(f"/api/v1/social/follow/{id_b}", headers=_auth(token_a))
    resp = await client.post(
        f"/api/v1/social/follow/{id_b}", headers=_auth(token_a)
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_unfollow(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    await client.post(f"/api/v1/social/follow/{id_b}", headers=_auth(token_a))
    resp = await client.delete(
        f"/api/v1/social/follow/{id_b}", headers=_auth(token_a)
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Unfollowed"


@pytest.mark.asyncio
async def test_unfollow_not_following_fails(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    resp = await client.delete(
        f"/api/v1/social/follow/{id_b}", headers=_auth(token_a)
    )
    assert resp.status_code == 404


# --- Following/Followers lists ---


@pytest.mark.asyncio
async def test_following_list(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    await client.post(f"/api/v1/social/follow/{id_b}", headers=_auth(token_a))

    resp = await client.get(f"/api/v1/social/following/{id_a}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["entities"][0]["display_name"] == "Bob"


@pytest.mark.asyncio
async def test_followers_list(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    await client.post(f"/api/v1/social/follow/{id_b}", headers=_auth(token_a))

    resp = await client.get(f"/api/v1/social/followers/{id_b}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["entities"][0]["display_name"] == "Alice"


# --- Social stats ---


@pytest.mark.asyncio
async def test_social_stats(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # A follows B
    await client.post(f"/api/v1/social/follow/{id_b}", headers=_auth(token_a))

    # Check A's stats
    resp = await client.get(f"/api/v1/social/stats/{id_a}")
    assert resp.status_code == 200
    assert resp.json()["following_count"] == 1
    assert resp.json()["followers_count"] == 0

    # Check B's stats
    resp = await client.get(f"/api/v1/social/stats/{id_b}")
    assert resp.json()["following_count"] == 0
    assert resp.json()["followers_count"] == 1


# --- Rate limiting ---


@pytest.mark.asyncio
async def test_auth_rate_limit(client: AsyncClient):
    """Auth endpoints should block after 5 attempts per minute."""
    for i in range(5):
        await client.post(
            LOGIN_URL,
            json={"email": f"test{i}@rate.com", "password": "Str0ngP@ss"},
        )

    # 6th attempt should be rate limited
    resp = await client.post(
        LOGIN_URL,
        json={"email": "test6@rate.com", "password": "Str0ngP@ss"},
    )
    assert resp.status_code == 429
