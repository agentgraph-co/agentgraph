from __future__ import annotations

import uuid

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
GRAPH_URL = "/api/v1/graph"
SOCIAL_URL = "/api/v1/social"


async def _create_user(client: AsyncClient, email: str, name: str) -> tuple[str, str]:
    """Register + login, return (token, entity_id)."""
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


@pytest.mark.asyncio
async def test_graph_returns_nodes(client: AsyncClient):
    """Graph endpoint returns valid structure with created entities."""
    await _create_user(client, "g1@test.com", "GraphUser1")
    await _create_user(client, "g2@test.com", "GraphUser2")

    resp = await client.get(GRAPH_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_count"] >= 2
    names = {n["label"] for n in data["nodes"]}
    assert "GraphUser1" in names
    assert "GraphUser2" in names


@pytest.mark.asyncio
async def test_graph_with_follow_edges(client: AsyncClient):
    token_a, id_a = await _create_user(client, "ga@test.com", "UserA")
    _, id_b = await _create_user(client, "gb@test.com", "UserB")

    # A follows B
    await client.post(
        f"{SOCIAL_URL}/follow/{id_b}", headers=_auth(token_a),
    )

    resp = await client.get(GRAPH_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data["edge_count"] >= 1
    # Find our specific edge
    our_edge = [
        e for e in data["edges"]
        if e["source"] == id_a and e["target"] == id_b
    ]
    assert len(our_edge) == 1


@pytest.mark.asyncio
async def test_ego_graph(client: AsyncClient):
    token_a, id_a = await _create_user(client, "ea@test.com", "EgoA")
    token_b, id_b = await _create_user(client, "eb@test.com", "EgoB")
    _, id_c = await _create_user(client, "ec@test.com", "EgoC")

    # A follows B, B follows C
    await client.post(f"{SOCIAL_URL}/follow/{id_b}", headers=_auth(token_a))
    await client.post(f"{SOCIAL_URL}/follow/{id_c}", headers=_auth(token_b))

    # Ego graph depth=1 from A should show A and B
    resp = await client.get(f"{GRAPH_URL}/ego/{id_a}?depth=1")
    assert resp.status_code == 200
    data = resp.json()
    node_ids = {n["id"] for n in data["nodes"]}
    assert id_a in node_ids
    assert id_b in node_ids

    # Ego graph depth=2 from A should include C too
    resp = await client.get(f"{GRAPH_URL}/ego/{id_a}?depth=2")
    assert resp.status_code == 200
    data = resp.json()
    node_ids = {n["id"] for n in data["nodes"]}
    assert id_c in node_ids


@pytest.mark.asyncio
async def test_ego_graph_not_found(client: AsyncClient):
    fake_id = uuid.uuid4()
    resp = await client.get(f"{GRAPH_URL}/ego/{fake_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_network_stats(client: AsyncClient):
    token_a, id_a = await _create_user(client, "sa@test.com", "StatsA")
    _, id_b = await _create_user(client, "sb@test.com", "StatsB")
    _, id_c = await _create_user(client, "sc@test.com", "StatsC")

    await client.post(f"{SOCIAL_URL}/follow/{id_b}", headers=_auth(token_a))
    await client.post(f"{SOCIAL_URL}/follow/{id_c}", headers=_auth(token_a))

    resp = await client.get(f"{GRAPH_URL}/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_entities"] >= 3
    assert data["total_humans"] >= 3
    assert data["total_follows"] >= 2
    assert isinstance(data["avg_followers"], float)
    assert isinstance(data["most_followed"], list)
    assert isinstance(data["most_connected"], list)


@pytest.mark.asyncio
async def test_graph_type_filter(client: AsyncClient):
    await _create_user(client, "ft@test.com", "FilterUser")

    resp = await client.get(GRAPH_URL, params={"entity_type": "human"})
    assert resp.status_code == 200
    assert resp.json()["node_count"] >= 1
    # All nodes should be human
    for node in resp.json()["nodes"]:
        assert node["type"] == "human"


@pytest.mark.asyncio
async def test_graph_limit(client: AsyncClient):
    await _create_user(client, "lim@test.com", "LimitUser")

    resp = await client.get(GRAPH_URL, params={"limit": 1})
    assert resp.status_code == 200
    assert resp.json()["node_count"] == 1
