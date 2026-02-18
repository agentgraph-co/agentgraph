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


MCP_CALL_URL = "/api/v1/mcp/tools/call"

USER_A = {
    "email": "mcp_exp_a@example.com",
    "password": "Str0ngP@ss",
    "display_name": "McpExpA",
}
USER_B = {
    "email": "mcp_exp_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "McpExpB",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post("/api/v1/auth/register", json=user)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


# --- Tool discovery ---


@pytest.mark.asyncio
async def test_new_tools_listed(client: AsyncClient):
    """All 7 new MCP tools should appear in the tool listing."""
    resp = await client.get("/api/v1/mcp/tools")
    names = {t["name"] for t in resp.json()["tools"]}
    for name in [
        "agentgraph_send_message",
        "agentgraph_get_notifications",
        "agentgraph_bookmark_post",
        "agentgraph_list_submolts",
        "agentgraph_join_submolt",
        "agentgraph_browse_marketplace",
        "agentgraph_endorse_capability",
    ]:
        assert name in names, f"{name} missing from tool listing"


# --- send_message ---


@pytest.mark.asyncio
async def test_send_message_via_mcp(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_send_message",
            "arguments": {
                "recipient_id": id_b,
                "content": "Hello from MCP!",
            },
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert data["result"]["content"] == "Hello from MCP!"
    assert "conversation_id" in data["result"]


@pytest.mark.asyncio
async def test_send_message_self_fails(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_send_message",
            "arguments": {
                "recipient_id": id_a,
                "content": "Self-message",
            },
        },
        headers=_auth(token_a),
    )
    assert resp.json()["is_error"] is True
    assert resp.json()["error"]["code"] == "invalid_request"


# --- get_notifications ---


@pytest.mark.asyncio
async def test_get_notifications_via_mcp(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # B follows A to generate a notification
    await client.post(
        f"/api/v1/social/follow/{id_a}", headers=_auth(token_b),
    )

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_get_notifications",
            "arguments": {"unread_only": True},
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert data["result"]["unread_count"] >= 1
    assert len(data["result"]["notifications"]) >= 1


# --- bookmark_post ---


@pytest.mark.asyncio
async def test_bookmark_post_via_mcp(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    # Create a post via MCP
    create_resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_create_post",
            "arguments": {"content": "Bookmark me!"},
        },
        headers=_auth(token),
    )
    post_id = create_resp.json()["result"]["id"]

    # Bookmark it
    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_bookmark_post",
            "arguments": {"post_id": post_id},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["result"]["bookmarked"] is True

    # Toggle off
    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_bookmark_post",
            "arguments": {"post_id": post_id},
        },
        headers=_auth(token),
    )
    assert resp.json()["result"]["bookmarked"] is False


# --- list_submolts ---


@pytest.mark.asyncio
async def test_list_submolts_via_mcp(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    # Create a submolt first
    await client.post(
        "/api/v1/submolts",
        json={"name": "mcptest", "display_name": "MCP Test"},
        headers=_auth(token),
    )

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_list_submolts",
            "arguments": {"search": "mcp"},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert data["result"]["count"] >= 1
    assert data["result"]["submolts"][0]["name"] == "mcptest"


# --- join_submolt ---


@pytest.mark.asyncio
async def test_join_submolt_via_mcp(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # A creates submolt
    await client.post(
        "/api/v1/submolts",
        json={"name": "mcpjoin", "display_name": "MCP Join"},
        headers=_auth(token_a),
    )

    # B joins via MCP
    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_join_submolt",
            "arguments": {"submolt_name": "mcpjoin"},
        },
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    assert resp.json()["is_error"] is False
    assert "Joined" in resp.json()["result"]["message"]


@pytest.mark.asyncio
async def test_join_submolt_duplicate_fails(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    await client.post(
        "/api/v1/submolts",
        json={"name": "mcpdup", "display_name": "MCP Dup"},
        headers=_auth(token_a),
    )

    # B joins
    await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_join_submolt",
            "arguments": {"submolt_name": "mcpdup"},
        },
        headers=_auth(token_b),
    )

    # B joins again — should fail
    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_join_submolt",
            "arguments": {"submolt_name": "mcpdup"},
        },
        headers=_auth(token_b),
    )
    assert resp.json()["is_error"] is True
    assert resp.json()["error"]["code"] == "conflict"


# --- browse_marketplace ---


@pytest.mark.asyncio
async def test_browse_marketplace_via_mcp(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    # Create a listing
    await client.post(
        "/api/v1/marketplace",
        json={
            "title": "MCP NLP Service",
            "description": "NLP via MCP",
            "category": "service",
            "pricing_model": "free",
            "tags": ["nlp"],
        },
        headers=_auth(token),
    )

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_browse_marketplace",
            "arguments": {"category": "service"},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert data["result"]["count"] >= 1
    assert data["result"]["listings"][0]["title"] == "MCP NLP Service"


# --- endorse_capability ---


@pytest.mark.asyncio
async def test_endorse_capability_via_mcp(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_endorse_capability",
            "arguments": {
                "entity_id": id_b,
                "capability": "code_review",
            },
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert data["result"]["capability"] == "code_review"


@pytest.mark.asyncio
async def test_endorse_self_fails(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_endorse_capability",
            "arguments": {
                "entity_id": id_a,
                "capability": "testing",
            },
        },
        headers=_auth(token_a),
    )
    assert resp.json()["is_error"] is True
    assert resp.json()["error"]["code"] == "invalid_request"
