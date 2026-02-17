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
ME_URL = "/api/v1/auth/me"
AGENTS_URL = "/api/v1/agents"
EVOLUTION_URL = "/api/v1/evolution"

OPERATOR = {
    "email": "operator@evo.com",
    "password": "Str0ngP@ss",
    "display_name": "Operator",
}


async def _setup_operator(client: AsyncClient) -> str:
    """Register + login operator, return token."""
    await client.post(REGISTER_URL, json=OPERATOR)
    resp = await client.post(
        LOGIN_URL,
        json={"email": OPERATOR["email"], "password": OPERATOR["password"]},
    )
    return resp.json()["access_token"]


async def _create_agent(client: AsyncClient, token: str, name: str = "TestBot") -> str:
    """Create an agent, return agent entity ID."""
    resp = await client.post(
        AGENTS_URL,
        json={
            "display_name": name,
            "capabilities": ["chat", "search"],
            "autonomy_level": 3,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()["agent"]["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Create evolution records ---


@pytest.mark.asyncio
async def test_create_initial_evolution(client: AsyncClient):
    token = await _setup_operator(client)
    agent_id = await _create_agent(client, token)

    resp = await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Initial release of TestBot",
            "capabilities_snapshot": ["chat", "search"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["version"] == "1.0.0"
    assert data["change_type"] == "initial"
    assert data["anchor_hash"] is not None
    assert data["parent_record_id"] is None


@pytest.mark.asyncio
async def test_create_evolution_update(client: AsyncClient):
    token = await _setup_operator(client)
    agent_id = await _create_agent(client, token)

    # Initial version
    await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Initial release",
            "capabilities_snapshot": ["chat"],
        },
        headers=_auth(token),
    )

    # Update version
    resp = await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.1.0",
            "change_type": "capability_add",
            "change_summary": "Added search capability",
            "capabilities_snapshot": ["chat", "search"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["version"] == "1.1.0"
    assert data["parent_record_id"] is not None  # Links to 1.0.0


@pytest.mark.asyncio
async def test_duplicate_version_fails(client: AsyncClient):
    token = await _setup_operator(client)
    agent_id = await _create_agent(client, token)

    await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Initial",
        },
        headers=_auth(token),
    )

    resp = await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "update",
            "change_summary": "Duplicate",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_non_operator_cannot_create(client: AsyncClient):
    token = await _setup_operator(client)
    agent_id = await _create_agent(client, token)

    # Register a different user
    await client.post(
        REGISTER_URL,
        json={
            "email": "other@evo.com",
            "password": "Str0ngP@ss",
            "display_name": "Other",
        },
    )
    other_resp = await client.post(
        LOGIN_URL,
        json={"email": "other@evo.com", "password": "Str0ngP@ss"},
    )
    other_token = other_resp.json()["access_token"]

    resp = await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Unauthorized",
        },
        headers=_auth(other_token),
    )
    assert resp.status_code == 403


# --- Timeline and lineage ---


@pytest.mark.asyncio
async def test_get_timeline(client: AsyncClient):
    token = await _setup_operator(client)
    agent_id = await _create_agent(client, token)

    for v in ["1.0.0", "1.1.0", "2.0.0"]:
        await client.post(
            EVOLUTION_URL,
            json={
                "entity_id": agent_id,
                "version": v,
                "change_type": "update",
                "change_summary": f"Version {v}",
                "capabilities_snapshot": ["chat"],
            },
            headers=_auth(token),
        )

    resp = await client.get(f"{EVOLUTION_URL}/{agent_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3
    versions = {r["version"] for r in data["records"]}
    assert versions == {"1.0.0", "1.1.0", "2.0.0"}


@pytest.mark.asyncio
async def test_get_lineage(client: AsyncClient):
    token = await _setup_operator(client)
    agent_id = await _create_agent(client, token)

    await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Initial",
            "capabilities_snapshot": ["chat"],
        },
        headers=_auth(token),
    )
    await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.1.0",
            "change_type": "update",
            "change_summary": "Update",
            "capabilities_snapshot": ["chat", "search"],
        },
        headers=_auth(token),
    )

    resp = await client.get(f"{EVOLUTION_URL}/{agent_id}/lineage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_versions"] == 2
    assert data["current_version"] == "1.1.0"
    assert data["fork_count"] == 0


# --- Version diff ---


@pytest.mark.asyncio
async def test_compare_versions(client: AsyncClient):
    token = await _setup_operator(client)
    agent_id = await _create_agent(client, token)

    await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Initial",
            "capabilities_snapshot": ["chat", "translate"],
        },
        headers=_auth(token),
    )
    await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "2.0.0",
            "change_type": "update",
            "change_summary": "Revamp",
            "capabilities_snapshot": ["chat", "search", "code"],
        },
        headers=_auth(token),
    )

    resp = await client.get(f"{EVOLUTION_URL}/{agent_id}/diff/1.0.0/2.0.0")
    assert resp.status_code == 200
    data = resp.json()
    assert "search" in data["added"]
    assert "code" in data["added"]
    assert "translate" in data["removed"]
    assert "chat" in data["unchanged"]


@pytest.mark.asyncio
async def test_empty_timeline(client: AsyncClient):
    token = await _setup_operator(client)
    agent_id = await _create_agent(client, token)

    resp = await client.get(f"{EVOLUTION_URL}/{agent_id}")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


# --- Fork tracking ---


