"""Tests for compliance report endpoints."""
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


@pytest.mark.asyncio
async def test_compliance_report_basic(client, db):
    token, _ = await _create_user(client, "comp1@test.com", "Comp1")
    org_id = await _create_org(client, token, "comp-basic")
    h = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/{org_id}/compliance", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert "org_info" in data
    assert "entity_summary" in data
    assert "security" in data
    assert "trust" in data
    assert "evolution" in data
    assert "generated_at" in data


@pytest.mark.asyncio
async def test_compliance_report_includes_security(client, db):
    token, _ = await _create_user(client, "comp2@test.com", "Comp2")
    org_id = await _create_org(client, token, "comp-sec")
    h = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/{org_id}/compliance", headers=h)
    sec = resp.json()["security"]
    assert "total_scans" in sec
    assert "clean_count" in sec
    assert "warning_count" in sec
    assert "critical_count" in sec


@pytest.mark.asyncio
async def test_compliance_report_includes_trust(client, db):
    token, _ = await _create_user(client, "comp3@test.com", "Comp3")
    org_id = await _create_org(client, token, "comp-trust")
    h = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/{org_id}/compliance", headers=h)
    trust = resp.json()["trust"]
    assert "avg_score" in trust
    assert "min_score" in trust
    assert "max_score" in trust


@pytest.mark.asyncio
async def test_compliance_report_includes_evolution(client, db):
    token, _ = await _create_user(client, "comp4@test.com", "Comp4")
    org_id = await _create_org(client, token, "comp-evo")
    h = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/{org_id}/compliance", headers=h)
    evo = resp.json()["evolution"]
    assert "total_records" in evo
    assert "pending_approvals" in evo
    assert "risk_tier_distribution" in evo


@pytest.mark.asyncio
async def test_compliance_report_unauthorized(client, db):
    token1, _ = await _create_user(client, "comp5@test.com", "Comp5")
    token2, _ = await _create_user(client, "comp5b@test.com", "Non5")
    org_id = await _create_org(client, token1, "comp-unauth")
    h2 = {"Authorization": f"Bearer {token2}"}
    resp = await client.get(f"{PREFIX}/{org_id}/compliance", headers=h2)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_compliance_report_empty_org(client, db):
    token, _ = await _create_user(client, "comp6@test.com", "Comp6")
    org_id = await _create_org(client, token, "comp-empty")
    h = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/{org_id}/compliance", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["org_info"]["member_count"] >= 1


@pytest.mark.asyncio
async def test_compliance_report_requires_admin(client, db):
    token1, _ = await _create_user(client, "comp7@test.com", "Owner7")
    token2, uid2 = await _create_user(client, "comp7b@test.com", "Mem7")
    org_id = await _create_org(client, token1, "comp-admin")
    h1 = {"Authorization": f"Bearer {token1}"}
    h2 = {"Authorization": f"Bearer {token2}"}
    body = {"entity_id": uid2, "role": "member"}
    await client.post(f"{PREFIX}/{org_id}/members", json=body, headers=h1)
    resp = await client.get(f"{PREFIX}/{org_id}/compliance", headers=h2)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_compliance_report_timestamp(client, db):
    token, _ = await _create_user(client, "comp8@test.com", "Comp8")
    org_id = await _create_org(client, token, "comp-ts")
    h = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/{org_id}/compliance", headers=h)
    assert resp.status_code == 200
    assert "generated_at" in resp.json()
    assert "T" in resp.json()["generated_at"]  # ISO format
