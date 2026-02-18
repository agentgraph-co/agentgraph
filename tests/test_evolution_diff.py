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
    "email": "evdiff_op@example.com",
    "password": "Str0ngP@ss",
    "display_name": "EvDiffOp",
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

    # Create agent
    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "DiffBot",
            "capabilities": ["chat"],
        },
        headers=_auth(token),
    )
    agent_id = resp.json()["agent"]["id"]
    return token, agent_id


@pytest.mark.asyncio
async def test_diff_capabilities(client: AsyncClient, db):
    """Diff shows added, removed, and unchanged capabilities."""
    token, agent_id = await _setup(client)

    # Create v1
    await client.post(
        "/api/v1/evolution",
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Initial version",
            "capabilities_snapshot": ["chat", "search"],
        },
        headers=_auth(token),
    )

    # Create v2 with different caps
    await client.post(
        "/api/v1/evolution",
        json={
            "entity_id": agent_id,
            "version": "2.0.0",
            "change_type": "update",
            "change_summary": "Added code review, dropped search",
            "capabilities_snapshot": ["chat", "code_review"],
        },
        headers=_auth(token),
    )

    resp = await client.get(
        f"/api/v1/evolution/{agent_id}/diff/1.0.0/2.0.0",
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["capabilities"]["added"] == ["code_review"]
    assert data["capabilities"]["removed"] == ["search"]
    assert data["capabilities"]["unchanged"] == ["chat"]


@pytest.mark.asyncio
async def test_diff_metadata(client: AsyncClient, db):
    """Diff shows metadata changes between versions."""
    token, agent_id = await _setup(client)

    await client.post(
        "/api/v1/evolution",
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "First release",
            "capabilities_snapshot": ["chat"],
            "extra_metadata": {"model": "gpt-4", "temperature": 0.7},
        },
        headers=_auth(token),
    )

    await client.post(
        "/api/v1/evolution",
        json={
            "entity_id": agent_id,
            "version": "1.1.0",
            "change_type": "update",
            "change_summary": "Switched to Claude",
            "capabilities_snapshot": ["chat"],
            "extra_metadata": {"model": "claude-sonnet", "temperature": 0.7},
        },
        headers=_auth(token),
    )

    resp = await client.get(
        f"/api/v1/evolution/{agent_id}/diff/1.0.0/1.1.0",
    )
    assert resp.status_code == 200
    data = resp.json()

    # model changed, temperature stayed the same (not in diff)
    assert "model" in data["metadata_diff"]
    assert data["metadata_diff"]["model"]["from"] == "gpt-4"
    assert data["metadata_diff"]["model"]["to"] == "claude-sonnet"
    assert "temperature" not in data["metadata_diff"]


@pytest.mark.asyncio
async def test_diff_change_types_and_summaries(client: AsyncClient, db):
    """Diff includes change_type and summary comparisons."""
    token, agent_id = await _setup(client)

    await client.post(
        "/api/v1/evolution",
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "First version",
            "capabilities_snapshot": ["chat"],
        },
        headers=_auth(token),
    )

    await client.post(
        "/api/v1/evolution",
        json={
            "entity_id": agent_id,
            "version": "1.1.0",
            "change_type": "capability_add",
            "change_summary": "Added code review capability",
            "capabilities_snapshot": ["chat", "code_review"],
        },
        headers=_auth(token),
    )

    resp = await client.get(
        f"/api/v1/evolution/{agent_id}/diff/1.0.0/1.1.0",
    )
    data = resp.json()

    assert data["change_types"]["from"] == "initial"
    assert data["change_types"]["to"] == "capability_add"
    assert data["summaries"]["version_a"] == "First version"
    assert data["summaries"]["version_b"] == "Added code review capability"
    assert data["risk_tiers"]["from"] == 1
    assert data["risk_tiers"]["to"] == 2


@pytest.mark.asyncio
async def test_diff_version_not_found(client: AsyncClient, db):
    """Diff returns 404 when a version doesn't exist."""
    token, agent_id = await _setup(client)

    await client.post(
        "/api/v1/evolution",
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "First",
            "capabilities_snapshot": [],
        },
        headers=_auth(token),
    )

    resp = await client.get(
        f"/api/v1/evolution/{agent_id}/diff/1.0.0/9.9.9",
    )
    assert resp.status_code == 404
