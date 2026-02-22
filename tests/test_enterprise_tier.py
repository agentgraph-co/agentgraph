"""Tests for enterprise tier: audit export, usage metering, org API keys."""
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


async def _create_user(client, suffix=None):
    """Register a user and return (token, entity_id)."""
    sfx = suffix or uuid.uuid4().hex[:8]
    email = f"ent_{sfx}@test.com"
    body = {"email": email, "password": "Str0ngP@ss1", "display_name": f"User {sfx}"}
    await client.post("/api/v1/auth/register", json=body)
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Str0ngP@ss1"},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


async def _create_org(client, token, name=None):
    """Create an org and return the org dict."""
    name = name or f"org_{uuid.uuid4().hex[:8]}"
    h = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        PREFIX, json={"name": name, "display_name": f"Org {name}"}, headers=h,
    )
    assert resp.status_code == 201
    return resp.json()


# =============================================================================
# Audit Export Tests
# =============================================================================


@pytest.mark.asyncio
async def test_audit_export_json(client, db):
    """Export audit logs as JSON returns list."""
    token, uid = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"{PREFIX}/{org_id}/audit-export", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data
    assert "total" in data
    assert "period_days" in data
    assert isinstance(data["logs"], list)


@pytest.mark.asyncio
async def test_audit_export_csv(client, db):
    """Export audit logs as CSV returns text/csv."""
    token, uid = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        f"{PREFIX}/{org_id}/audit-export", params={"format": "csv"}, headers=h,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")


@pytest.mark.asyncio
async def test_audit_export_with_days_filter(client, db):
    """Export with days filter accepted."""
    token, _ = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        f"{PREFIX}/{org_id}/audit-export", params={"days": 7}, headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["period_days"] == 7


@pytest.mark.asyncio
async def test_audit_export_with_action_filter(client, db):
    """Export with action_filter parameter accepted."""
    token, _ = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        f"{PREFIX}/{org_id}/audit-export",
        params={"action_filter": "org.api_key"},
        headers=h,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["logs"], list)


