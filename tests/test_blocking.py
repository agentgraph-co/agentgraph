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
SOCIAL_URL = "/api/v1/social"

USER_A = {
    "email": "block-a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "BlockA",
}
USER_B = {
    "email": "block-b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "BlockB",
}


async def _setup_user(
    client: AsyncClient, user: dict,
) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL,
        json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_block_entity(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    resp = await client.post(
        f"{SOCIAL_URL}/block/{id_b}", headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert "BlockB" in resp.json()["message"]


@pytest.mark.asyncio
async def test_block_removes_follow(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    # Follow first
    await client.post(
        f"{SOCIAL_URL}/follow/{id_b}", headers=_auth(token_a),
    )

    # Block removes the follow
    await client.post(
        f"{SOCIAL_URL}/block/{id_b}", headers=_auth(token_a),
    )

    # Following list should be empty
    resp = await client.get(f"{SOCIAL_URL}/following/{id_b}")
    assert len(resp.json()["entities"]) == 0 or all(
        e["display_name"] != "BlockA"
        for e in resp.json()["entities"]
    )


@pytest.mark.asyncio
async def test_blocked_cannot_follow(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # A blocks B
    await client.post(
        f"{SOCIAL_URL}/block/{id_b}", headers=_auth(token_a),
    )

    # B cannot follow A (A blocked B)
    resp = await client.post(
        f"{SOCIAL_URL}/follow/{id_a}", headers=_auth(token_b),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unblock(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    await client.post(
        f"{SOCIAL_URL}/block/{id_b}", headers=_auth(token_a),
    )

    resp = await client.delete(
        f"{SOCIAL_URL}/block/{id_b}", headers=_auth(token_a),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_blocked(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    await client.post(
        f"{SOCIAL_URL}/block/{id_b}", headers=_auth(token_a),
    )

    resp = await client.get(
        f"{SOCIAL_URL}/blocked", headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1
    blocked_ids = [
        b["entity_id"] for b in resp.json()["blocked"]
    ]
    assert id_b in blocked_ids


@pytest.mark.asyncio
async def test_cannot_block_self(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)

    resp = await client.post(
        f"{SOCIAL_URL}/block/{id_a}", headers=_auth(token_a),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_block_duplicate(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    await client.post(
        f"{SOCIAL_URL}/block/{id_b}", headers=_auth(token_a),
    )
    resp = await client.post(
        f"{SOCIAL_URL}/block/{id_b}", headers=_auth(token_a),
    )
    assert resp.status_code == 409
