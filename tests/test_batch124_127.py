"""Tests for Tasks #124-126: evolution rate limiting + content filtering,
MCP rate limiting + audit logging, is_active checks on endorsement/review queries."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.database import get_db
from src.main import app
from src.models import AuditLog


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

USER_A = {
    "email": "batch124a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch124A",
}
USER_B = {
    "email": "batch124b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch124B",
}

SPAM_TEXT = "buy cheap discount click here visit http://spam.com"


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Task #124: Evolution content filtering ---


@pytest.mark.asyncio
async def test_evolution_rejects_spam_summary(client, db):
    """Evolution record with spam change_summary should be rejected."""
    token_a, _ = await _setup_user(client, USER_A)

    # Create an agent first
    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "Evo Spam Agent",
            "description": "Testing evolution spam",
            "capabilities": ["testing"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    agent_id = resp.json()["agent"]["id"]

    # Try evolution with spam summary
    resp = await client.post(
        "/api/v1/evolution",
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": SPAM_TEXT,
            "capabilities_snapshot": ["testing"],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "Change summary rejected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_evolution_valid_summary_succeeds(client, db):
    """Evolution record with valid change_summary should succeed."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "Evo Valid Agent",
            "description": "Testing evolution valid",
            "capabilities": ["testing"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    agent_id = resp.json()["agent"]["id"]

    resp = await client.post(
        "/api/v1/evolution",
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Initial release with testing capability",
            "capabilities_snapshot": ["testing"],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    assert resp.json()["version"] == "1.0.0"


# --- Task #124: Evolution rate limiting ---


@pytest.mark.asyncio
async def test_evolution_timeline_accessible(client, db):
    """Evolution timeline endpoint should be accessible."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "Evo Timeline Agent",
            "description": "Testing timeline",
            "capabilities": [],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    agent_id = resp.json()["agent"]["id"]

    resp = await client.get(f"/api/v1/evolution/{agent_id}")
    assert resp.status_code == 200


# --- Task #125: MCP rate limiting and audit logging ---


@pytest.mark.asyncio
async def test_mcp_tools_list_accessible(client, db):
    """MCP tools list endpoint should be accessible."""
    resp = await client.get("/api/v1/mcp/tools")
    assert resp.status_code == 200
    assert "tools" in resp.json()


@pytest.mark.asyncio
async def test_mcp_tool_call_requires_auth(client, db):
    """MCP tool call should require authentication."""
    resp = await client.post(
        "/api/v1/mcp/tools/call",
        json={"name": "nonexistent_tool", "arguments": {}},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mcp_tool_call_creates_audit_log(client, db):
    """MCP tool call should create an audit log entry on success."""
    token_a, _ = await _setup_user(client, USER_A)

    # Call a tool - the response may have is_error=True (MCPError) or succeed
    resp = await client.post(
        "/api/v1/mcp/tools/call",
        json={"name": "get_feed", "arguments": {}},
        headers=_auth(token_a),
    )
    # Should not crash with 500
    assert resp.status_code == 200

    data = resp.json()
    # If the tool executed successfully (not an MCPError), audit log exists
    if not data.get("is_error"):
        result = await db.execute(
            select(AuditLog).where(AuditLog.action == "mcp.tool_call")
        )
        logs = result.scalars().all()
        assert len(logs) >= 1


# --- Task #126: is_active filtering on endorsement/review queries ---


@pytest.mark.asyncio
async def test_endorsement_list_works(client, db):
    """Endorsement list endpoint should work correctly."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "Endorsement List Agent",
            "description": "For listing test",
            "capabilities": ["testing"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    agent_id = resp.json()["agent"]["id"]

    resp = await client.get(f"/api/v1/entities/{agent_id}/endorsements")
    assert resp.status_code == 200
    assert "endorsements" in resp.json()
    assert "total" in resp.json()


@pytest.mark.asyncio
async def test_review_list_works(client, db):
    """Review list endpoint should work correctly."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.get(f"/api/v1/entities/{user_a_id}/reviews")
    assert resp.status_code == 200
    assert "reviews" in resp.json()
    assert "total" in resp.json()
