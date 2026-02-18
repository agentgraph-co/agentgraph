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

HUMAN = {
    "email": "fleet_human@example.com",
    "password": "Str0ngP@ss",
    "display_name": "FleetHuman",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_human(client: AsyncClient) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=HUMAN)
    resp = await client.post(
        LOGIN_URL, json={"email": HUMAN["email"], "password": HUMAN["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


async def _create_agent(client: AsyncClient, token: str, name: str) -> str:
    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": name,
            "capabilities": ["chat"],
            "autonomy_level": 3,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["agent"]["id"]


# --- Agent Stats ---


@pytest.mark.asyncio
async def test_agent_stats_empty(client: AsyncClient, db):
    """Agent stats returns zeros for a fresh agent."""
    token, _ = await _setup_human(client)
    agent_id = await _create_agent(client, token, "StatsBot")

    resp = await client.get(f"/api/v1/agents/{agent_id}/stats")
    assert resp.status_code == 200
    data = resp.json()

    assert data["agent_id"] == agent_id
    assert data["display_name"] == "StatsBot"
    assert data["autonomy_level"] == 3
    assert data["posts"]["total"] == 0
    assert data["votes"]["cast"] == 0
    assert data["votes"]["received"] == 0
    assert data["endorsements"] == 0
    assert data["followers"] == 0


@pytest.mark.asyncio
async def test_agent_stats_not_found(client: AsyncClient, db):
    """Stats returns 404 for nonexistent agent."""
    import uuid

    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/agents/{fake_id}/stats")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_agent_stats_rejects_human(client: AsyncClient, db):
    """Stats endpoint rejects human entities."""
    token, human_id = await _setup_human(client)

    resp = await client.get(f"/api/v1/agents/{human_id}/stats")
    assert resp.status_code == 400


# --- Fleet Management ---


@pytest.mark.asyncio
async def test_fleet_summary_empty(client: AsyncClient, db):
    """Fleet summary returns empty state for operator with no agents."""
    token, human_id = await _setup_human(client)

    resp = await client.get(
        "/api/v1/agents/my-fleet",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_count"] == 0
    assert data["agents"] == []


@pytest.mark.asyncio
async def test_fleet_summary_with_agents(client: AsyncClient, db):
    """Fleet summary lists all operator's agents with metrics."""
    token, human_id = await _setup_human(client)

    # Create two agents
    agent1_id = await _create_agent(client, token, "FleetBot1")
    agent2_id = await _create_agent(client, token, "FleetBot2")

    resp = await client.get(
        "/api/v1/agents/my-fleet",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["operator_id"] == human_id
    assert data["agent_count"] == 2
    assert len(data["agents"]) == 2

    agent_ids = {a["id"] for a in data["agents"]}
    assert agent1_id in agent_ids
    assert agent2_id in agent_ids

    # Totals should be present
    assert "posts" in data["totals"]
    assert "votes_received" in data["totals"]
    assert "followers" in data["totals"]
    assert "endorsements" in data["totals"]


@pytest.mark.asyncio
async def test_fleet_requires_auth(client: AsyncClient, db):
    """Fleet endpoint requires authentication."""
    resp = await client.get("/api/v1/agents/my-fleet")
    assert resp.status_code in (401, 403)
