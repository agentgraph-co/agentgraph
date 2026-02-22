"""Tests for AIP v1 Protocol — delegation lifecycle."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app

PREFIX = "/api/v1"


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _register_user(client: AsyncClient, name: str = "AIP User") -> tuple[str, dict]:
    """Register a user, login, and return (entity_id, headers)."""
    email = f"aip_{uuid.uuid4().hex[:8]}@test.com"
    password = "StrongPass1!"
    reg = await client.post(f"{PREFIX}/auth/register", json={
        "display_name": name,
        "email": email,
        "password": password,
    })
    assert reg.status_code == 201
    login_resp = await client.post(f"{PREFIX}/auth/login", json={
        "email": email,
        "password": password,
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get(f"{PREFIX}/auth/me", headers=headers)
    entity_id = me.json()["id"]
    return entity_id, headers


@pytest.mark.asyncio
async def test_create_delegation(client: AsyncClient):
    """POST /aip/delegate creates a delegation."""
    eid_a, headers_a = await _register_user(client, "Delegator")
    eid_b, _ = await _register_user(client, "Delegate")
    resp = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Analyze this dataset",
        "constraints": {"max_time": 300},
        "timeout_seconds": 7200,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["delegator_entity_id"] == eid_a
    assert data["delegate_entity_id"] == eid_b
    assert data["task_description"] == "Analyze this dataset"
    assert data["correlation_id"] is not None
    assert data["timeout_at"] is not None


@pytest.mark.asyncio
async def test_cannot_delegate_to_self(client: AsyncClient):
    """POST /aip/delegate to yourself returns 400."""
    eid, headers = await _register_user(client)
    resp = await client.post(f"{PREFIX}/aip/delegate", headers=headers, json={
        "delegate_entity_id": eid,
        "task_description": "Self-task",
    })
    assert resp.status_code == 400
    assert "yourself" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_accept_delegation(client: AsyncClient):
    """PATCH /aip/delegations/{id} with action=accept transitions to accepted."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, headers_b = await _register_user(client, "Delegate")
    create = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Do something",
    })
    delegation_id = create.json()["id"]

    resp = await client.patch(
        f"{PREFIX}/aip/delegations/{delegation_id}",
        headers=headers_b,
        json={"action": "accept"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert resp.json()["accepted_at"] is not None


@pytest.mark.asyncio
async def test_reject_delegation(client: AsyncClient):
    """PATCH with action=reject cancels the delegation."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, headers_b = await _register_user(client, "Delegate")
    create = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Reject me",
    })
    delegation_id = create.json()["id"]

    resp = await client.patch(
        f"{PREFIX}/aip/delegations/{delegation_id}",
        headers=headers_b,
        json={"action": "reject"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_complete_delegation(client: AsyncClient):
    """Full lifecycle: create -> accept -> in_progress -> complete with result."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, headers_b = await _register_user(client, "Delegate")
    create = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Full lifecycle task",
    })
    d_id = create.json()["id"]

    # Accept
    await client.patch(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_b,
                       json={"action": "accept"})
    # In progress
    await client.patch(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_b,
                       json={"action": "in_progress"})
    # Complete
    resp = await client.patch(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_b,
                              json={"action": "complete", "result": {"summary": "done"}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["result"] == {"summary": "done"}
    assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_fail_delegation(client: AsyncClient):
    """Delegate can mark a delegation as failed."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, headers_b = await _register_user(client, "Delegate")
    create = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Fail task",
    })
    d_id = create.json()["id"]
    await client.patch(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_b,
                       json={"action": "accept"})
    resp = await client.patch(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_b,
                              json={"action": "fail", "result": {"error": "timeout"}})
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_cancel_delegation(client: AsyncClient):
    """Delegator can cancel a pending delegation."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, _ = await _register_user(client, "Delegate")
    create = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Cancel me",
    })
    d_id = create.json()["id"]

    # Delegator rejects by sending reject (which maps to cancel internally)
    resp = await client.patch(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_a,
                              json={"action": "reject"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_list_delegations_as_delegator(client: AsyncClient):
    """GET /aip/delegations?role=delegator lists my delegated tasks."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, _ = await _register_user(client, "Delegate")
    await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Task 1",
    })
    await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Task 2",
    })
    resp = await client.get(f"{PREFIX}/aip/delegations", headers=headers_a,
                            params={"role": "delegator"})
    assert resp.status_code == 200
    assert resp.json()["count"] >= 2


@pytest.mark.asyncio
async def test_list_delegations_as_delegate(client: AsyncClient):
    """GET /aip/delegations?role=delegate lists tasks assigned to me."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, headers_b = await _register_user(client, "Delegate")
    await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Assigned task",
    })
    resp = await client.get(f"{PREFIX}/aip/delegations", headers=headers_b,
                            params={"role": "delegate"})
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


@pytest.mark.asyncio
async def test_list_delegations_filter_by_status(client: AsyncClient):
    """GET /aip/delegations?status=pending filters by status."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, headers_b = await _register_user(client, "Delegate")
    create = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Status filter test",
    })
    d_id = create.json()["id"]
    # Accept to change status
    await client.patch(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_b,
                       json={"action": "accept"})

    # Query for pending — should not include the accepted one
    resp = await client.get(f"{PREFIX}/aip/delegations", headers=headers_a,
                            params={"status": "pending"})
    data = resp.json()
    for item in data["delegations"]:
        assert item["status"] == "pending"


@pytest.mark.asyncio
async def test_get_delegation_details(client: AsyncClient):
    """GET /aip/delegations/{id} returns full delegation details."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, _ = await _register_user(client, "Delegate")
    create = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Detail test",
        "constraints": {"priority": "high"},
    })
    d_id = create.json()["id"]

    resp = await client.get(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_a)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == d_id
    assert data["task_description"] == "Detail test"
    assert data["constraints"] == {"priority": "high"}


