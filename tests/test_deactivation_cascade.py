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

HUMAN = {
    "email": "cascade@example.com",
    "password": "Str0ngP@ss",
    "display_name": "CascadeUser",
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
async def test_self_deactivate_revokes_api_keys(client: AsyncClient, db):
    """Self-deactivation revokes agent API keys."""
    token, human_id = await _setup_human(client)

    # Create an agent
    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "CascadeBot",
            "capabilities": ["chat"],
            "autonomy_level": 2,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    agent_id = resp.json()["agent"]["id"]
    agent_api_key = resp.json()["api_key"]

    # Verify agent API key works
    me_resp = await client.get(
        "/api/v1/auth/me", headers={"X-API-Key": agent_api_key}
    )
    assert me_resp.status_code == 200

    # Deactivate the agent
    resp = await client.delete(
        f"/api/v1/agents/{agent_id}", headers=_auth(token)
    )
    assert resp.status_code == 200

    # Agent API key should no longer work
    me_resp = await client.get(
        "/api/v1/auth/me", headers={"X-API-Key": agent_api_key}
    )
    assert me_resp.status_code == 401


@pytest.mark.asyncio
async def test_self_deactivate_disables_webhooks(client: AsyncClient, db):
    """Self-deactivation deactivates webhook subscriptions."""
    token, human_id = await _setup_human(client)

    # Create a webhook
    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://hooks.example.com/wh",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201

    # Verify webhook is active
    resp = await client.get("/api/v1/webhooks", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["webhooks"][0]["is_active"] is True

    # Deactivate account
    resp = await client.post("/api/v1/account/deactivate", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "cascade" in data
    assert data["cascade"]["deactivated_webhooks"] >= 1


@pytest.mark.asyncio
async def test_self_deactivate_returns_cascade_summary(client: AsyncClient, db):
    """Self-deactivation returns cascade cleanup summary."""
    token, human_id = await _setup_human(client)

    resp = await client.post("/api/v1/account/deactivate", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["cascade"]["revoked_api_keys"] >= 0
    assert data["cascade"]["deactivated_webhooks"] >= 0


@pytest.mark.asyncio
async def test_deactivated_token_rejected(client: AsyncClient, db):
    """After deactivation, the JWT token is rejected."""
    token, human_id = await _setup_human(client)

    # Deactivate
    resp = await client.post("/api/v1/account/deactivate", headers=_auth(token))
    assert resp.status_code == 200

    # Token should be rejected
    resp = await client.get("/api/v1/auth/me", headers=_auth(token))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_agent_deactivate_cascade(client: AsyncClient, db):
    """Agent deactivation revokes its API keys via cascade."""
    token, human_id = await _setup_human(client)

    # Create agent with webhook
    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "CascadeBot2",
            "capabilities": ["search"],
            "autonomy_level": 1,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    agent_id = resp.json()["agent"]["id"]
    api_key = resp.json()["api_key"]

    # Create webhook for agent
    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://hooks.example.com/agent",
            "event_types": ["dm.received"],
        },
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 201

    # Deactivate agent
    resp = await client.delete(
        f"/api/v1/agents/{agent_id}", headers=_auth(token)
    )
    assert resp.status_code == 200

    # API key no longer works
    resp = await client.get(
        "/api/v1/auth/me", headers={"X-API-Key": api_key}
    )
    assert resp.status_code == 401
