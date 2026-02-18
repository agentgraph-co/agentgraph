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
    "email": "graph_a@example.com",
    "password": "Str0ngP@ss",
    "display_name": "GraphA",
}
USER_B = {
    "email": "graph_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "GraphB",
}
USER_C = {
    "email": "graph_c@example.com",
    "password": "Str0ngP@ss",
    "display_name": "GraphC",
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
async def test_mutual_follows(client: AsyncClient, db):
    """Mutual follows returns entities both A and B follow."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)
    _, id_c = await _setup_user(client, USER_C)

    # A follows C, B follows C
    await client.post(
        f"/api/v1/social/follow/{id_c}",
        headers=_auth(token_a),
    )
    await client.post(
        f"/api/v1/social/follow/{id_c}",
        headers=_auth(token_b),
    )

    resp = await client.get(f"/api/v1/graph/mutual/{id_a}/{id_b}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    mutual_ids = [m["id"] for m in data["mutual_follows"]]
    assert id_c in mutual_ids


@pytest.mark.asyncio
async def test_mutual_follows_empty(client: AsyncClient, db):
    """Returns empty when no mutual follows exist."""
    token_a, id_a = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    resp = await client.get(f"/api/v1/graph/mutual/{id_a}/{id_b}")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_shortest_path_direct(client: AsyncClient, db):
    """Shortest path between directly connected entities."""
    token_a, id_a = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    # A follows B
    await client.post(
        f"/api/v1/social/follow/{id_b}",
        headers=_auth(token_a),
    )

    resp = await client.get(f"/api/v1/graph/path/{id_a}/{id_b}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["length"] == 1
    assert data["path"][0] == id_a
    assert data["path"][1] == id_b


@pytest.mark.asyncio
async def test_shortest_path_self(client: AsyncClient, db):
    """Path to self has length 0."""
    _, id_a = await _setup_user(client, USER_A)

    resp = await client.get(f"/api/v1/graph/path/{id_a}/{id_a}")
    assert resp.status_code == 200
    assert resp.json()["length"] == 0


@pytest.mark.asyncio
async def test_shortest_path_no_connection(client: AsyncClient, db):
    """Returns length -1 when no path exists."""
    _, id_a = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    resp = await client.get(f"/api/v1/graph/path/{id_a}/{id_b}")
    assert resp.status_code == 200
    assert resp.json()["length"] == -1
