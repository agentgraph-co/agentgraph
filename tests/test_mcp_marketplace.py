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
MCP_CALL_URL = "/api/v1/mcp/tools/call"
AGENT_REGISTER_URL = "/api/v1/agents/register"

SELLER = {
    "email": "mcp_seller@example.com",
    "password": "Str0ngP@ss",
    "display_name": "MCPSeller",
}
BUYER = {
    "email": "mcp_buyer@example.com",
    "password": "Str0ngP@ss",
    "display_name": "MCPBuyer",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_mcp_create_listing(client: AsyncClient, db):
    """MCP tool: create a marketplace listing."""
    token, _ = await _setup_user(client, SELLER)

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_create_listing",
            "arguments": {
                "title": "Code Review Bot",
                "description": "Automated code review service",
                "category": "service",
                "pricing_model": "one_time",
                "price_cents": 500,
                "tags": ["code", "review"],
            },
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert data["result"]["title"] == "Code Review Bot"
    assert data["result"]["category"] == "service"


@pytest.mark.asyncio
async def test_mcp_purchase_listing(client: AsyncClient, db):
    """MCP tool: purchase a listing."""
    seller_token, _ = await _setup_user(client, SELLER)
    buyer_token, _ = await _setup_user(client, BUYER)

    # Create listing via MCP
    create_resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_create_listing",
            "arguments": {
                "title": "Free Bot",
                "description": "Free service",
                "category": "service",
            },
        },
        headers=_auth(seller_token),
    )
    listing_id = create_resp.json()["result"]["id"]

    # Purchase via MCP
    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_purchase_listing",
            "arguments": {
                "listing_id": listing_id,
                "notes": "Looking forward to it",
            },
        },
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert data["result"]["status"] == "completed"


@pytest.mark.asyncio
async def test_mcp_purchase_own_listing_fails(client: AsyncClient, db):
    """MCP tool: cannot purchase own listing."""
    token, _ = await _setup_user(client, SELLER)

    create_resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_create_listing",
            "arguments": {
                "title": "My Service",
                "description": "My own service",
                "category": "tool",
            },
        },
        headers=_auth(token),
    )
    listing_id = create_resp.json()["result"]["id"]

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_purchase_listing",
            "arguments": {"listing_id": listing_id},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is True
    assert "own" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_mcp_review_listing(client: AsyncClient, db):
    """MCP tool: review a listing."""
    seller_token, _ = await _setup_user(client, SELLER)
    buyer_token, _ = await _setup_user(client, BUYER)

    create_resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_create_listing",
            "arguments": {
                "title": "Reviewable Service",
                "description": "Test review",
                "category": "skill",
            },
        },
        headers=_auth(seller_token),
    )
    listing_id = create_resp.json()["result"]["id"]

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_review_listing",
            "arguments": {
                "listing_id": listing_id,
                "rating": 5,
                "text": "Excellent service!",
            },
        },
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert data["result"]["rating"] == 5
    assert data["result"]["updated"] is False


@pytest.mark.asyncio
async def test_mcp_flag_content(client: AsyncClient, db):
    """MCP tool: flag a post for moderation."""
    token, _ = await _setup_user(client, SELLER)

    # Create a post first
    post_resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_create_post",
            "arguments": {"content": "Some questionable content"},
        },
        headers=_auth(token),
    )
    post_id = post_resp.json()["result"]["id"]

    # Create another user to flag it
    flagger_token, _ = await _setup_user(client, BUYER)

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_flag_content",
            "arguments": {
                "target_type": "post",
                "target_id": post_id,
                "reason": "spam",
                "details": "Looks like spam",
            },
        },
        headers=_auth(flagger_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert data["result"]["reason"] == "spam"
    assert data["result"]["target_type"] == "post"


@pytest.mark.asyncio
async def test_mcp_create_evolution(client: AsyncClient, db):
    """MCP tool: agent records evolution via API key auth."""
    # Register agent
    reg_resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "EvoBot", "capabilities": ["chat"]},
    )
    api_key = reg_resp.json()["api_key"]

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_create_evolution",
            "arguments": {
                "version": "1.0.0",
                "change_type": "initial",
                "change_summary": "Initial release",
                "capabilities_snapshot": ["chat"],
            },
        },
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
    assert data["result"]["version"] == "1.0.0"
    assert data["result"]["change_type"] == "initial"


@pytest.mark.asyncio
async def test_mcp_create_evolution_human_fails(client: AsyncClient, db):
    """MCP tool: humans cannot record evolution."""
    token, _ = await _setup_user(client, SELLER)

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_create_evolution",
            "arguments": {
                "version": "1.0.0",
                "change_type": "initial",
                "change_summary": "Should fail",
            },
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is True
    assert "agent" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_mcp_tools_count(client: AsyncClient, db):
    """Verify all MCP tools are listed."""
    resp = await client.get("/api/v1/mcp/tools")
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    assert len(tools) == 31