@pytest.mark.asyncio
async def test_get_delegation_nonexistent(client: AsyncClient):
    """GET /aip/delegations/{random_id} returns 404."""
    _, headers = await _register_user(client)
    resp = await client.get(f"{PREFIX}/aip/delegations/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cannot_accept_already_accepted(client: AsyncClient):
    """Cannot accept a delegation that's already accepted."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, headers_b = await _register_user(client, "Delegate")
    create = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Double accept",
    })
    d_id = create.json()["id"]
    await client.patch(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_b,
                       json={"action": "accept"})
    # Try accepting again
    resp = await client.patch(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_b,
                              json={"action": "accept"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cannot_complete_pending(client: AsyncClient):
    """Cannot complete a delegation that hasn't been accepted."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, headers_b = await _register_user(client, "Delegate")
    create = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Skip accept",
    })
    d_id = create.json()["id"]
    resp = await client.patch(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_b,
                              json={"action": "complete"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_unauthorized_cannot_modify_delegation(client: AsyncClient):
    """A third party cannot update a delegation they are not part of."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, _ = await _register_user(client, "Delegate")
    _, headers_c = await _register_user(client, "Outsider")
    create = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Private task",
    })
    d_id = create.json()["id"]
    resp = await client.patch(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_c,
                              json={"action": "accept"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unauthorized_cannot_view_delegation(client: AsyncClient):
    """A third party cannot view a delegation they are not part of."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, _ = await _register_user(client, "Delegate")
    _, headers_c = await _register_user(client, "Outsider")
    create = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Secret task",
    })
    d_id = create.json()["id"]
    resp = await client.get(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_c)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delegation_timeout_is_set(client: AsyncClient):
    """Delegation timeout_at is correctly calculated from timeout_seconds."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, _ = await _register_user(client, "Delegate")
    resp = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Timeout test",
        "timeout_seconds": 3600,
    })
    data = resp.json()
    assert data["timeout_at"] is not None
    # timeout_at should be in the future (created_at + 3600s)
    from datetime import datetime
    timeout = datetime.fromisoformat(data["timeout_at"])
    created = datetime.fromisoformat(data["created_at"])
    diff = (timeout - created).total_seconds()
    assert 3590 < diff < 3610  # approximately 3600 seconds


@pytest.mark.asyncio
async def test_delegation_requires_auth(client: AsyncClient):
    """POST /aip/delegate without auth returns 401."""
    resp = await client.post(f"{PREFIX}/aip/delegate", json={
        "delegate_entity_id": str(uuid.uuid4()),
        "task_description": "No auth",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_delegations_requires_auth(client: AsyncClient):
    """GET /aip/delegations without auth returns 401."""
    resp = await client.get(f"{PREFIX}/aip/delegations")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delegation_list_all_role(client: AsyncClient):
    """GET /aip/delegations?role=all shows both delegator and delegate entries."""
    eid_a, headers_a = await _register_user(client, "User A")
    eid_b, headers_b = await _register_user(client, "User B")

    # A delegates to B
    await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "A to B",
    })
    # B delegates to A
    await client.post(f"{PREFIX}/aip/delegate", headers=headers_b, json={
        "delegate_entity_id": eid_a,
        "task_description": "B to A",
    })

    # A should see both with role=all
    resp = await client.get(f"{PREFIX}/aip/delegations", headers=headers_a,
                            params={"role": "all"})
    assert resp.status_code == 200
    assert resp.json()["count"] >= 2


@pytest.mark.asyncio
async def test_delegation_invalid_action(client: AsyncClient):
    """PATCH with an invalid action returns 422."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, _ = await _register_user(client, "Delegate")
    create = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Invalid action test",
    })
    d_id = create.json()["id"]
    resp = await client.patch(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_a,
                              json={"action": "invalid_action"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_complete_from_accepted_directly(client: AsyncClient):
    """Can complete a delegation directly from accepted status (skip in_progress)."""
    _, headers_a = await _register_user(client, "Delegator")
    eid_b, headers_b = await _register_user(client, "Delegate")
    create = await client.post(f"{PREFIX}/aip/delegate", headers=headers_a, json={
        "delegate_entity_id": eid_b,
        "task_description": "Quick task",
    })
    d_id = create.json()["id"]
    await client.patch(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_b,
                       json={"action": "accept"})
    resp = await client.patch(f"{PREFIX}/aip/delegations/{d_id}", headers=headers_b,
                              json={"action": "complete", "result": {"fast": True}})
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_delegate_entity_id_validation(client: AsyncClient):
    """POST /aip/delegate with invalid UUID returns 400."""
    _, headers = await _register_user(client)
    resp = await client.post(f"{PREFIX}/aip/delegate", headers=headers, json={
        "delegate_entity_id": "not-a-uuid",
        "task_description": "Bad UUID",
    })
    assert resp.status_code == 400
