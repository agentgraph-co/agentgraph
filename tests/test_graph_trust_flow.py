"""Tests for graph trust flow computation and endpoint."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.main import app
from src.models import (
    Entity,
    EntityType,
    PrivacyTier,
    TrustAttestation,
)


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
GRAPH_URL = "/api/v1/graph"


async def _create_user(client: AsyncClient, email: str, name: str):
    await client.post(
        REGISTER_URL,
        json={"email": email, "password": "Str0ngP@ss", "display_name": name},
    )
    resp = await client.post(
        LOGIN_URL, json={"email": email, "password": "Str0ngP@ss"},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _make_entity(db: AsyncSession, **kwargs) -> Entity:
    defaults = {
        "id": uuid.uuid4(),
        "type": EntityType.HUMAN,
        "display_name": f"User-{uuid.uuid4().hex[:6]}",
        "did_web": f"did:web:agentgraph.io:users:{uuid.uuid4()}",
        "email_verified": False,
        "bio_markdown": "",
    }
    defaults.update(kwargs)
    entity = Entity(**defaults)
    db.add(entity)
    return entity


# --- Trust flow unit tests ---


@pytest.mark.asyncio
async def test_trust_flow_no_attestations(db: AsyncSession):
    """Entity with no attestations returns empty attestation list."""
    from src.graph.trust_flow import compute_trust_flow

    e = _make_entity(db)
    await db.flush()

    result = await compute_trust_flow(db, e.id)
    assert result["entity_id"] == str(e.id)
    assert result["attestations"] == []


@pytest.mark.asyncio
async def test_trust_flow_single_level(db: AsyncSession):
    """Single attester shows up in trust flow."""
    from src.graph.trust_flow import compute_trust_flow

    target = _make_entity(db, display_name="Target")
    attester = _make_entity(db, display_name="Attester")
    await db.flush()

    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester.id,
        target_entity_id=target.id,
        attestation_type="competent",
        weight=0.8,
    ))
    await db.flush()

    result = await compute_trust_flow(db, target.id, max_depth=1)
    assert len(result["attestations"]) == 1
    assert result["attestations"][0]["attester_id"] == str(attester.id)
    assert result["attestations"][0]["attestation_type"] == "competent"
    assert result["attestations"][0]["weight"] == 0.8


@pytest.mark.asyncio
async def test_trust_flow_multi_level(db: AsyncSession):
    """Trust flow follows attestation chains at depth > 1."""
    from src.graph.trust_flow import compute_trust_flow

    target = _make_entity(db, display_name="Target")
    mid = _make_entity(db, display_name="Mid")
    root = _make_entity(db, display_name="Root")
    await db.flush()

    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=mid.id,
        target_entity_id=target.id,
        attestation_type="reliable",
        weight=0.7,
    ))
    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=root.id,
        target_entity_id=mid.id,
        attestation_type="competent",
        weight=0.9,
    ))
    await db.flush()

    result = await compute_trust_flow(db, target.id, max_depth=2)
    assert len(result["attestations"]) == 1
    mid_node = result["attestations"][0]
    assert mid_node["attester_id"] == str(mid.id)
    assert len(mid_node["children"]) == 1
    assert mid_node["children"][0]["attester_id"] == str(root.id)


@pytest.mark.asyncio
async def test_trust_flow_depth_limit(db: AsyncSession):
    """Depth limit prevents going deeper than specified."""
    from src.graph.trust_flow import compute_trust_flow

    target = _make_entity(db)
    mid = _make_entity(db)
    root = _make_entity(db)
    await db.flush()

    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=mid.id,
        target_entity_id=target.id,
        attestation_type="reliable",
        weight=0.5,
    ))
    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=root.id,
        target_entity_id=mid.id,
        attestation_type="reliable",
        weight=0.5,
    ))
    await db.flush()

    result = await compute_trust_flow(db, target.id, max_depth=1)
    mid_node = result["attestations"][0]
    # At depth=1, should not recurse further
    assert mid_node["children"] == []


@pytest.mark.asyncio
async def test_trust_flow_cycle_prevention(db: AsyncSession):
    """Cycles in attestation graph are handled without infinite recursion."""
    from src.graph.trust_flow import compute_trust_flow

    e1 = _make_entity(db)
    e2 = _make_entity(db)
    await db.flush()

    # Mutual attestation (cycle)
    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=e2.id,
        target_entity_id=e1.id,
        attestation_type="competent",
        weight=0.5,
    ))
    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=e1.id,
        target_entity_id=e2.id,
        attestation_type="reliable",
        weight=0.5,
    ))
    await db.flush()

    # Should not hang
    result = await compute_trust_flow(db, e1.id, max_depth=5)
    assert result["entity_id"] == str(e1.id)


@pytest.mark.asyncio
async def test_trust_flow_endpoint(client: AsyncClient):
    """GET /graph/trust-flow/{id} returns valid trust flow."""
    t1, id1 = await _create_user(client, "tf1@test.com", "TFUser1")
    resp = await client.get(f"{GRAPH_URL}/trust-flow/{id1}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == id1
    assert "attestations" in data


@pytest.mark.asyncio
async def test_trust_flow_privacy_check(client: AsyncClient, db: AsyncSession):
    """Private entity trust flow requires follower access."""
    t1, id1 = await _create_user(client, "tfp1@test.com", "TFPriv1")

    # Make entity private
    from sqlalchemy import update

    from src.models import Entity
    await db.execute(
        update(Entity).where(Entity.id == uuid.UUID(id1)).values(
            privacy_tier=PrivacyTier.PRIVATE,
        )
    )
    await db.flush()

    # Unauthenticated request should be 403
    resp = await client.get(f"{GRAPH_URL}/trust-flow/{id1}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_trust_flow_nonexistent_entity(client: AsyncClient):
    """Trust flow for nonexistent entity returns 404."""
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"{GRAPH_URL}/trust-flow/{fake_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trust_flow_with_weight(db: AsyncSession):
    """Trust flow preserves attestation weight."""
    from src.graph.trust_flow import compute_trust_flow

    target = _make_entity(db)
    attester = _make_entity(db)
    await db.flush()

    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester.id,
        target_entity_id=target.id,
        attestation_type="safe",
        weight=0.95,
    ))
    await db.flush()

    result = await compute_trust_flow(db, target.id)
    assert result["attestations"][0]["weight"] == 0.95


@pytest.mark.asyncio
async def test_trust_flow_max_depth_5(db: AsyncSession):
    """Trust flow works at max depth 5."""
    from src.graph.trust_flow import compute_trust_flow

    entities = []
    for _ in range(6):
        e = _make_entity(db)
        entities.append(e)
    await db.flush()

    # Chain: e0 <- e1 <- e2 <- e3 <- e4 <- e5
    for i in range(5):
        db.add(TrustAttestation(
            id=uuid.uuid4(),
            attester_entity_id=entities[i + 1].id,
            target_entity_id=entities[i].id,
            attestation_type="competent",
            weight=0.5,
        ))
    await db.flush()

    result = await compute_trust_flow(db, entities[0].id, max_depth=5)
    # Should have at least 1 attestation at root level
    assert len(result["attestations"]) >= 1
