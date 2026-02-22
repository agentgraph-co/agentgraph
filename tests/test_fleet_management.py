"""Tests for fleet management endpoints."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app

PREFIX = "/api/v1/organizations"


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _create_user(client, email, name):
    body = {"email": email, "password": "Str0ngP@ss1", "display_name": name}
    await client.post("/api/v1/auth/register", json=body)
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "Str0ngP@ss1"})
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


async def _create_org(client, token, name):
    h = {"Authorization": f"Bearer {token}"}
    resp = await client.post(PREFIX, json={"name": name, "display_name": name.title()}, headers=h)
    return resp.json()["id"]


async def _create_agent(client, token, org_id, name):
    """Register an agent and add it to the org."""
    h = {"Authorization": f"Bearer {token}"}
    resp = await client.post("/api/v1/agents", json={
        "display_name": name, "capabilities": ["test"],
    }, headers=h)
    agent_id = resp.json()["agent"]["id"]
    await client.post(f"{PREFIX}/{org_id}/members", json={"entity_id": agent_id}, headers=h)
    return agent_id


@pytest.mark.asyncio
async def test_fleet_dashboard_empty(client, db):
    token, _ = await _create_user(client, "fleet1@test.com", "Fleet1")
    org_id = await _create_org(client, token, "fleet-empty")
    h = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/{org_id}/fleet", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_agents"] == 0
    assert data["agents"] == []


@pytest.mark.asyncio
async def test_fleet_dashboard_with_agents(client, db):
    token, _ = await _create_user(client, "fleet2@test.com", "Fleet2")
    org_id = await _create_org(client, token, "fleet-agents")
    h = {"Authorization": f"Bearer {token}"}
    await _create_agent(client, token, org_id, "Agent1")
    resp = await client.get(f"{PREFIX}/{org_id}/fleet", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_agents"] >= 1
    assert len(data["agents"]) >= 1


@pytest.mark.asyncio
async def test_fleet_dashboard_unauthorized(client, db):
    token1, _ = await _create_user(client, "fleet3@test.com", "Fleet3")
    token2, _ = await _create_user(client, "fleet3b@test.com", "NonMem3")
    org_id = await _create_org(client, token1, "fleet-unauth")
    h2 = {"Authorization": f"Bearer {token2}"}
    resp = await client.get(f"{PREFIX}/{org_id}/fleet", headers=h2)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_bulk_enable_agents(client, db):
    token, _ = await _create_user(client, "fleet4@test.com", "Fleet4")
    org_id = await _create_org(client, token, "fleet-enable")
    h = {"Authorization": f"Bearer {token}"}
    agent_id = await _create_agent(client, token, org_id, "Agent4")
    # Disable first then enable
    ba_url = f"{PREFIX}/{org_id}/fleet/bulk-action"
    await client.post(ba_url, json={"entity_ids": [agent_id], "action": "disable"}, headers=h)
    resp = await client.post(ba_url, json={"entity_ids": [agent_id], "action": "enable"}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["affected"] == 1


@pytest.mark.asyncio
async def test_bulk_disable_agents(client, db):
    token, _ = await _create_user(client, "fleet5@test.com", "Fleet5")
    org_id = await _create_org(client, token, "fleet-disable")
    h = {"Authorization": f"Bearer {token}"}
    agent_id = await _create_agent(client, token, org_id, "Agent5")
    ba_url = f"{PREFIX}/{org_id}/fleet/bulk-action"
    payload = {"entity_ids": [agent_id], "action": "disable"}
    resp = await client.post(ba_url, json=payload, headers=h)
    assert resp.status_code == 200
    assert resp.json()["affected"] == 1


@pytest.mark.asyncio
async def test_bulk_action_unauthorized(client, db):
    token1, _ = await _create_user(client, "fleet6@test.com", "Fleet6")
    token2, uid2 = await _create_user(client, "fleet6b@test.com", "Mem6")
    org_id = await _create_org(client, token1, "fleet-bulkunauth")
    h1 = {"Authorization": f"Bearer {token1}"}
    h2 = {"Authorization": f"Bearer {token2}"}
    # Add as regular member (not admin)
    mbody = {"entity_id": uid2, "role": "member"}
    await client.post(f"{PREFIX}/{org_id}/members", json=mbody, headers=h1)
    ba_url = f"{PREFIX}/{org_id}/fleet/bulk-action"
    resp = await client.post(ba_url, json={"entity_ids": [], "action": "enable"}, headers=h2)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_bulk_action_empty_list(client, db):
    token, _ = await _create_user(client, "fleet7@test.com", "Fleet7")
    org_id = await _create_org(client, token, "fleet-emptylist")
    h = {"Authorization": f"Bearer {token}"}
    ba_url = f"{PREFIX}/{org_id}/fleet/bulk-action"
    resp = await client.post(ba_url, json={"entity_ids": [], "action": "enable"}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["affected"] == 0


@pytest.mark.asyncio
async def test_fleet_trust_averages(client, db):
    token, _ = await _create_user(client, "fleet8@test.com", "Fleet8")
    org_id = await _create_org(client, token, "fleet-trust")
    h = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/{org_id}/fleet", headers=h)
    assert resp.status_code == 200
    assert "total_trust_avg" in resp.json()


@pytest.mark.asyncio
async def test_fleet_includes_framework_source(client, db):
    token, _ = await _create_user(client, "fleet9@test.com", "Fleet9")
    org_id = await _create_org(client, token, "fleet-fw")
    h = {"Authorization": f"Bearer {token}"}
    await _create_agent(client, token, org_id, "FWAgent")
    resp = await client.get(f"{PREFIX}/{org_id}/fleet", headers=h)
    assert resp.status_code == 200
    agents = resp.json()["agents"]
    if agents:
        assert "framework_source" in agents[0]


@pytest.mark.asyncio
async def test_fleet_endpoint_requires_membership(client, db):
    token1, _ = await _create_user(client, "fleet10@test.com", "Fleet10")
    token2, _ = await _create_user(client, "fleet10b@test.com", "Non10")
    org_id = await _create_org(client, token1, "fleet-membership")
    h2 = {"Authorization": f"Bearer {token2}"}
    resp = await client.get(f"{PREFIX}/{org_id}/fleet", headers=h2)
    assert resp.status_code == 403
