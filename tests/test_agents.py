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
AGENTS_URL = "/api/v1/agents"

OPERATOR = {
    "email": "operator@example.com",
    "password": "Str0ngP@ss",
    "display_name": "Operator",
}

AGENT_DATA = {
    "display_name": "CodeBot",
    "capabilities": ["code-review", "text-generation"],
    "autonomy_level": 3,
}


async def _get_operator_token(client: AsyncClient) -> str:
    await client.post(REGISTER_URL, json=OPERATOR)
    resp = await client.post(
        LOGIN_URL,
        json={"email": OPERATOR["email"], "password": OPERATOR["password"]},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Create agent tests ---


@pytest.mark.asyncio
async def test_create_agent(client: AsyncClient):
    token = await _get_operator_token(client)
    resp = await client.post(AGENTS_URL, json=AGENT_DATA, headers=_auth(token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent"]["display_name"] == "CodeBot"
    assert data["agent"]["capabilities"] == ["code-review", "text-generation"]
    assert data["agent"]["autonomy_level"] == 3
    assert data["agent"]["type"] == "agent"
    assert data["agent"]["did_web"].startswith("did:web:agentgraph.io:agents:")
    assert len(data["api_key"]) == 64  # hex of 32 bytes


@pytest.mark.asyncio
async def test_create_agent_unauthenticated(client: AsyncClient):
    resp = await client.post(AGENTS_URL, json=AGENT_DATA)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_agent_invalid_autonomy(client: AsyncClient):
    token = await _get_operator_token(client)
    bad_data = {**AGENT_DATA, "autonomy_level": 10}
    resp = await client.post(AGENTS_URL, json=bad_data, headers=_auth(token))
    assert resp.status_code == 422


# --- List agents tests ---


@pytest.mark.asyncio
async def test_list_agents(client: AsyncClient):
    token = await _get_operator_token(client)
    await client.post(AGENTS_URL, json=AGENT_DATA, headers=_auth(token))
    await client.post(
        AGENTS_URL,
        json={"display_name": "Agent2", "capabilities": []},
        headers=_auth(token),
    )

    resp = await client.get(AGENTS_URL, headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# --- Get agent tests ---


@pytest.mark.asyncio
async def test_get_agent(client: AsyncClient):
    token = await _get_operator_token(client)
    create_resp = await client.post(
        AGENTS_URL, json=AGENT_DATA, headers=_auth(token)
    )
    agent_id = create_resp.json()["agent"]["id"]

    resp = await client.get(f"{AGENTS_URL}/{agent_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "CodeBot"


@pytest.mark.asyncio
async def test_get_agent_not_owner(client: AsyncClient):
    token = await _get_operator_token(client)
    create_resp = await client.post(
        AGENTS_URL, json=AGENT_DATA, headers=_auth(token)
    )
    agent_id = create_resp.json()["agent"]["id"]

    # Register a different user
    other = {
        "email": "other@example.com",
        "password": "Str0ngP@ss",
        "display_name": "Other",
    }
    await client.post(REGISTER_URL, json=other)
    other_resp = await client.post(
        LOGIN_URL,
        json={"email": other["email"], "password": other["password"]},
    )
    other_token = other_resp.json()["access_token"]

    resp = await client.get(
        f"{AGENTS_URL}/{agent_id}", headers=_auth(other_token)
    )
    assert resp.status_code == 403


# --- Update agent tests ---


@pytest.mark.asyncio
async def test_update_agent(client: AsyncClient):
    token = await _get_operator_token(client)
    create_resp = await client.post(
        AGENTS_URL, json=AGENT_DATA, headers=_auth(token)
    )
    agent_id = create_resp.json()["agent"]["id"]

    resp = await client.patch(
        f"{AGENTS_URL}/{agent_id}",
        json={"display_name": "UpdatedBot", "autonomy_level": 5},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "UpdatedBot"
    assert resp.json()["autonomy_level"] == 5


# --- Rotate key tests ---


@pytest.mark.asyncio
async def test_rotate_key(client: AsyncClient):
    token = await _get_operator_token(client)
    create_resp = await client.post(
        AGENTS_URL, json=AGENT_DATA, headers=_auth(token)
    )
    agent_id = create_resp.json()["agent"]["id"]
    old_key = create_resp.json()["api_key"]

    resp = await client.post(
        f"{AGENTS_URL}/{agent_id}/rotate-key", headers=_auth(token)
    )
    assert resp.status_code == 200
    new_key = resp.json()["api_key"]
    assert new_key != old_key
    assert len(new_key) == 64


# --- API key auth tests ---


@pytest.mark.asyncio
async def test_api_key_auth(client: AsyncClient):
    token = await _get_operator_token(client)
    create_resp = await client.post(
        AGENTS_URL, json=AGENT_DATA, headers=_auth(token)
    )
    api_key = create_resp.json()["api_key"]

    # Agent can access /me via API key
    resp = await client.get(
        "/api/v1/auth/me", headers={"X-API-Key": api_key}
    )
    assert resp.status_code == 200
    assert resp.json()["type"] == "agent"
    assert resp.json()["display_name"] == "CodeBot"


@pytest.mark.asyncio
async def test_api_key_auth_after_rotate(client: AsyncClient):
    token = await _get_operator_token(client)
    create_resp = await client.post(
        AGENTS_URL, json=AGENT_DATA, headers=_auth(token)
    )
    agent_id = create_resp.json()["agent"]["id"]
    old_key = create_resp.json()["api_key"]

    # Rotate
    rotate_resp = await client.post(
        f"{AGENTS_URL}/{agent_id}/rotate-key", headers=_auth(token)
    )
    new_key = rotate_resp.json()["api_key"]

    # Old key should fail
    resp = await client.get(
        "/api/v1/auth/me", headers={"X-API-Key": old_key}
    )
    assert resp.status_code == 401

    # New key should work
    resp = await client.get(
        "/api/v1/auth/me", headers={"X-API-Key": new_key}
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invalid_api_key(client: AsyncClient):
    resp = await client.get(
        "/api/v1/auth/me", headers={"X-API-Key": "bogus"}
    )
    assert resp.status_code == 401


# --- Deactivate agent tests ---


@pytest.mark.asyncio
async def test_deactivate_agent(client: AsyncClient):
    token = await _get_operator_token(client)
    create_resp = await client.post(
        AGENTS_URL, json=AGENT_DATA, headers=_auth(token)
    )
    agent_id = create_resp.json()["agent"]["id"]
    api_key = create_resp.json()["api_key"]

    # Deactivate
    resp = await client.delete(
        f"{AGENTS_URL}/{agent_id}", headers=_auth(token)
    )
    assert resp.status_code == 200

    # API key should no longer work (agent inactive)
    resp = await client.get(
        "/api/v1/auth/me", headers={"X-API-Key": api_key}
    )
    assert resp.status_code == 401


# --- Daily agent registration limit tests ---


@pytest.mark.asyncio
async def test_daily_agent_limit(client: AsyncClient):
    """Operator cannot create more than 10 agents per day."""
    token = await _get_operator_token(client)

    # Create 10 agents (should all succeed)
    for i in range(10):
        resp = await client.post(
            AGENTS_URL,
            json={"display_name": f"LimitBot{i}", "capabilities": []},
            headers=_auth(token),
        )
        assert resp.status_code == 201, f"Agent {i} should succeed, got {resp.status_code}"

    # 11th agent should be rejected with 429
    resp = await client.post(
        AGENTS_URL,
        json={"display_name": "LimitBotOverflow", "capabilities": []},
        headers=_auth(token),
    )
    assert resp.status_code == 429
    assert "maximum 10 agents per day" in resp.json()["detail"]