@pytest.mark.asyncio
async def test_audit_export_non_member(client, db):
    """Non-member cannot export audit logs."""
    token_owner, _ = await _create_user(client)
    token_outsider, _ = await _create_user(client)
    org = await _create_org(client, token_owner)
    org_id = org["id"]

    resp = await client.get(
        f"{PREFIX}/{org_id}/audit-export",
        headers={"Authorization": f"Bearer {token_outsider}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audit_export_member_not_admin(client, db):
    """Regular member (not admin/owner) cannot export."""
    token_owner, _ = await _create_user(client)
    token_member, member_id = await _create_user(client)
    org = await _create_org(client, token_owner)
    org_id = org["id"]
    h_owner = {"Authorization": f"Bearer {token_owner}"}

    # Add as regular member
    await client.post(
        f"{PREFIX}/{org_id}/members",
        json={"entity_id": member_id, "role": "member"},
        headers=h_owner,
    )

    resp = await client.get(
        f"{PREFIX}/{org_id}/audit-export",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audit_export_empty_org(client, db):
    """Org with no audit activity returns empty list."""
    token, _ = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    # Export with very narrow action filter to get empty results
    resp = await client.get(
        f"{PREFIX}/{org_id}/audit-export",
        params={"action_filter": "nonexistent_action_xyz"},
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_audit_export_nonexistent_org(client, db):
    """Nonexistent org returns 404."""
    token, _ = await _create_user(client)
    h = {"Authorization": f"Bearer {token}"}
    fake_id = str(uuid.uuid4())

    resp = await client.get(f"{PREFIX}/{fake_id}/audit-export", headers=h)
    assert resp.status_code == 404


# =============================================================================
# Usage Metering Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_usage_stats(client, db):
    """Get usage stats returns expected fields."""
    token, _ = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"{PREFIX}/{org_id}/usage", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert "period_days" in data
    assert "api_calls" in data
    assert "active_members" in data
    assert "active_agents" in data
    assert "posts" in data


@pytest.mark.asyncio
async def test_usage_custom_days(client, db):
    """Usage endpoint accepts custom days parameter."""
    token, _ = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        f"{PREFIX}/{org_id}/usage", params={"days": 7}, headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["period_days"] == 7


@pytest.mark.asyncio
async def test_usage_non_member(client, db):
    """Non-member cannot view usage."""
    token_owner, _ = await _create_user(client)
    token_outsider, _ = await _create_user(client)
    org = await _create_org(client, token_owner)
    org_id = org["id"]

    resp = await client.get(
        f"{PREFIX}/{org_id}/usage",
        headers={"Authorization": f"Bearer {token_outsider}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_usage_member_not_admin(client, db):
    """Regular member cannot view usage stats."""
    token_owner, _ = await _create_user(client)
    token_member, member_id = await _create_user(client)
    org = await _create_org(client, token_owner)
    org_id = org["id"]
    h_owner = {"Authorization": f"Bearer {token_owner}"}

    await client.post(
        f"{PREFIX}/{org_id}/members",
        json={"entity_id": member_id, "role": "member"},
        headers=h_owner,
    )

    resp = await client.get(
        f"{PREFIX}/{org_id}/usage",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_usage_nonexistent_org(client, db):
    """Nonexistent org returns 404."""
    token, _ = await _create_user(client)
    h = {"Authorization": f"Bearer {token}"}
    fake_id = str(uuid.uuid4())

    resp = await client.get(f"{PREFIX}/{fake_id}/usage", headers=h)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_usage_reflects_activity(client, db):
    """Usage stats reflect actual activity (posts)."""
    token, uid = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    # Create a post to generate activity
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Test post for usage metering"},
        headers=h,
    )

    resp = await client.get(f"{PREFIX}/{org_id}/usage", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    # At minimum, the user has been active
    assert data["posts"] >= 1


# =============================================================================
# Org API Keys Tests
# =============================================================================


@pytest.mark.asyncio
async def test_create_org_api_key(client, db):
    """Create org API key returns key and metadata."""
    token, _ = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"{PREFIX}/{org_id}/api-keys",
        json={"label": "test-key"},
        headers=h,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert "key" in data
    assert data["key"].startswith("ag_org_")
    assert data["label"] == "test-key"
    assert data["organization_id"] == org_id


@pytest.mark.asyncio
async def test_key_only_shown_on_creation(client, db):
    """Key is only returned on creation, not in list."""
    token, _ = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        f"{PREFIX}/{org_id}/api-keys",
        json={"label": "once-key"},
        headers=h,
    )
    assert create_resp.status_code == 201
    assert "key" in create_resp.json()

    list_resp = await client.get(f"{PREFIX}/{org_id}/api-keys", headers=h)
    assert list_resp.status_code == 200
    keys = list_resp.json()["api_keys"]
    for k in keys:
        assert "key" not in k


@pytest.mark.asyncio
async def test_list_org_api_keys(client, db):
    """List org API keys returns all active keys."""
    token, _ = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    # Create two keys
    await client.post(
        f"{PREFIX}/{org_id}/api-keys",
        json={"label": "key-1"},
        headers=h,
    )
    await client.post(
        f"{PREFIX}/{org_id}/api-keys",
        json={"label": "key-2"},
        headers=h,
    )

    resp = await client.get(f"{PREFIX}/{org_id}/api-keys", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_revoke_org_api_key(client, db):
    """Revoke an org API key."""
    token, _ = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        f"{PREFIX}/{org_id}/api-keys",
        json={"label": "to-revoke"},
        headers=h,
    )
    key_id = create_resp.json()["id"]

    resp = await client.delete(
        f"{PREFIX}/{org_id}/api-keys/{key_id}", headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["detail"] == "API key revoked"


@pytest.mark.asyncio
async def test_revoked_key_not_in_list(client, db):
    """Revoked key should not appear in active key list."""
    token, _ = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        f"{PREFIX}/{org_id}/api-keys",
        json={"label": "revoke-me"},
        headers=h,
    )
    key_id = create_resp.json()["id"]

    await client.delete(f"{PREFIX}/{org_id}/api-keys/{key_id}", headers=h)

    list_resp = await client.get(f"{PREFIX}/{org_id}/api-keys", headers=h)
    key_ids = [k["id"] for k in list_resp.json()["api_keys"]]
    assert key_id not in key_ids


@pytest.mark.asyncio
async def test_api_key_non_member(client, db):
    """Non-member cannot create org API keys."""
    token_owner, _ = await _create_user(client)
    token_outsider, _ = await _create_user(client)
    org = await _create_org(client, token_owner)
    org_id = org["id"]

    resp = await client.post(
        f"{PREFIX}/{org_id}/api-keys",
        json={"label": "hack"},
        headers={"Authorization": f"Bearer {token_outsider}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_api_key_member_not_admin(client, db):
    """Regular member cannot create org API keys."""
    token_owner, _ = await _create_user(client)
    token_member, member_id = await _create_user(client)
    org = await _create_org(client, token_owner)
    org_id = org["id"]
    h_owner = {"Authorization": f"Bearer {token_owner}"}

    await client.post(
        f"{PREFIX}/{org_id}/members",
        json={"entity_id": member_id, "role": "member"},
        headers=h_owner,
    )

    resp = await client.post(
        f"{PREFIX}/{org_id}/api-keys",
        json={"label": "nope"},
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_api_key_nonexistent_org(client, db):
    """Nonexistent org returns 404 for API key creation."""
    token, _ = await _create_user(client)
    h = {"Authorization": f"Bearer {token}"}
    fake_id = str(uuid.uuid4())

    resp = await client.post(
        f"{PREFIX}/{fake_id}/api-keys",
        json={"label": "orphan"},
        headers=h,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_key(client, db):
    """Delete nonexistent key returns 404."""
    token, _ = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}
    fake_key_id = str(uuid.uuid4())

    resp = await client.delete(
        f"{PREFIX}/{org_id}/api-keys/{fake_key_id}", headers=h,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_key_custom_label_scopes(client, db):
    """Create key with custom label and scopes."""
    token, _ = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"{PREFIX}/{org_id}/api-keys",
        json={"label": "prod-key", "scopes": ["read", "write"]},
        headers=h,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["label"] == "prod-key"
    assert data["scopes"] == ["read", "write"]


# =============================================================================
# Compliance Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_compliance_report_still_works(client, db):
    """Compliance report endpoint still functions after changes."""
    token, _ = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"{PREFIX}/{org_id}/compliance", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert "org_info" in data
    assert "entity_summary" in data
    assert "security" in data
    assert "trust" in data
    assert "evolution" in data
    assert "audit_export" in data


@pytest.mark.asyncio
async def test_fleet_dashboard_still_works(client, db):
    """Fleet dashboard endpoint still functions after changes."""
    token, _ = await _create_user(client)
    org = await _create_org(client, token)
    org_id = org["id"]
    h = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"{PREFIX}/{org_id}/fleet", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_agents" in data
    assert "active_agents" in data
    assert "agents" in data
