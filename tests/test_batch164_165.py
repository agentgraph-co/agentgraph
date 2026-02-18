"""Tests for Task #164: is_active filtering on agent stats counts."""
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
AGENT_REGISTER_URL = "/api/v1/agents/register"

USER_A = {
    "email": "batch164a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch164A",
}
USER_B = {
    "email": "batch164b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch164B",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_agent_stats_endpoint_accessible(client, db):
    """Agent stats endpoint should return proper structure."""
    # Register an agent
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={
            "display_name": "StatsBot164",
            "capabilities": ["analysis"],
            "autonomy_level": 2,
            "bio_markdown": "A stats test bot",
        },
    )
    assert resp.status_code == 201
    agent_id = resp.json()["agent"]["id"]

    # Get stats
    resp = await client.get(f"/api/v1/agents/{agent_id}/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "agent_id" in data
    assert "endorsements" in data
    assert "reviews" in data
    assert "followers" in data
    assert data["endorsements"] == 0
    assert data["followers"] == 0
    assert data["reviews"]["count"] == 0


@pytest.mark.asyncio
async def test_agent_stats_deactivated_returns_404(client, db):
    """Agent stats for deactivated agent should return 404."""
    token_a, _ = await _setup_user(client, USER_A)

    # Register an agent with operator
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={
            "display_name": "DeactBot164",
            "capabilities": ["test"],
            "operator_email": USER_A["email"],
        },
    )
    assert resp.status_code == 201
    agent_id = resp.json()["agent"]["id"]

    # Deactivate the agent
    resp = await client.delete(
        f"/api/v1/agents/{agent_id}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Stats should return 404
    resp = await client.get(f"/api/v1/agents/{agent_id}/stats")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fleet_summary_accessible(client, db):
    """Fleet summary endpoint should return proper structure."""
    token_a, _ = await _setup_user(client, USER_A)

    # Register an agent with operator
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={
            "display_name": "FleetBot164",
            "capabilities": ["chat"],
            "operator_email": USER_A["email"],
        },
    )
    assert resp.status_code == 201

    # Get fleet summary
    resp = await client.get(
        "/api/v1/agents/my-fleet",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "agent_count" in data
    assert data["agent_count"] >= 1
    assert "totals" in data
    assert "endorsements" in data["totals"]
    assert "followers" in data["totals"]
