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

HUMAN = {
    "email": "agent_reg_human@example.com",
    "password": "Str0ngP@ss",
    "display_name": "AgentRegHuman",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_human(client: AsyncClient) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=HUMAN)
    resp = await client.post(
        LOGIN_URL, json={"email": HUMAN["email"], "password": HUMAN["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


@pytest.mark.asyncio
async def test_register_agent_direct(client: AsyncClient, db):
    """Agent can register directly without a human operator."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={
            "display_name": "TestBot",
            "capabilities": ["nlp", "search"],
            "autonomy_level": 3,
            "bio_markdown": "A test bot",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent"]["display_name"] == "TestBot"
    assert data["agent"]["type"] == "agent"
    assert data["agent"]["capabilities"] == ["nlp", "search"]
    assert data["agent"]["autonomy_level"] == 3
    assert data["agent"]["operator_id"] is None
    assert "api_key" in data
    assert len(data["api_key"]) == 64  # hex token


@pytest.mark.asyncio
async def test_register_agent_with_operator(client: AsyncClient, db):
    """Agent can register and link to an existing human operator."""
    await _setup_human(client)

    resp = await client.post(
        AGENT_REGISTER_URL,
        json={
            "display_name": "LinkedBot",
            "capabilities": ["chat"],
            "operator_email": HUMAN["email"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent"]["operator_id"] is not None
    assert data["agent"]["display_name"] == "LinkedBot"


@pytest.mark.asyncio
async def test_register_agent_invalid_operator(client: AsyncClient, db):
    """Registration fails if operator email doesn't exist."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={
            "display_name": "FailBot",
            "operator_email": "nobody@example.com",
        },
    )
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_registered_agent_can_authenticate(client: AsyncClient, db):
    """Agent registered via API can authenticate with its API key."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "AuthBot"},
    )
    assert resp.status_code == 201
    api_key = resp.json()["api_key"]

    # Use the API key to access authenticated endpoints
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "AuthBot"
    assert resp.json()["type"] == "agent"


@pytest.mark.asyncio
async def test_registered_agent_has_did(client: AsyncClient, db):
    """Registered agent gets a DID automatically."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "DidBot"},
    )
    assert resp.status_code == 201
    agent = resp.json()["agent"]
    assert agent["did_web"].startswith("did:web:agentgraph.io:agents:")
