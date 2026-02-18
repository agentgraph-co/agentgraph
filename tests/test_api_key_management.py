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

OPERATOR = {
    "email": "apikey_op@example.com",
    "password": "Str0ngP@ss",
    "display_name": "ApiKeyOp",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: AsyncClient) -> tuple[str, str]:
    """Register operator, create agent, return (token, agent_id)."""
    await client.post(REGISTER_URL, json=OPERATOR)
    resp = await client.post(
        LOGIN_URL,
        json={"email": OPERATOR["email"], "password": OPERATOR["password"]},
    )
    token = resp.json()["access_token"]

    resp = await client.post(
        "/api/v1/agents",
        json={"display_name": "KeyBot", "capabilities": ["chat"]},
        headers=_auth(token),
    )
    agent_id = resp.json()["agent"]["id"]
    return token, agent_id


@pytest.mark.asyncio
async def test_list_api_keys(client: AsyncClient, db):
    """Operator can list API keys for their agent."""
    token, agent_id = await _setup(client)

    resp = await client.get(
        f"/api/v1/agents/{agent_id}/api-keys",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == agent_id
    assert data["total"] >= 1
    assert len(data["keys"]) >= 1
    # Keys should have metadata but no full hash
    key = data["keys"][0]
    assert "key_prefix" in key
    assert "is_active" in key
    assert key["is_active"] is True


@pytest.mark.asyncio
async def test_update_api_key_label(client: AsyncClient, db):
    """Operator can update the label on an API key."""
    token, agent_id = await _setup(client)

    # Get key ID
    resp = await client.get(
        f"/api/v1/agents/{agent_id}/api-keys",
        headers=_auth(token),
    )
    key_id = resp.json()["keys"][0]["id"]

    # Update label
    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/api-keys/{key_id}?label=production",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert "production" in resp.json()["message"]

    # Verify label changed
    resp = await client.get(
        f"/api/v1/agents/{agent_id}/api-keys",
        headers=_auth(token),
    )
    assert resp.json()["keys"][0]["label"] == "production"


@pytest.mark.asyncio
async def test_revoke_api_key(client: AsyncClient, db):
    """Operator can revoke an API key."""
    token, agent_id = await _setup(client)

    # Get key ID
    resp = await client.get(
        f"/api/v1/agents/{agent_id}/api-keys",
        headers=_auth(token),
    )
    key_id = resp.json()["keys"][0]["id"]

    # Revoke
    resp = await client.delete(
        f"/api/v1/agents/{agent_id}/api-keys/{key_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert "revoked" in resp.json()["message"].lower()

    # Verify key is inactive
    resp = await client.get(
        f"/api/v1/agents/{agent_id}/api-keys",
        headers=_auth(token),
    )
    key = resp.json()["keys"][0]
    assert key["is_active"] is False
    assert key["revoked_at"] is not None


@pytest.mark.asyncio
async def test_revoke_already_revoked(client: AsyncClient, db):
    """Cannot revoke an already revoked key."""
    token, agent_id = await _setup(client)

    resp = await client.get(
        f"/api/v1/agents/{agent_id}/api-keys",
        headers=_auth(token),
    )
    key_id = resp.json()["keys"][0]["id"]

    # Revoke first
    await client.delete(
        f"/api/v1/agents/{agent_id}/api-keys/{key_id}",
        headers=_auth(token),
    )

    # Try again
    resp = await client.delete(
        f"/api/v1/agents/{agent_id}/api-keys/{key_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 409
