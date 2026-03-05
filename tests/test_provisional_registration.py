"""Tests for provisional agent registration and claim flow."""
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
AGENT_REGISTER_URL = "/api/v1/agents/register"
AGENT_CLAIM_URL = "/api/v1/agents/claim"

OPERATOR = {
    "email": "prov_operator@example.com",
    "password": "Str0ngP@ss",
    "display_name": "ProvOperator",
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
async def test_register_agent_without_operator_is_provisional(client: AsyncClient, db):
    """Agent registered without operator should be provisional."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "ProvBot", "capabilities": ["chat"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent"]["is_provisional"] is True
    assert data["claim_token"] is not None
    assert len(data["claim_token"]) > 20


@pytest.mark.asyncio
async def test_register_agent_with_operator_is_not_provisional(client: AsyncClient, db):
    """Agent registered with operator should NOT be provisional."""
    token, _ = await _setup_user(client, OPERATOR)

    resp = await client.post(
        AGENT_REGISTER_URL,
        json={
            "display_name": "FullBot",
            "capabilities": ["chat"],
            "operator_email": OPERATOR["email"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent"]["is_provisional"] is False
    assert data["claim_token"] is None


@pytest.mark.asyncio
async def test_claim_provisional_agent(client: AsyncClient, db):
    """Operator can claim a provisional agent using the claim token."""
    token, _ = await _setup_user(client, OPERATOR)

    # Register provisional agent
    reg_resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "ClaimBot", "capabilities": ["chat"]},
    )
    claim_token = reg_resp.json()["claim_token"]

    # Claim it
    claim_resp = await client.post(
        AGENT_CLAIM_URL,
        json={"claim_token": claim_token},
        headers=_auth(token),
    )
    assert claim_resp.status_code == 200
    data = claim_resp.json()
    assert data["agent"]["is_provisional"] is False
    assert data["agent"]["operator_id"] is not None
    assert "claimed successfully" in data["message"].lower()


@pytest.mark.asyncio
async def test_claim_invalid_token_returns_404(client: AsyncClient, db):
    """Invalid claim token should return 404."""
    token, _ = await _setup_user(client, OPERATOR)

    resp = await client.post(
        AGENT_CLAIM_URL,
        json={"claim_token": "totally-invalid-token"},
        headers=_auth(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_claim_already_claimed_returns_404(client: AsyncClient, db):
    """Claiming an already-claimed agent should return 404 (token cleared)."""
    token, _ = await _setup_user(client, OPERATOR)

    reg_resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "DoubleClaimBot", "capabilities": ["chat"]},
    )
    claim_token = reg_resp.json()["claim_token"]

    # First claim
    resp1 = await client.post(
        AGENT_CLAIM_URL,
        json={"claim_token": claim_token},
        headers=_auth(token),
    )
    assert resp1.status_code == 200

    # Second claim
    resp2 = await client.post(
        AGENT_CLAIM_URL,
        json={"claim_token": claim_token},
        headers=_auth(token),
    )
    assert resp2.status_code == 404


MCP_CALL_URL = "/api/v1/mcp/tools/call"


@pytest.mark.asyncio
async def test_provisional_agent_restricted_scopes(client: AsyncClient, db):
    """Provisional agents get limited scopes — cannot use feed:write."""
    reg_resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "NoPostBot", "capabilities": ["chat"]},
    )
    api_key = reg_resp.json()["api_key"]

    # Direct feed API blocked by scope (defense in depth)
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Hello from provisional bot!"},
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 403
    assert "scope" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_provisional_agent_restricted_marketplace_scopes(client: AsyncClient, db):
    """Provisional agents get limited scopes — cannot use marketplace:list."""
    reg_resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "NoListBot", "capabilities": ["chat"]},
    )
    api_key = reg_resp.json()["api_key"]

    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "My Service",
            "description": "A test listing",
            "category": "service",
        },
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 403
    assert "scope" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_provisional_agent_cannot_post_via_mcp(client: AsyncClient, db):
    """Provisional agents blocked from feed posting even via MCP."""
    reg_resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "NoMCPPostBot", "capabilities": ["chat"]},
    )
    api_key = reg_resp.json()["api_key"]

    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_create_post",
            "arguments": {"content": "Hello from provisional bot via MCP!"},
        },
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    # MCP returns is_error=True for provisional agents
    assert data["is_error"] is True
    assert "provisional" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_claimed_agent_can_post_via_mcp(client: AsyncClient, db):
    """After claiming, agent can create feed posts via MCP."""
    token, _ = await _setup_user(client, OPERATOR)

    # Register provisional
    reg_resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "CanPostBot", "capabilities": ["chat"]},
    )
    api_key = reg_resp.json()["api_key"]
    claim_token = reg_resp.json()["claim_token"]

    # Claim
    await client.post(
        AGENT_CLAIM_URL,
        json={"claim_token": claim_token},
        headers=_auth(token),
    )

    # Now MCP post should work
    resp = await client.post(
        MCP_CALL_URL,
        json={
            "name": "agentgraph_create_post",
            "arguments": {"content": "Hello from claimed bot!"},
        },
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_error"] is False
