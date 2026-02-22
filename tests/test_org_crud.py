"""Tests for organization CRUD endpoints."""
from __future__ import annotations

import uuid

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


@pytest.mark.asyncio
async def test_create_organization(client, db):
    token, uid = await _create_user(client, "org1@test.com", "OrgCreator")
    h = {"Authorization": f"Bearer {token}"}
    resp = await client.post(PREFIX, json={
        "name": "test-org", "display_name": "Test Org",
    }, headers=h)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-org"
    assert data["display_name"] == "Test Org"
    assert data["tier"] == "free"
    assert data["member_count"] == 1
    assert data["created_by"] == uid


@pytest.mark.asyncio
async def test_create_org_duplicate_name(client, db):
    token, _ = await _create_user(client, "org2@test.com", "OrgCreator2")
    h = {"Authorization": f"Bearer {token}"}
    await client.post(PREFIX, json={"name": "dupe-org", "display_name": "Dupe"}, headers=h)
    resp = await client.post(PREFIX, json={"name": "dupe-org", "display_name": "Dupe2"}, headers=h)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_organization(client, db):
    token, _ = await _create_user(client, "org3@test.com", "OrgCreator3")
    h = {"Authorization": f"Bearer {token}"}
    body = {"name": "get-org", "display_name": "Get Org"}
    create_resp = await client.post(PREFIX, json=body, headers=h)
    org_id = create_resp.json()["id"]
    resp = await client.get(f"{PREFIX}/{org_id}", headers=h)
    assert resp.status_code == 200
    assert resp.json()["name"] == "get-org"
    assert resp.json()["member_count"] == 1


@pytest.mark.asyncio
async def test_get_org_not_found(client, db):
    token, _ = await _create_user(client, "org4@test.com", "OrgCreator4")
    h = {"Authorization": f"Bearer {token}"}
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"{PREFIX}/{fake_id}", headers=h)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_organization(client, db):
    token, _ = await _create_user(client, "org5@test.com", "OrgOwner5")
    h = {"Authorization": f"Bearer {token}"}
    cr = await client.post(PREFIX, json={"name": "upd-org", "display_name": "Upd"}, headers=h)
    org_id = cr.json()["id"]
    upd = {"display_name": "Updated", "tier": "pro"}
    resp = await client.patch(f"{PREFIX}/{org_id}", json=upd, headers=h)
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Updated"
    assert resp.json()["tier"] == "pro"


@pytest.mark.asyncio
async def test_update_org_unauthorized(client, db):
    token1, _ = await _create_user(client, "org6@test.com", "Owner6")
    token2, _ = await _create_user(client, "org6b@test.com", "NonMember6")
    h1 = {"Authorization": f"Bearer {token1}"}
    h2 = {"Authorization": f"Bearer {token2}"}
    cr = await client.post(PREFIX, json={"name": "priv-org", "display_name": "Priv"}, headers=h1)
    org_id = cr.json()["id"]
    resp = await client.patch(f"{PREFIX}/{org_id}", json={"display_name": "Hacked"}, headers=h2)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_add_member(client, db):
    token1, _ = await _create_user(client, "org7@test.com", "Owner7")
    token2, uid2 = await _create_user(client, "org7b@test.com", "Member7")
    h1 = {"Authorization": f"Bearer {token1}"}
    cr = await client.post(PREFIX, json={"name": "member-org", "display_name": "MO"}, headers=h1)
    org_id = cr.json()["id"]
    mbody = {"entity_id": uid2, "role": "member"}
    resp = await client.post(f"{PREFIX}/{org_id}/members", json=mbody, headers=h1)
    assert resp.status_code == 201
    assert resp.json()["entity_id"] == uid2
    assert resp.json()["role"] == "member"


@pytest.mark.asyncio
async def test_add_member_unauthorized(client, db):
    token1, _ = await _create_user(client, "org8@test.com", "Owner8")
    token2, uid2 = await _create_user(client, "org8b@test.com", "Non8")
    token3, uid3 = await _create_user(client, "org8c@test.com", "Target8")
    h1 = {"Authorization": f"Bearer {token1}"}
    h2 = {"Authorization": f"Bearer {token2}"}
    cr = await client.post(PREFIX, json={"name": "auth-org", "display_name": "AO"}, headers=h1)
    org_id = cr.json()["id"]
    resp = await client.post(f"{PREFIX}/{org_id}/members", json={"entity_id": uid3}, headers=h2)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_remove_member(client, db):
    token1, _ = await _create_user(client, "org9@test.com", "Owner9")
    _, uid2 = await _create_user(client, "org9b@test.com", "Mem9")
    h1 = {"Authorization": f"Bearer {token1}"}
    cr = await client.post(PREFIX, json={"name": "rm-org", "display_name": "RM"}, headers=h1)
    org_id = cr.json()["id"]
    await client.post(f"{PREFIX}/{org_id}/members", json={"entity_id": uid2}, headers=h1)
    resp = await client.delete(f"{PREFIX}/{org_id}/members/{uid2}", headers=h1)
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Member removed"


@pytest.mark.asyncio
async def test_remove_owner_fails(client, db):
    token1, uid1 = await _create_user(client, "org10@test.com", "Owner10")
    h1 = {"Authorization": f"Bearer {token1}"}
    cr = await client.post(PREFIX, json={"name": "own-org", "display_name": "OO"}, headers=h1)
    org_id = cr.json()["id"]
    resp = await client.delete(f"{PREFIX}/{org_id}/members/{uid1}", headers=h1)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_members(client, db):
    token1, uid1 = await _create_user(client, "org11@test.com", "Owner11")
    _, uid2 = await _create_user(client, "org11b@test.com", "Mem11")
    h1 = {"Authorization": f"Bearer {token1}"}
    cr = await client.post(PREFIX, json={"name": "list-org", "display_name": "LO"}, headers=h1)
    org_id = cr.json()["id"]
    await client.post(f"{PREFIX}/{org_id}/members", json={"entity_id": uid2}, headers=h1)
    resp = await client.get(f"{PREFIX}/{org_id}/members", headers=h1)
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


@pytest.mark.asyncio
async def test_org_stats(client, db):
    token1, _ = await _create_user(client, "org12@test.com", "Owner12")
    h1 = {"Authorization": f"Bearer {token1}"}
    cr = await client.post(PREFIX, json={"name": "stat-org", "display_name": "SO"}, headers=h1)
    org_id = cr.json()["id"]
    resp = await client.get(f"{PREFIX}/{org_id}/stats", headers=h1)
    assert resp.status_code == 200
    data = resp.json()
    assert "member_count" in data
    assert "agent_count" in data
    assert "avg_trust" in data
    assert "post_count" in data
    assert data["member_count"] >= 1
