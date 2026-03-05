"""Tests for the AutoGen bridge API endpoints.

Tests the router endpoints (config, tools, execute) — does NOT test the
AutoGen bridge module directly since AutoGen may not be installed.
"""
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


# ---------------------------------------------------------------------------
# GET /bridges/autogen/config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_autogen_config(client: AsyncClient):
    """Config endpoint returns AutoGen bridge metadata."""
    resp = await client.get(f"{BASE}/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["framework"] == "autogen"
    assert data["version"] == "1.0.0"
    assert "api_key" in data["auth_methods"]
    assert "jwt_bearer" in data["auth_methods"]
    assert data["tool_count"] > 0
    assert "description" in data


@pytest.mark.asyncio
async def test_autogen_config_tool_count_matches_tools(client: AsyncClient):
    """Config tool_count should match the actual number of tools returned."""
    config_resp = await client.get(f"{BASE}/config")
    tools_resp = await client.get(f"{BASE}/tools")
    assert config_resp.status_code == 200
    assert tools_resp.status_code == 200
    assert config_resp.json()["tool_count"] == len(tools_resp.json()["tools"])


# ---------------------------------------------------------------------------
# GET /bridges/autogen/tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_autogen_tools_list(client: AsyncClient):
    """Tools endpoint returns all expected tools with schemas."""
    resp = await client.get(f"{BASE}/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert "tools" in data
    tools = data["tools"]
    assert len(tools) >= 6

    tool_names = {t["name"] for t in tools}
    expected = {
        "search_entities",
        "get_trust_score",
        "create_post",
        "get_entity_profile",
        "attest_entity",
        "get_feed",
    }
    assert expected.issubset(tool_names)


@pytest.mark.asyncio
async def test_autogen_tools_have_valid_schemas(client: AsyncClient):
    """Each tool should have a name, description, and parameters dict."""
    resp = await client.get(f"{BASE}/tools")
    assert resp.status_code == 200
    for tool in resp.json()["tools"]:
        assert "name" in tool
        assert len(tool["name"]) > 0
        assert "description" in tool
        assert len(tool["description"]) > 0
        assert "parameters" in tool
        assert isinstance(tool["parameters"], dict)
        assert tool["parameters"].get("type") == "object"


# ---------------------------------------------------------------------------
# POST /bridges/autogen/execute — requires auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_requires_auth(client: AsyncClient):
    """Execute endpoint should reject unauthenticated requests."""
    resp = await client.post(
        f"{BASE}/execute",
        json={"tool_name": "get_feed", "arguments": {}},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_execute_unknown_tool(client: AsyncClient):
    """Execute with an unknown tool name should return 404."""
    token, _ = await _setup_user(client, "ag-u1@test.com", "User1")
    resp = await client.post(
        f"{BASE}/execute",
        json={"tool_name": "nonexistent_tool", "arguments": {}},
        headers=_auth(token),
    )
    assert resp.status_code == 404
    assert "Unknown tool" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_execute_get_feed(client: AsyncClient):
    """Execute get_feed tool returns posts list."""
    token, _ = await _setup_user(client, "ag-u2@test.com", "User2")
    resp = await client.post(
        f"{BASE}/execute",
        json={"tool_name": "get_feed", "arguments": {"limit": 5}},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool_name"] == "get_feed"
    assert data["is_error"] is False
    assert "posts" in data["result"]
    assert isinstance(data["result"]["posts"], list)


@pytest.mark.asyncio
async def test_execute_search_entities(client: AsyncClient):
    """Execute search_entities tool returns matching entities."""
    token, _ = await _setup_user(client, "ag-u3@test.com", "SearchAutoGen")
    resp = await client.post(
        f"{BASE}/execute",
        json={
            "tool_name": "search_entities",
            "arguments": {"query": "SearchAutoGen", "limit": 10},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool_name"] == "search_entities"
    assert data["is_error"] is False
    assert "entities" in data["result"]
    assert isinstance(data["result"]["entities"], list)


@pytest.mark.asyncio
async def test_execute_get_trust_score_not_found(client: AsyncClient):
    """Execute get_trust_score for a nonexistent entity returns null score."""
    token, _ = await _setup_user(client, "ag-u4@test.com", "User4")
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"{BASE}/execute",
        json={
            "tool_name": "get_trust_score",
            "arguments": {"entity_id": fake_id},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool_name"] == "get_trust_score"
    assert data["is_error"] is False
    assert data["result"]["trust_score"] is None


@pytest.mark.asyncio
async def test_execute_get_trust_score_invalid_uuid(client: AsyncClient):
    """Execute get_trust_score with invalid UUID returns error in result."""
    token, _ = await _setup_user(client, "ag-u5@test.com", "User5")
    resp = await client.post(
        f"{BASE}/execute",
        json={
            "tool_name": "get_trust_score",
            "arguments": {"entity_id": "not-a-uuid"},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data["result"]


@pytest.mark.asyncio
async def test_execute_create_post(client: AsyncClient):
    """Execute create_post tool creates a new post."""
    token, _ = await _setup_user(client, "ag-u6@test.com", "User6")
    resp = await client.post(
        f"{BASE}/execute",
        json={
            "tool_name": "create_post",
            "arguments": {"content": "Hello from AutoGen bridge!"},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool_name"] == "create_post"
    assert data["is_error"] is False
    assert "id" in data["result"]
    assert data["result"]["content"] == "Hello from AutoGen bridge!"


@pytest.mark.asyncio
async def test_execute_create_post_empty_content(client: AsyncClient):
    """Execute create_post with empty content returns error."""
    token, _ = await _setup_user(client, "ag-u7@test.com", "User7")
    resp = await client.post(
        f"{BASE}/execute",
        json={
            "tool_name": "create_post",
            "arguments": {"content": ""},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data["result"]


@pytest.mark.asyncio
async def test_execute_get_entity_profile(client: AsyncClient):
    """Execute get_entity_profile returns entity details."""
    token, entity_id = await _setup_user(
        client, "ag-u8@test.com", "AutoGen Test User",
    )
    resp = await client.post(
        f"{BASE}/execute",
        json={
            "tool_name": "get_entity_profile",
            "arguments": {"entity_id": entity_id},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool_name"] == "get_entity_profile"
    assert data["is_error"] is False
    assert data["result"]["id"] == entity_id
    assert data["result"]["display_name"] == "AutoGen Test User"


@pytest.mark.asyncio
async def test_execute_get_entity_profile_not_found(client: AsyncClient):
    """Execute get_entity_profile for nonexistent entity returns error."""
    token, _ = await _setup_user(client, "ag-u9@test.com", "User9")
    resp = await client.post(
        f"{BASE}/execute",
        json={
            "tool_name": "get_entity_profile",
            "arguments": {"entity_id": str(uuid.uuid4())},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data["result"]


@pytest.mark.asyncio
async def test_execute_attest_entity_self(client: AsyncClient):
    """Execute attest_entity on self should return error."""
    token, entity_id = await _setup_user(client, "ag-u10@test.com", "User10")
    resp = await client.post(
        f"{BASE}/execute",
        json={
            "tool_name": "attest_entity",
            "arguments": {
                "entity_id": entity_id,
                "attestation_type": "competent",
            },
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data["result"]
    assert "yourself" in data["result"]["error"].lower()


@pytest.mark.asyncio
async def test_execute_attest_entity_invalid_type(client: AsyncClient):
    """Execute attest_entity with invalid attestation_type returns error."""
    token, _ = await _setup_user(client, "ag-u11@test.com", "User11")
    resp = await client.post(
        f"{BASE}/execute",
        json={
            "tool_name": "attest_entity",
            "arguments": {
                "entity_id": str(uuid.uuid4()),
                "attestation_type": "invalid_type",
            },
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data["result"]


@pytest.mark.asyncio
async def test_execute_default_empty_arguments(client: AsyncClient):
    """Execute a tool with no arguments key should use defaults."""
    token, _ = await _setup_user(client, "ag-u12@test.com", "User12")
    resp = await client.post(
        f"{BASE}/execute",
        json={"tool_name": "get_feed"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool_name"] == "get_feed"
    assert data["is_error"] is False
