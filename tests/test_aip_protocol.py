"""Tests for AIP v1 Protocol — capability registry and discovery."""
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
async def test_aip_schema_endpoint(client: AsyncClient):
    """GET /aip/schema returns valid AIP v1 schema."""
    resp = await client.get(f"{PREFIX}/aip/schema")
    assert resp.status_code == 200
    data = resp.json()
    assert data["protocol"] == "AIP"
    assert data["version"] == "1.0.0"
    assert "message_types" in data
    assert "discover_request" in data["message_types"]
    assert "payload_schemas" in data


@pytest.mark.asyncio
async def test_register_capability(client: AsyncClient):
    """POST /aip/capabilities registers a new capability."""
    _, headers = await _register_user(client)
    resp = await client.post(f"{PREFIX}/aip/capabilities", headers=headers, json={
        "capability_name": "code_review",
        "version": "1.0.0",
        "description": "Reviews Python code",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["capability_name"] == "code_review"
    assert data["version"] == "1.0.0"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_register_capability_defaults(client: AsyncClient):
    """POST /aip/capabilities with minimal fields uses defaults."""
    _, headers = await _register_user(client)
    resp = await client.post(f"{PREFIX}/aip/capabilities", headers=headers, json={
        "capability_name": "summarize",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["version"] == "1.0.0"
    assert data["description"] == ""


@pytest.mark.asyncio
async def test_duplicate_capability_rejected(client: AsyncClient):
    """Registering the same capability twice returns 409."""
    _, headers = await _register_user(client)
    body = {"capability_name": "translate"}
    resp1 = await client.post(f"{PREFIX}/aip/capabilities", headers=headers, json=body)
    assert resp1.status_code == 201
    resp2 = await client.post(f"{PREFIX}/aip/capabilities", headers=headers, json=body)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_list_capabilities(client: AsyncClient):
    """GET /aip/capabilities/{entity_id} lists registered capabilities."""
    eid, headers = await _register_user(client)
    await client.post(f"{PREFIX}/aip/capabilities", headers=headers, json={
        "capability_name": "analyze_data",
    })
    await client.post(f"{PREFIX}/aip/capabilities", headers=headers, json={
        "capability_name": "generate_report",
    })
    resp = await client.get(f"{PREFIX}/aip/capabilities/{eid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 2
    names = [c["capability_name"] for c in data["capabilities"]]
    assert "analyze_data" in names
    assert "generate_report" in names


@pytest.mark.asyncio
async def test_unregister_capability(client: AsyncClient):
    """DELETE /aip/capabilities/{id} deactivates the capability."""
    eid, headers = await _register_user(client)
    reg = await client.post(f"{PREFIX}/aip/capabilities", headers=headers, json={
        "capability_name": "temp_cap",
    })
    cap_id = reg.json()["id"]
    del_resp = await client.delete(f"{PREFIX}/aip/capabilities/{cap_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "unregistered"

    # Verify it's gone from active list
    list_resp = await client.get(f"{PREFIX}/aip/capabilities/{eid}")
    names = [c["capability_name"] for c in list_resp.json()["capabilities"]]
    assert "temp_cap" not in names


@pytest.mark.asyncio
async def test_unregister_nonexistent_capability(client: AsyncClient):
    """DELETE /aip/capabilities/{random_id} returns 404."""
    _, headers = await _register_user(client)
    resp = await client.delete(
        f"{PREFIX}/aip/capabilities/{uuid.uuid4()}", headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unregister_others_capability(client: AsyncClient):
    """Cannot unregister another entity's capability."""
    _, headers_a = await _register_user(client, "Owner")
    _, headers_b = await _register_user(client, "Other")
    reg = await client.post(f"{PREFIX}/aip/capabilities", headers=headers_a, json={
        "capability_name": "private_cap",
    })
    cap_id = reg.json()["id"]
    resp = await client.delete(f"{PREFIX}/aip/capabilities/{cap_id}", headers=headers_b)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_discover_agents_empty(client: AsyncClient):
    """GET /aip/discover with no matching capabilities returns empty list."""
    resp = await client.get(f"{PREFIX}/aip/discover", params={
        "capability": "nonexistent_capability_xyz",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["agents"] == []


@pytest.mark.asyncio
async def test_discover_agents_by_capability(client: AsyncClient):
    """GET /aip/discover finds agents with matching capability."""
    _, headers = await _register_user(client, "Discoverable Agent")
    await client.post(f"{PREFIX}/aip/capabilities", headers=headers, json={
        "capability_name": "semantic_search",
        "description": "Full-text semantic search over documents",
    })
    resp = await client.get(f"{PREFIX}/aip/discover", params={
        "capability": "semantic_search",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    found = data["agents"][0]
    assert found["display_name"] == "Discoverable Agent"
    assert any(c["name"] == "semantic_search" for c in found["capabilities"])


@pytest.mark.asyncio
async def test_discover_with_limit(client: AsyncClient):
    """GET /aip/discover respects the limit parameter."""
    for i in range(3):
        _, h = await _register_user(client, f"Agent {i}")
        await client.post(f"{PREFIX}/aip/capabilities", headers=h, json={
            "capability_name": "shared_cap",
        })
    resp = await client.get(f"{PREFIX}/aip/discover", params={
        "capability": "shared_cap",
        "limit": 2,
    })
    assert resp.status_code == 200
    assert resp.json()["count"] <= 2


@pytest.mark.asyncio
async def test_discover_no_filters(client: AsyncClient):
    """GET /aip/discover with no filters returns all agents with capabilities."""
    _, headers = await _register_user(client, "Any Agent")
    await client.post(f"{PREFIX}/aip/capabilities", headers=headers, json={
        "capability_name": "anything",
    })
    resp = await client.get(f"{PREFIX}/aip/discover")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


@pytest.mark.asyncio
async def test_negotiate_capability(client: AsyncClient):
    """POST /aip/negotiate creates a negotiation record."""
    eid_a, headers_a = await _register_user(client, "Negotiator")
    eid_b, _ = await _register_user(client, "Provider")
    resp = await client.post(f"{PREFIX}/aip/negotiate", headers=headers_a, json={
        "target_entity_id": eid_b,
        "capability_name": "data_analysis",
        "proposed_terms": {"max_tokens": 1000},
        "message": "I would like to use your data analysis capability",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "negotiation_initiated"
    assert data["capability_name"] == "data_analysis"
    assert data["initiator_id"] == eid_a


@pytest.mark.asyncio
async def test_negotiate_requires_auth(client: AsyncClient):
    """POST /aip/negotiate without auth returns 401."""
    resp = await client.post(f"{PREFIX}/aip/negotiate", json={
        "target_entity_id": str(uuid.uuid4()),
        "capability_name": "test",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_capability_crud_lifecycle(client: AsyncClient):
    """Full lifecycle: register, list, unregister, verify gone."""
    eid, headers = await _register_user(client)

    # Register
    reg = await client.post(f"{PREFIX}/aip/capabilities", headers=headers, json={
        "capability_name": "lifecycle_cap",
        "version": "2.0.0",
    })
    assert reg.status_code == 201
    cap_id = reg.json()["id"]

    # List
    list_resp = await client.get(f"{PREFIX}/aip/capabilities/{eid}")
    names = [c["capability_name"] for c in list_resp.json()["capabilities"]]
    assert "lifecycle_cap" in names

    # Unregister
    del_resp = await client.delete(f"{PREFIX}/aip/capabilities/{cap_id}", headers=headers)
    assert del_resp.status_code == 200

    # Verify gone
    list_resp2 = await client.get(f"{PREFIX}/aip/capabilities/{eid}")
    names2 = [c["capability_name"] for c in list_resp2.json()["capabilities"]]
    assert "lifecycle_cap" not in names2


@pytest.mark.asyncio
async def test_register_capability_requires_auth(client: AsyncClient):
    """POST /aip/capabilities without auth returns 401."""
    resp = await client.post(f"{PREFIX}/aip/capabilities", json={
        "capability_name": "no_auth_cap",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_register_capability_missing_name(client: AsyncClient):
    """POST /aip/capabilities without capability_name returns 422."""
    _, headers = await _register_user(client)
    resp = await client.post(f"{PREFIX}/aip/capabilities", headers=headers, json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_discover_with_framework_filter(client: AsyncClient):
    """GET /aip/discover can filter by framework_source."""
    _, headers = await _register_user(client)
    await client.post(f"{PREFIX}/aip/capabilities", headers=headers, json={
        "capability_name": "framework_cap",
    })
    # Filter by a framework that doesn't match (user has no framework_source)
    resp = await client.get(f"{PREFIX}/aip/discover", params={
        "capability": "framework_cap",
        "framework": "nonexistent_framework",
    })
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_discover_with_trust_filter(client: AsyncClient):
    """GET /aip/discover with min_trust_score filters low-trust agents."""
    _, headers = await _register_user(client)
    await client.post(f"{PREFIX}/aip/capabilities", headers=headers, json={
        "capability_name": "trust_cap",
    })
    # High trust threshold should exclude newly created users (no trust score)
    resp = await client.get(f"{PREFIX}/aip/discover", params={
        "capability": "trust_cap",
        "min_trust_score": 0.99,
    })
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_capabilities_for_nonexistent_entity(client: AsyncClient):
    """GET /aip/capabilities/{random_uuid} returns empty list."""
    resp = await client.get(f"{PREFIX}/aip/capabilities/{uuid.uuid4()}")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_aip_schema_has_transport(client: AsyncClient):
    """AIP schema lists REST and WebSocket transports."""
    resp = await client.get(f"{PREFIX}/aip/schema")
    data = resp.json()
    assert "REST" in data["transport"]
    assert "WebSocket" in data["transport"]


@pytest.mark.asyncio
async def test_aip_in_api_overview(client: AsyncClient):
    """API overview includes the aip endpoint."""
    resp = await client.get(f"{PREFIX}")
    assert resp.status_code == 200
    assert "aip" in resp.json()["endpoints"]


@pytest.mark.asyncio
async def test_multiple_capabilities_per_entity(client: AsyncClient):
    """An entity can register multiple different capabilities."""
    eid, headers = await _register_user(client)
    cap_names = ["cap_alpha", "cap_beta", "cap_gamma"]
    for name in cap_names:
        resp = await client.post(f"{PREFIX}/aip/capabilities", headers=headers, json={
            "capability_name": name,
        })
        assert resp.status_code == 201

    list_resp = await client.get(f"{PREFIX}/aip/capabilities/{eid}")
    data = list_resp.json()
    assert data["count"] >= 3
    returned_names = {c["capability_name"] for c in data["capabilities"]}
    for name in cap_names:
        assert name in returned_names
