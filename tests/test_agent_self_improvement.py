from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import Entity


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
AGENTS_URL = "/api/v1/agents"
EVO = "/api/v1/evolution"

OPERATOR = {
    "email": "si-operator@test.com",
    "password": "Str0ngP@ss",
    "display_name": "SIOperator",
}
OPERATOR2 = {
    "email": "si-other@test.com",
    "password": "Str0ngP@ss",
    "display_name": "OtherOperator",
}


async def _setup_operator(client: AsyncClient, user: dict = None) -> tuple[str, str]:
    """Register + login, return (token, entity_id)."""
    user = user or OPERATOR
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


async def _create_agent(client: AsyncClient, token: str) -> tuple[str, str]:
    """Create an agent, return (agent_id, api_key)."""
    resp = await client.post(
        AGENTS_URL,
        json={
            "display_name": "SelfImpBot",
            "capabilities": ["chat", "search"],
            "autonomy_level": 3,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    return data["agent"]["id"], data["api_key"]


def _ak(api_key: str) -> dict:
    return {"X-API-Key": api_key}


def _jwt(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


PROPOSAL = {
    "new_capabilities": ["chat", "search", "code-gen"],
    "new_version": "1.1.0",
    "reason": "Learned code generation from user interactions",
    "changes_summary": "Added code generation capability",
}


# --- Propose ---


@pytest.mark.asyncio
async def test_propose_self_improvement(client, db):
    """Agent can propose a self-improvement that creates a pending record."""
    op_token, _ = await _setup_operator(client)
    agent_id, api_key = await _create_agent(client, op_token)

    resp = await client.post(
        f"{EVO}/{agent_id}/self-improve", json=PROPOSAL, headers=_ak(api_key),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["change_type"] == "self_improvement"
    assert data["risk_tier"] == 3
    assert data["approval_status"] == "pending"
    assert data["version"] == "1.1.0"
    assert "code-gen" in data["capabilities_snapshot"]
    assert data["anchor_hash"] is not None


@pytest.mark.asyncio
async def test_propose_not_agent_returns_403(client, db):
    """A human operator cannot propose self-improvement for an agent."""
    op_token, _ = await _setup_operator(client)
    agent_id, _ = await _create_agent(client, op_token)

    resp = await client.post(
        f"{EVO}/{agent_id}/self-improve", json=PROPOSAL, headers=_jwt(op_token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_propose_human_entity_returns_403(client, db):
    """Self-improvement on a human entity returns 403 (not an agent type)."""
    op_token, op_id = await _setup_operator(client)

    # The human entity_id == current_entity.id, but type is not AGENT
    resp = await client.post(
        f"{EVO}/{op_id}/self-improve", json=PROPOSAL, headers=_jwt(op_token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_propose_duplicate_version_returns_409(client, db):
    """Proposing an already-existing version returns 409."""
    op_token, _ = await _setup_operator(client)
    agent_id, api_key = await _create_agent(client, op_token)

    resp1 = await client.post(
        f"{EVO}/{agent_id}/self-improve", json=PROPOSAL, headers=_ak(api_key),
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        f"{EVO}/{agent_id}/self-improve", json=PROPOSAL, headers=_ak(api_key),
    )
    assert resp2.status_code == 409


# --- Approve ---


@pytest.mark.asyncio
async def test_approve_self_improvement(client, db):
    """Operator can approve a pending self-improvement proposal."""
    op_token, _ = await _setup_operator(client)
    agent_id, api_key = await _create_agent(client, op_token)

    propose_resp = await client.post(
        f"{EVO}/{agent_id}/self-improve",
        json={
            "new_capabilities": ["chat", "search", "translate"],
            "new_version": "1.2.0",
            "reason": "Learned translation",
            "changes_summary": "Added translation capability",
        },
        headers=_ak(api_key),
    )
    record_id = propose_resp.json()["id"]

    approve_resp = await client.post(
        f"{EVO}/{agent_id}/approve/{record_id}",
        json={"note": "Looks good"},
        headers=_jwt(op_token),
    )
    assert approve_resp.status_code == 200
    data = approve_resp.json()
    assert data["approval_status"] == "approved"
    assert data["approval_note"] == "Looks good"

    # Verify capabilities were applied
    agent = await db.get(Entity, uuid.UUID(agent_id))
    await db.refresh(agent)
    assert "translate" in agent.capabilities


@pytest.mark.asyncio
async def test_approve_capabilities_applied(client, db):
    """After approval, the agent entity's capabilities reflect the proposal."""
    op_token, _ = await _setup_operator(client)
    agent_id, api_key = await _create_agent(client, op_token)

    # Verify initial capabilities via DB
    agent = await db.get(Entity, uuid.UUID(agent_id))
    assert "code-review" not in (agent.capabilities or [])

    propose_resp = await client.post(
        f"{EVO}/{agent_id}/self-improve",
        json={
            "new_capabilities": ["chat", "search", "code-review"],
            "new_version": "2.0.0",
            "reason": "Developed code review skills",
            "changes_summary": "Adding code-review to capabilities",
        },
        headers=_ak(api_key),
    )
    record_id = propose_resp.json()["id"]

    # Before approval: unchanged
    await db.refresh(agent)
    assert "code-review" not in (agent.capabilities or [])

    # Approve
    await client.post(
        f"{EVO}/{agent_id}/approve/{record_id}",
        json={"note": ""},
        headers=_jwt(op_token),
    )

    # After approval: updated
    await db.refresh(agent)
    assert "code-review" in agent.capabilities


# --- Reject ---


@pytest.mark.asyncio
async def test_reject_self_improvement(client, db):
    """Operator can reject a pending self-improvement proposal."""
    op_token, _ = await _setup_operator(client)
    agent_id, api_key = await _create_agent(client, op_token)

    propose_resp = await client.post(
        f"{EVO}/{agent_id}/self-improve",
        json={
            "new_capabilities": ["chat", "search", "exploit"],
            "new_version": "1.4.0",
            "reason": "Want to add exploit capability",
            "changes_summary": "Adding exploit capability",
        },
        headers=_ak(api_key),
    )
    record_id = propose_resp.json()["id"]

    reject_resp = await client.post(
        f"{EVO}/{agent_id}/reject/{record_id}",
        json={"note": "Exploit capability not allowed"},
        headers=_jwt(op_token),
    )
    assert reject_resp.status_code == 200
    data = reject_resp.json()
    assert data["approval_status"] == "rejected"

    # Capabilities NOT applied
    agent = await db.get(Entity, uuid.UUID(agent_id))
    await db.refresh(agent)
    assert "exploit" not in (agent.capabilities or [])


# --- Authorization ---


@pytest.mark.asyncio
async def test_wrong_operator_cannot_approve(client, db):
    """A different operator cannot approve another operator's agent."""
    op1_token, _ = await _setup_operator(client, OPERATOR)
    op2_token, _ = await _setup_operator(client, OPERATOR2)
    agent_id, api_key = await _create_agent(client, op1_token)

    propose_resp = await client.post(
        f"{EVO}/{agent_id}/self-improve",
        json={
            "new_capabilities": ["chat"],
            "new_version": "1.6.0",
            "reason": "test",
            "changes_summary": "test auth",
        },
        headers=_ak(api_key),
    )
    record_id = propose_resp.json()["id"]

    approve_resp = await client.post(
        f"{EVO}/{agent_id}/approve/{record_id}",
        json={"note": "hijack"},
        headers=_jwt(op2_token),
    )
    assert approve_resp.status_code == 403


@pytest.mark.asyncio
async def test_cannot_approve_non_self_improvement(client, db):
    """Approve endpoint rejects non-self-improvement records."""
    op_token, _ = await _setup_operator(client)
    agent_id, _ = await _create_agent(client, op_token)

    create_resp = await client.post(
        EVO,
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Initial release",
            "capabilities_snapshot": ["chat"],
        },
        headers=_jwt(op_token),
    )
    record_id = create_resp.json()["id"]

    resp = await client.post(
        f"{EVO}/{agent_id}/approve/{record_id}",
        json={"note": ""},
        headers=_jwt(op_token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_proposal_shows_in_pending_list(client, db):
    """Self-improvement proposals appear in the operator's pending list."""
    op_token, _ = await _setup_operator(client)
    agent_id, api_key = await _create_agent(client, op_token)

    await client.post(
        f"{EVO}/{agent_id}/self-improve",
        json={
            "new_capabilities": ["chat", "search", "summarize"],
            "new_version": "1.7.0",
            "reason": "Learned summarization",
            "changes_summary": "Added summarize capability",
        },
        headers=_ak(api_key),
    )

    pending_resp = await client.get(
        f"{EVO}/pending/all", headers=_jwt(op_token),
    )
    assert pending_resp.status_code == 200
    records = pending_resp.json()["records"]
    si_records = [r for r in records if r["change_type"] == "self_improvement"]
    assert len(si_records) >= 1
    assert si_records[0]["version"] == "1.7.0"


@pytest.mark.asyncio
async def test_double_approve_rejected(client, db):
    """Cannot approve an already-approved record."""
    op_token, _ = await _setup_operator(client)
    agent_id, api_key = await _create_agent(client, op_token)

    propose_resp = await client.post(
        f"{EVO}/{agent_id}/self-improve",
        json={
            "new_capabilities": ["chat"],
            "new_version": "1.8.0",
            "reason": "test",
            "changes_summary": "test double",
        },
        headers=_ak(api_key),
    )
    record_id = propose_resp.json()["id"]

    await client.post(
        f"{EVO}/{agent_id}/approve/{record_id}",
        json={"note": ""},
        headers=_jwt(op_token),
    )

    resp = await client.post(
        f"{EVO}/{agent_id}/approve/{record_id}",
        json={"note": "again"},
        headers=_jwt(op_token),
    )
    assert resp.status_code == 400
