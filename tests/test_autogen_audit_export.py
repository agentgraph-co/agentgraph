"""Tests for AutoGen bridge audit trail compliance export."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
BASE = "/api/v1/bridges/autogen"


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _setup_user(
    client: AsyncClient, email: str, name: str,
) -> tuple:
    """Register + login a test user; return (token, entity_id)."""
    await client.post(
        REGISTER_URL,
        json={"email": email, "password": "Str0ngP@ss1", "display_name": name},
    )
    resp = await client.post(
        LOGIN_URL, json={"email": email, "password": "Str0ngP@ss1"},
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- API endpoint tests ---


@pytest.mark.asyncio
async def test_audit_export_requires_auth(client: AsyncClient):
    """Audit export requires authentication."""
    resp = await client.get(f"{BASE}/audit-export")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_audit_export_empty(client: AsyncClient):
    """Audit export with no interactions returns empty list."""
    token, _ = await _setup_user(client, "ae-empty@test.com", "EmptyUser")
    resp = await client.get(
        f"{BASE}/audit-export",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["record_count"] == 0
    assert data["records"] == []
    assert data["format"] == "agentgraph_compliance_v1"
    assert "exported_at" in data
    assert "entity_id" in data


@pytest.mark.asyncio
async def test_audit_export_after_tool_execution(client: AsyncClient):
    """Audit export captures tool execution records."""
    token, entity_id = await _setup_user(
        client, "ae-tool@test.com", "ToolUser",
    )

    # Execute a tool to create an audit record
    await client.post(
        f"{BASE}/execute",
        json={"tool_name": "get_feed", "arguments": {"limit": 5}},
        headers=_auth(token),
    )

    # Now export the audit trail
    resp = await client.get(
        f"{BASE}/audit-export",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["record_count"] >= 1
    assert len(data["records"]) >= 1

    # Verify record structure
    record = data["records"][0]
    assert "id" in record
    assert "timestamp" in record
    assert "action" in record
    assert record["action"] == "bridges.autogen.execute"
    assert "details" in record
    assert record["details"]["tool_name"] == "get_feed"


@pytest.mark.asyncio
async def test_audit_export_with_limit(client: AsyncClient):
    """Audit export respects the limit parameter."""
    token, _ = await _setup_user(
        client, "ae-limit@test.com", "LimitUser",
    )

    # Execute two tools
    for _ in range(3):
        await client.post(
            f"{BASE}/execute",
            json={"tool_name": "get_feed", "arguments": {}},
            headers=_auth(token),
        )

    resp = await client.get(
        f"{BASE}/audit-export?limit=2",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["record_count"] <= 2


@pytest.mark.asyncio
async def test_audit_export_with_action_filter(client: AsyncClient):
    """Audit export can filter by action prefix."""
    token, _ = await _setup_user(
        client, "ae-filter@test.com", "FilterUser",
    )

    # Execute a tool
    await client.post(
        f"{BASE}/execute",
        json={"tool_name": "get_feed", "arguments": {}},
        headers=_auth(token),
    )

    # Filter for autogen actions — should find records
    resp = await client.get(
        f"{BASE}/audit-export?action_filter=bridges.autogen",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["record_count"] >= 1

    # Filter for a non-matching action — should be empty
    resp = await client.get(
        f"{BASE}/audit-export?action_filter=nonexistent",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["record_count"] == 0


# --- Direct function tests ---


@pytest.mark.asyncio
async def test_export_audit_trail_function_directly(db):
    """Test the export_audit_trail function directly."""
    from src.bridges.autogen_bridge import export_audit_trail

    fake_id = uuid.uuid4()
    result = await export_audit_trail(db, fake_id)

    assert result["entity_id"] == str(fake_id)
    assert result["format"] == "agentgraph_compliance_v1"
    assert result["record_count"] == 0
    assert result["records"] == []
    assert "exported_at" in result
