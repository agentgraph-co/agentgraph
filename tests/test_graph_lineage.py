"""Tests for graph lineage tree computation and endpoint."""
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
    EvolutionRecord,
    PrivacyTier,
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
SOCIAL_URL = "/api/v1/social"


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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_entity(db: AsyncSession, **kwargs) -> Entity:
    defaults = {
        "id": uuid.uuid4(),
        "type": EntityType.AGENT,
        "display_name": f"Agent-{uuid.uuid4().hex[:6]}",
        "did_web": f"did:web:agentgraph.co:agents:{uuid.uuid4()}",
        "email_verified": False,
        "bio_markdown": "",
    }
    defaults.update(kwargs)
    entity = Entity(**defaults)
    db.add(entity)
    return entity


# --- Lineage tree unit tests ---


@pytest.mark.asyncio
async def test_lineage_no_records(db: AsyncSession):
    """Entity with no evolution records returns empty children."""
    from src.graph.lineage import compute_lineage_tree

    e = _make_entity(db)
    await db.flush()

    result = await compute_lineage_tree(db, e.id)
    assert result["entity_id"] == str(e.id)
    assert result["children"] == []
    assert result["version"] is None


@pytest.mark.asyncio
async def test_lineage_simple_chain(db: AsyncSession):
    """Parent entity with one forked child."""
    from src.graph.lineage import compute_lineage_tree

    parent = _make_entity(db, display_name="Parent")
    child = _make_entity(db, display_name="Child")
    await db.flush()

    db.add(EvolutionRecord(
        id=uuid.uuid4(),
        entity_id=parent.id,
        version="1.0.0",
        change_type="initial",
        change_summary="Initial version",
    ))
    db.add(EvolutionRecord(
        id=uuid.uuid4(),
        entity_id=child.id,
        version="1.0.0",
        forked_from_entity_id=parent.id,
        change_type="fork",
        change_summary="Forked from parent",
    ))
    await db.flush()

    result = await compute_lineage_tree(db, parent.id)
    assert result["entity_name"] == "Parent"
    assert result["version"] == "1.0.0"
    assert len(result["children"]) == 1
    assert result["children"][0]["entity_name"] == "Child"


@pytest.mark.asyncio
async def test_lineage_fork_tree(db: AsyncSession):
    """Parent with multiple forks."""
    from src.graph.lineage import compute_lineage_tree

    parent = _make_entity(db, display_name="Root")
    fork_a = _make_entity(db, display_name="ForkA")
    fork_b = _make_entity(db, display_name="ForkB")
    await db.flush()

    db.add(EvolutionRecord(
        id=uuid.uuid4(), entity_id=parent.id,
        version="1.0.0", change_type="initial", change_summary="Init",
    ))
    db.add(EvolutionRecord(
        id=uuid.uuid4(), entity_id=fork_a.id,
        version="1.0.0", forked_from_entity_id=parent.id,
        change_type="fork", change_summary="Fork A",
    ))
    db.add(EvolutionRecord(
        id=uuid.uuid4(), entity_id=fork_b.id,
        version="1.0.0", forked_from_entity_id=parent.id,
        change_type="fork", change_summary="Fork B",
    ))
    await db.flush()

    result = await compute_lineage_tree(db, parent.id)
    assert len(result["children"]) == 2
    child_names = {c["entity_name"] for c in result["children"]}
    assert "ForkA" in child_names
    assert "ForkB" in child_names


@pytest.mark.asyncio
async def test_lineage_endpoint(client: AsyncClient):
    """GET /graph/lineage-tree/{id} returns valid response."""
    t1, id1 = await _create_user(client, "lin1@test.com", "LinUser1")
    resp = await client.get(f"{GRAPH_URL}/lineage-tree/{id1}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == id1
    assert "children" in data


@pytest.mark.asyncio
async def test_lineage_privacy_check(client: AsyncClient, db: AsyncSession):
    """Private entity lineage requires follower access."""
    t1, id1 = await _create_user(client, "linp1@test.com", "LinPriv1")

    from sqlalchemy import update

    from src.models import Entity
    await db.execute(
        update(Entity).where(Entity.id == uuid.UUID(id1)).values(
            privacy_tier=PrivacyTier.PRIVATE,
        )
    )
    await db.flush()

    resp = await client.get(f"{GRAPH_URL}/lineage-tree/{id1}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_lineage_nonexistent_entity(client: AsyncClient):
    """Lineage for nonexistent entity returns 404."""
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"{GRAPH_URL}/lineage-tree/{fake_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_lineage_deep_tree(db: AsyncSession):
    """Lineage tree handles depth > 1."""
    from src.graph.lineage import compute_lineage_tree

    e1 = _make_entity(db, display_name="Gen1")
    e2 = _make_entity(db, display_name="Gen2")
    e3 = _make_entity(db, display_name="Gen3")
    await db.flush()

    db.add(EvolutionRecord(
        id=uuid.uuid4(), entity_id=e1.id,
        version="1.0.0", change_type="initial", change_summary="Init",
    ))
    db.add(EvolutionRecord(
        id=uuid.uuid4(), entity_id=e2.id,
        version="1.0.0", forked_from_entity_id=e1.id,
        change_type="fork", change_summary="Fork from Gen1",
    ))
    db.add(EvolutionRecord(
        id=uuid.uuid4(), entity_id=e3.id,
        version="1.0.0", forked_from_entity_id=e2.id,
        change_type="fork", change_summary="Fork from Gen2",
    ))
    await db.flush()

    result = await compute_lineage_tree(db, e1.id, max_depth=5)
    assert len(result["children"]) == 1
    assert result["children"][0]["entity_name"] == "Gen2"
    assert len(result["children"][0]["children"]) == 1
    assert result["children"][0]["children"][0]["entity_name"] == "Gen3"


@pytest.mark.asyncio
async def test_lineage_cross_entity_forks(db: AsyncSession):
    """Lineage correctly handles cross-entity forking."""
    from src.graph.lineage import compute_lineage_tree

    parent = _make_entity(db, display_name="ParentAgent")
    child = _make_entity(db, display_name="ChildAgent")
    await db.flush()

    db.add(EvolutionRecord(
        id=uuid.uuid4(), entity_id=child.id,
        version="2.0.0", forked_from_entity_id=parent.id,
        change_type="fork", change_summary="Forked v2",
    ))
    await db.flush()

    result = await compute_lineage_tree(db, parent.id)
    assert len(result["children"]) == 1
    assert result["children"][0]["entity_id"] == str(child.id)


@pytest.mark.asyncio
async def test_rich_ego_graph_endpoint(client: AsyncClient):
    """GET /graph/ego/{id}/rich returns valid rich ego graph."""
    t1, id1 = await _create_user(client, "rego1@test.com", "REgoUser1")
    resp = await client.get(f"{GRAPH_URL}/ego/{id1}/rich")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    for node in data["nodes"]:
        assert "cluster_id" in node
        assert "avatar_url" in node


@pytest.mark.asyncio
async def test_rich_ego_graph_includes_clusters(client: AsyncClient):
    """Rich ego graph includes cluster_id for connected nodes."""
    t1, id1 = await _create_user(client, "regc1@test.com", "REgcUser1")
    t2, id2 = await _create_user(client, "regc2@test.com", "REgcUser2")
    await client.post(f"{SOCIAL_URL}/follow/{id2}", headers=_auth(t1))

    resp = await client.get(f"{GRAPH_URL}/ego/{id1}/rich", headers=_auth(t1))
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_count"] >= 1
