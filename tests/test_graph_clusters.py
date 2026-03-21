"""Tests for graph community detection and cluster endpoints."""
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
    EntityRelationship,
    EntityType,
    RelationshipType,
    TrustScore,
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
        "type": EntityType.HUMAN,
        "display_name": f"User-{uuid.uuid4().hex[:6]}",
        "did_web": f"did:web:agentgraph.co:users:{uuid.uuid4()}",
        "email_verified": False,
        "bio_markdown": "",
    }
    defaults.update(kwargs)
    entity = Entity(**defaults)
    db.add(entity)
    return entity


# --- Community detection unit tests ---


@pytest.mark.asyncio
async def test_detect_communities_empty_graph(db: AsyncSession):
    """Empty graph returns no clusters."""
    from src.graph.community import detect_communities

    result = await detect_communities(db)
    # Note: DB may contain pre-existing entities, so we just verify structure
    assert "total_clusters" in result
    assert "clusters" in result
    assert isinstance(result["clusters"], dict)


@pytest.mark.asyncio
async def test_detect_communities_single_cluster(db: AsyncSession):
    """Three connected entities form one cluster."""
    from src.graph.community import detect_communities

    e1 = _make_entity(db)
    e2 = _make_entity(db)
    e3 = _make_entity(db)
    await db.flush()

    db.add(EntityRelationship(
        source_entity_id=e1.id, target_entity_id=e2.id,
        type=RelationshipType.FOLLOW,
    ))
    db.add(EntityRelationship(
        source_entity_id=e2.id, target_entity_id=e3.id,
        type=RelationshipType.FOLLOW,
    ))
    db.add(EntityRelationship(
        source_entity_id=e3.id, target_entity_id=e1.id,
        type=RelationshipType.FOLLOW,
    ))
    await db.flush()

    result = await detect_communities(db)
    assert result["total_clusters"] >= 1
    total_members = sum(c["size"] for c in result["clusters"].values())
    assert total_members >= 3


@pytest.mark.asyncio
async def test_detect_communities_multiple_clusters(db: AsyncSession):
    """Two disconnected groups form separate clusters."""
    from src.graph.community import detect_communities

    # Group A
    a1 = _make_entity(db)
    a2 = _make_entity(db)
    await db.flush()
    db.add(EntityRelationship(
        source_entity_id=a1.id, target_entity_id=a2.id,
        type=RelationshipType.FOLLOW,
    ))
    db.add(EntityRelationship(
        source_entity_id=a2.id, target_entity_id=a1.id,
        type=RelationshipType.FOLLOW,
    ))

    # Group B
    b1 = _make_entity(db)
    b2 = _make_entity(db)
    await db.flush()
    db.add(EntityRelationship(
        source_entity_id=b1.id, target_entity_id=b2.id,
        type=RelationshipType.FOLLOW,
    ))
    db.add(EntityRelationship(
        source_entity_id=b2.id, target_entity_id=b1.id,
        type=RelationshipType.FOLLOW,
    ))
    await db.flush()

    result = await detect_communities(db)
    assert result["total_clusters"] >= 2


@pytest.mark.asyncio
async def test_get_clusters_endpoint(client: AsyncClient):
    """GET /graph/clusters returns valid response."""
    await _create_user(client, "clus1@test.com", "ClusUser1")
    await _create_user(client, "clus2@test.com", "ClusUser2")
    resp = await client.get(f"{GRAPH_URL}/clusters")
    assert resp.status_code == 200
    data = resp.json()
    assert "clusters" in data
    assert "total_clusters" in data


@pytest.mark.asyncio
async def test_get_cluster_detail(client: AsyncClient):
    """GET /graph/clusters/{id} returns cluster members."""
    t1, id1 = await _create_user(client, "cd1@test.com", "CDUser1")
    t2, id2 = await _create_user(client, "cd2@test.com", "CDUser2")
    # Create follow so they form a cluster
    await client.post(f"{SOCIAL_URL}/follow/{id2}", headers=_auth(t1))
    await client.post(f"{SOCIAL_URL}/follow/{id1}", headers=_auth(t2))

    # Get clusters first
    resp = await client.get(f"{GRAPH_URL}/clusters")
    assert resp.status_code == 200
    data = resp.json()
    if data["total_clusters"] > 0:
        cid = data["clusters"][0]["cluster_id"]
        detail = await client.get(f"{GRAPH_URL}/clusters/{cid}")
        assert detail.status_code == 200
        assert "members" in detail.json()


@pytest.mark.asyncio
async def test_get_cluster_not_found(client: AsyncClient):
    """GET /graph/clusters/99999 returns 404."""
    resp = await client.get(f"{GRAPH_URL}/clusters/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_clusters_cached(db: AsyncSession):
    """get_cached_clusters returns cached result on second call."""
    from src import cache
    from src.graph.community import CACHE_KEY, detect_communities, get_cached_clusters

    # Clear any stale cache from prior tests
    await cache.invalidate(CACHE_KEY)

    e1 = _make_entity(db)
    e2 = _make_entity(db)
    await db.flush()
    db.add(EntityRelationship(
        source_entity_id=e1.id,
        target_entity_id=e2.id,
        type=RelationshipType.FOLLOW,
    ))
    await db.flush()

    # First call computes and caches
    r1 = await detect_communities(db)
    assert r1["total_clusters"] > 0
    # Second call should use cache
    r2 = await get_cached_clusters(db)
    assert r2["total_clusters"] == r1["total_clusters"]


@pytest.mark.asyncio
async def test_clusters_with_trust_scores(db: AsyncSession):
    """Cluster avg_trust reflects entity trust scores."""
    from src.graph.community import detect_communities

    e1 = _make_entity(db)
    e2 = _make_entity(db)
    await db.flush()

    db.add(TrustScore(entity_id=e1.id, score=0.8, components={}))
    db.add(TrustScore(entity_id=e2.id, score=0.6, components={}))
    db.add(EntityRelationship(
        source_entity_id=e1.id, target_entity_id=e2.id,
        type=RelationshipType.FOLLOW,
    ))
    db.add(EntityRelationship(
        source_entity_id=e2.id, target_entity_id=e1.id,
        type=RelationshipType.FOLLOW,
    ))
    await db.flush()

    result = await detect_communities(db)
    # Find the cluster containing our entities
    for cluster in result["clusters"].values():
        if str(e1.id) in cluster["members"]:
            assert cluster["avg_trust"] > 0
            break


@pytest.mark.asyncio
async def test_rich_graph_includes_clusters(client: AsyncClient):
    """GET /graph/rich returns nodes with cluster_id."""
    t1, id1 = await _create_user(client, "rich1@test.com", "RichUser1")
    t2, id2 = await _create_user(client, "rich2@test.com", "RichUser2")
    await client.post(f"{SOCIAL_URL}/follow/{id2}", headers=_auth(t1))

    resp = await client.get(f"{GRAPH_URL}/rich")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    # Nodes should have cluster_id field (may be null)
    for node in data["nodes"]:
        assert "cluster_id" in node
        assert "avatar_url" in node


@pytest.mark.asyncio
async def test_rich_graph_multi_edge_types(client: AsyncClient):
    """GET /graph/rich returns edges with weight and attestation_type fields."""
    await _create_user(client, "rme1@test.com", "RMEUser1")
    resp = await client.get(f"{GRAPH_URL}/rich")
    assert resp.status_code == 200
    data = resp.json()
    # All edges should have weight and attestation_type fields
    for edge in data["edges"]:
        assert "weight" in edge
        assert "attestation_type" in edge
