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
MCP_TOOLS_URL = "/api/v1/mcp/tools"
MCP_CALL_URL = "/api/v1/mcp/tools/call"

USER_A = {
    "email": "agent_user@mcp.com",
    "password": "Str0ngP@ss",
    "display_name": "MCPAgent",
}
USER_B = {
    "email": "target@mcp.com",
    "password": "Str0ngP@ss",
    "display_name": "Target",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register + login, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Tool discovery ---


@pytest.mark.asyncio
async def test_list_tools(client: AsyncClient):
    """Tool listing should be public (no auth required)."""
    resp = await client.get(MCP_TOOLS_URL)
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    assert len(tools) >= 10
    names = {t["name"] for t in tools}
    assert "agentgraph_create_post" in names
    assert "agentgraph_search" in names
    assert "agentgraph_follow" in names


@pytest.mark.asyncio
async def test_tool_has_input_schema(client: AsyncClient):
    resp = await client.get(MCP_TOOLS_URL)
    tools = resp.json()["tools"]
    for tool in tools:
        assert "inputSchema" in tool
        assert "type" in tool["inputSchema"]


# --- Tool execution ---


@pytest.mark.asyncio
async def test_create_post_via_mcp(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_create_post",
            "arguments": {"content": "Hello from MCP!"},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert data["result"]["content"] == "Hello from MCP!"
    assert "id" in data["result"]


@pytest.mark.asyncio
async def test_get_feed_via_mcp(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    # Create a post first
    await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_create_post",
            "arguments": {"content": "Feed test post"},
        },
        headers=_auth(token),
    )

    resp = await client.post(
        MCP_CALL_URL,
        json={"name": "agentgraph_get_feed", "arguments": {"limit": 10}},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert data["result"]["count"] >= 1


@pytest.mark.asyncio
async def test_follow_via_mcp(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_follow",
            "arguments": {"target_id": id_b},
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert resp.json()["is_error"] is False
    assert "Target" in resp.json()["result"]["message"]


@pytest.mark.asyncio
async def test_follow_self_via_mcp(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_follow",
            "arguments": {"target_id": id_a},
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert resp.json()["is_error"] is True
    assert resp.json()["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_search_via_mcp(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_search",
            "arguments": {"query": "MCP"},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert "entities" in data["result"]
    assert "posts" in data["result"]


@pytest.mark.asyncio
async def test_get_profile_via_mcp(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_get_profile",
            "arguments": {"entity_id": id_a},
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert data["result"]["display_name"] == "MCPAgent"


@pytest.mark.asyncio
async def test_unknown_tool(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        MCP_CALL_URL,
        json={"name": "nonexistent_tool", "arguments": {}},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_error"] is True
    assert resp.json()["error"]["code"] == "tool_not_found"


@pytest.mark.asyncio
async def test_unauthenticated_tool_call(client: AsyncClient):
    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_get_feed",
            "arguments": {},
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_vote_via_mcp(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    # Create a post
    create_resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_create_post",
            "arguments": {"content": "Vote me!"},
        },
        headers=_auth(token),
    )
    post_id = create_resp.json()["result"]["id"]

    # Vote on it
    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_vote",
            "arguments": {"post_id": post_id, "direction": "up"},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_error"] is False
    assert resp.json()["result"]["vote_count"] == 1


@pytest.mark.asyncio
async def test_get_followers_via_mcp(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # A follows B
    await client.post(
        MCP_CALL_URL,
        json={"name": "agentgraph_follow", "arguments": {"target_id": id_b}},
        headers=_auth(token_a),
    )

    # Get B's followers
    resp = await client.post(
        MCP_CALL_URL,
        json={"name": "agentgraph_get_followers", "arguments": {"entity_id": id_b}},
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert data["result"]["count"] == 1
    assert data["result"]["followers"][0]["display_name"] == "MCPAgent"
