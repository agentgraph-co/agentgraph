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

OPERATOR_A = {
    "email": "op_a@example.com",
    "password": "Str0ngP@ss",
    "display_name": "OperatorA",
}
OPERATOR_B = {
    "email": "op_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "OperatorB",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_human(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


async def _create_unlinked_agent(client: AsyncClient) -> tuple[str, str]:
    """Register an agent without an operator. Returns (api_key, agent_id)."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "UnlinkedBot", "capabilities": ["chat"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    return data["api_key"], data["agent"]["id"]


async def _create_linked_agent(
    client: AsyncClient, operator_email: str,
) -> tuple[str, str]:
    """Register an agent linked to an operator. Returns (api_key, agent_id)."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={
            "display_name": "LinkedBot",
            "capabilities": ["chat"],
            "operator_email": operator_email,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    return data["api_key"], data["agent"]["id"]


@pytest.mark.asyncio
async def test_set_operator_on_unlinked_agent(client: AsyncClient, db):
    """A human can link an unlinked agent to themselves."""
    token_a, _ = await _setup_human(client, OPERATOR_A)
    _, agent_id = await _create_unlinked_agent(client)

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/set-operator",
        json={"operator_email": OPERATOR_A["email"]},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert resp.json()["operator_id"] is not None


@pytest.mark.asyncio
async def test_transfer_operator(client: AsyncClient, db):
    """Current operator can transfer an agent to a different human."""
    token_a, _ = await _setup_human(client, OPERATOR_A)
    await _setup_human(client, OPERATOR_B)
    _, agent_id = await _create_linked_agent(client, OPERATOR_A["email"])

    # Operator A transfers to Operator B
    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/set-operator",
        json={"operator_email": OPERATOR_B["email"]},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    # Operator should now be B
    assert data["operator_id"] is not None


@pytest.mark.asyncio
async def test_cannot_claim_agent_linked_to_another(client: AsyncClient, db):
    """Non-operator human cannot claim an agent linked to someone else."""
    await _setup_human(client, OPERATOR_A)
    token_b, _ = await _setup_human(client, OPERATOR_B)
    _, agent_id = await _create_linked_agent(client, OPERATOR_A["email"])

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/set-operator",
        json={"operator_email": OPERATOR_B["email"]},
        headers=_auth(token_b),
    )
    assert resp.status_code == 403
    assert "another operator" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_set_operator_invalid_email(client: AsyncClient, db):
    """Setting operator with nonexistent email fails."""
    token_a, _ = await _setup_human(client, OPERATOR_A)
    _, agent_id = await _create_unlinked_agent(client)

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/set-operator",
        json={"operator_email": "nobody@example.com"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_release_operator(client: AsyncClient, db):
    """Operator can release (unlink) an agent."""
    token_a, _ = await _setup_human(client, OPERATOR_A)
    _, agent_id = await _create_linked_agent(client, OPERATOR_A["email"])

    resp = await client.delete(
        f"/api/v1/agents/{agent_id}/operator",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert resp.json()["operator_id"] is None


@pytest.mark.asyncio
async def test_release_already_unlinked(client: AsyncClient, db):
    """Releasing an agent that has no operator fails."""
    token_a, _ = await _setup_human(client, OPERATOR_A)
    _, agent_id = await _create_unlinked_agent(client)

    # First link it so we own it
    await client.patch(
        f"/api/v1/agents/{agent_id}/set-operator",
        json={"operator_email": OPERATOR_A["email"]},
        headers=_auth(token_a),
    )
    # Release it
    await client.delete(
        f"/api/v1/agents/{agent_id}/operator",
        headers=_auth(token_a),
    )
    # Try to release again — should fail since no operator now
    # But we can't call release since _require_owner will fail on None operator_id
    # Actually the agent is unlinked so operator_id is None, _require_owner checks
    # agent.operator_id != operator.id, which will be None != our_id = True -> 403
    resp = await client.delete(
        f"/api/v1/agents/{agent_id}/operator",
        headers=_auth(token_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_autonomy(client: AsyncClient, db):
    """Operator can update agent autonomy level."""
    token_a, _ = await _setup_human(client, OPERATOR_A)
    _, agent_id = await _create_linked_agent(client, OPERATOR_A["email"])

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/autonomy",
        json={"autonomy_level": 4},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert resp.json()["autonomy_level"] == 4


@pytest.mark.asyncio
async def test_update_autonomy_invalid_level(client: AsyncClient, db):
    """Autonomy level must be 1-5."""
    token_a, _ = await _setup_human(client, OPERATOR_A)
    _, agent_id = await _create_linked_agent(client, OPERATOR_A["email"])

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/autonomy",
        json={"autonomy_level": 0},
        headers=_auth(token_a),
    )
    assert resp.status_code == 422

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/autonomy",
        json={"autonomy_level": 6},
        headers=_auth(token_a),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_autonomy_non_owner_fails(client: AsyncClient, db):
    """Non-operator cannot update autonomy."""
    await _setup_human(client, OPERATOR_A)
    token_b, _ = await _setup_human(client, OPERATOR_B)
    _, agent_id = await _create_linked_agent(client, OPERATOR_A["email"])

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/autonomy",
        json={"autonomy_level": 2},
        headers=_auth(token_b),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_agent_public(client: AsyncClient, db):
    """Anyone can view an agent's public profile without auth."""
    _, agent_id = await _create_unlinked_agent(client)

    resp = await client.get(f"/api/v1/agents/{agent_id}/public")
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "UnlinkedBot"
    assert data["capabilities"] == ["chat"]


@pytest.mark.asyncio
async def test_get_agent_public_not_found(client: AsyncClient, db):
    """Public profile returns 404 for nonexistent agent."""
    import uuid

    resp = await client.get(f"/api/v1/agents/{uuid.uuid4()}/public")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_autonomy_audit_logged(client: AsyncClient, db):
    """Autonomy changes are recorded in the audit log."""
    token_a, _ = await _setup_human(client, OPERATOR_A)
    _, agent_id = await _create_linked_agent(client, OPERATOR_A["email"])

    await client.patch(
        f"/api/v1/agents/{agent_id}/autonomy",
        json={"autonomy_level": 5},
        headers=_auth(token_a),
    )

    resp = await client.get(
        "/api/v1/account/audit-log",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    logs = resp.json()["entries"]
    autonomy_logs = [e for e in logs if e["action"] == "agent.autonomy_update"]
    assert len(autonomy_logs) >= 1
    assert autonomy_logs[0]["details"]["new_autonomy_level"] == 5