@pytest.mark.asyncio
async def test_fork_tracking(client: AsyncClient):
    token = await _setup_operator(client)
    agent_a = await _create_agent(client, token, "AgentA")
    agent_b = await _create_agent(client, token, "AgentB")

    # A has a version
    await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_a,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Original",
            "capabilities_snapshot": ["chat"],
        },
        headers=_auth(token),
    )

    # B is forked from A
    resp = await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_b,
            "version": "1.0.0",
            "change_type": "fork",
            "change_summary": "Forked from AgentA",
            "capabilities_snapshot": ["chat", "custom"],
            "forked_from_entity_id": agent_a,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert resp.json()["forked_from_entity_id"] == agent_a

    # Check A's lineage shows fork_count
    lineage = await client.get(f"{EVOLUTION_URL}/{agent_a}/lineage")
    assert lineage.json()["fork_count"] == 1

    # Check B's lineage shows forked_from
    lineage_b = await client.get(f"{EVOLUTION_URL}/{agent_b}/lineage")
    assert lineage_b.json()["forked_from"] == agent_a


# --- Approval workflow ---


@pytest.mark.asyncio
async def test_tier1_auto_approved(client: AsyncClient):
    """Tier 1 changes (initial, update) are auto-approved."""
    token = await _setup_operator(client)
    agent_id = await _create_agent(client, token)

    resp = await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "First version",
            "capabilities_snapshot": ["chat"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["risk_tier"] == 1
    assert data["approval_status"] == "auto_approved"


@pytest.mark.asyncio
async def test_tier2_pending_approval(client: AsyncClient):
    """Tier 2 changes (capability_add) require approval."""
    token = await _setup_operator(client)
    agent_id = await _create_agent(client, token)

    # First create initial version (auto-approved)
    await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Initial",
            "capabilities_snapshot": ["chat"],
        },
        headers=_auth(token),
    )

    # Capability add = tier 2 = pending
    resp = await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.1.0",
            "change_type": "capability_add",
            "change_summary": "Adding search capability",
            "capabilities_snapshot": ["chat", "search"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["risk_tier"] == 2
    assert data["approval_status"] == "pending"


@pytest.mark.asyncio
async def test_approve_evolution(client: AsyncClient):
    """Operator can approve a pending evolution record."""
    token = await _setup_operator(client)
    agent_id = await _create_agent(client, token)

    await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Initial",
        },
        headers=_auth(token),
    )

    resp = await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "2.0.0",
            "change_type": "capability_add",
            "change_summary": "Adding capabilities",
            "capabilities_snapshot": ["chat", "code-gen"],
        },
        headers=_auth(token),
    )
    record_id = resp.json()["id"]
    assert resp.json()["approval_status"] == "pending"

    # Approve it
    resp = await client.post(
        f"{EVOLUTION_URL}/records/{record_id}/approve",
        json={"action": "approve", "note": "Looks good"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "approved"
    assert resp.json()["approval_note"] == "Looks good"
    assert resp.json()["approved_at"] is not None


@pytest.mark.asyncio
async def test_reject_evolution(client: AsyncClient):
    """Operator can reject a pending evolution record."""
    token = await _setup_operator(client)
    agent_id = await _create_agent(client, token)

    await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Initial",
        },
        headers=_auth(token),
    )

    resp = await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "2.0.0",
            "change_type": "capability_remove",
            "change_summary": "Removing capabilities",
        },
        headers=_auth(token),
    )
    record_id = resp.json()["id"]

    resp = await client.post(
        f"{EVOLUTION_URL}/records/{record_id}/approve",
        json={"action": "reject", "note": "Not safe"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "rejected"


@pytest.mark.asyncio
async def test_cannot_approve_auto_approved(client: AsyncClient):
    """Cannot approve a record that's already auto-approved."""
    token = await _setup_operator(client)
    agent_id = await _create_agent(client, token)

    resp = await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Initial",
        },
        headers=_auth(token),
    )
    record_id = resp.json()["id"]

    resp = await client.post(
        f"{EVOLUTION_URL}/records/{record_id}/approve",
        json={"action": "approve"},
        headers=_auth(token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_pending_evolutions_list(client: AsyncClient):
    """Get all pending evolution records for operator's agents."""
    token = await _setup_operator(client)
    agent_id = await _create_agent(client, token)

    await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Initial",
        },
        headers=_auth(token),
    )

    # Create two pending records
    await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.1.0",
            "change_type": "capability_add",
            "change_summary": "Adding cap 1",
        },
        headers=_auth(token),
    )
    await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_id,
            "version": "1.2.0",
            "change_type": "capability_remove",
            "change_summary": "Removing cap",
        },
        headers=_auth(token),
    )

    resp = await client.get(
        f"{EVOLUTION_URL}/pending/all", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    for r in data["records"]:
        assert r["approval_status"] == "pending"


@pytest.mark.asyncio
async def test_tier3_fork_pending(client: AsyncClient):
    """Tier 3 changes (fork) require approval."""
    token = await _setup_operator(client)
    agent_a = await _create_agent(client, token, "SourceBot")
    agent_b = await _create_agent(client, token, "ForkBot")

    await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_a,
            "version": "1.0.0",
            "change_type": "initial",
            "change_summary": "Source",
        },
        headers=_auth(token),
    )

    resp = await client.post(
        EVOLUTION_URL,
        json={
            "entity_id": agent_b,
            "version": "1.0.0",
            "change_type": "fork",
            "change_summary": "Forked from source",
            "forked_from_entity_id": agent_a,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["risk_tier"] == 3
    assert data["approval_status"] == "pending"
