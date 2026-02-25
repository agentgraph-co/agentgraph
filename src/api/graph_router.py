"""Social graph visualization and analysis endpoints.

Provides graph data exports for D3/Three.js frontends,
ego-graph queries, and network statistics.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src import cache
from src.api.deps import get_optional_entity
from src.api.privacy import check_privacy_access
from src.api.rate_limit import rate_limit_reads
from src.database import get_db
from src.models import (
    Entity,
    EntityRelationship,
    EntityType,
    Listing,
    Post,
    PrivacyTier,
    RelationshipType,
    Submolt,
    TrustAttestation,
    TrustScore,
)

router = APIRouter(prefix="/graph", tags=["graph"])


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    trust_score: float | None = None
    is_active: bool = True
    cluster_id: int | None = None
    avatar_url: str | None = None


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str
    weight: float | None = None
    attestation_type: str | None = None


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    node_count: int
    edge_count: int


class NetworkStatsResponse(BaseModel):
    total_entities: int
    total_humans: int
    total_agents: int
    total_follows: int
    avg_followers: float
    avg_following: float
    most_followed: list[dict]
    most_connected: list[dict]


class PublicPlatformStats(BaseModel):
    total_humans: int
    total_agents: int
    total_posts: int
    total_communities: int
    total_listings: int


class ClusterInfo(BaseModel):
    cluster_id: int
    size: int
    avg_trust: float
    member_count: int
    dominant_type: str


class ClustersResponse(BaseModel):
    clusters: list[ClusterInfo]
    total_clusters: int


class ClusterDetailResponse(BaseModel):
    cluster_id: int
    members: list[GraphNode]
    edges: list[GraphEdge]
    size: int
    avg_trust: float
    dominant_type: str



# --- Helper: build privacy filter ---


def _build_privacy_filter(current_entity):
    """Build an SQLAlchemy privacy filter clause."""
    from sqlalchemy import or_

    if current_entity is None:
        return Entity.privacy_tier == PrivacyTier.PUBLIC

    following_subq = (
        select(EntityRelationship.target_entity_id)
        .where(
            EntityRelationship.source_entity_id == current_entity.id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    privacy_filter = or_(
        Entity.privacy_tier == PrivacyTier.PUBLIC,
        Entity.id == current_entity.id,
    )
    if current_entity.email_verified:
        privacy_filter = privacy_filter | (
            Entity.privacy_tier == PrivacyTier.VERIFIED
        )
    privacy_filter = privacy_filter | (
        (Entity.privacy_tier == PrivacyTier.PRIVATE)
        & Entity.id.in_(following_subq)
    )
    return privacy_filter


@router.get(
    "", response_model=GraphResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_full_graph(
    limit: int = Query(500, ge=1, le=2000),
    entity_type: str | None = Query(None, pattern="^(human|agent)$"),
    min_trust: float | None = Query(None, ge=0.0, le=1.0),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get the social graph as nodes and edges for visualization.

    Returns entities as nodes and follow relationships as edges.
    Supports filtering by entity type and minimum trust score.
    Excludes PRIVATE-tier entities unless the viewer follows them.
    """
    from sqlalchemy import or_

    # Build entity query — exclude PRIVATE entities unless viewer follows them
    entity_query = select(Entity).where(
        Entity.is_active.is_(True),
    )
    if current_entity is None:
        entity_query = entity_query.where(
            Entity.privacy_tier == PrivacyTier.PUBLIC,
        )
    else:
        following_subq = (
            select(EntityRelationship.target_entity_id)
            .where(
                EntityRelationship.source_entity_id == current_entity.id,
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
        )
        privacy_filter = or_(
            Entity.privacy_tier == PrivacyTier.PUBLIC,
            Entity.id == current_entity.id,
        )
        if current_entity.email_verified:
            privacy_filter = privacy_filter | (
                Entity.privacy_tier == PrivacyTier.VERIFIED
            )
        privacy_filter = privacy_filter | (
            (Entity.privacy_tier == PrivacyTier.PRIVATE)
            & Entity.id.in_(following_subq)
        )
        entity_query = entity_query.where(privacy_filter)
    if entity_type:
        entity_query = entity_query.where(Entity.type == entity_type)

    entity_query = entity_query.limit(limit)
    result = await db.execute(entity_query)
    entities = result.scalars().all()
    entity_ids = {e.id for e in entities}

    # Get trust scores for these entities
    trust_result = await db.execute(
        select(TrustScore).where(
            TrustScore.entity_id.in_(entity_ids),
        )
    )
    trust_map = {ts.entity_id: ts.score for ts in trust_result.scalars().all()}

    # Filter by trust score if requested
    if min_trust is not None:
        entities = [
            e for e in entities
            if trust_map.get(e.id, 0.0) >= min_trust
        ]
        entity_ids = {e.id for e in entities}

    # Get relationships between visible entities
    rel_result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id.in_(entity_ids),
            EntityRelationship.target_entity_id.in_(entity_ids),
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    relationships = rel_result.scalars().all()

    nodes = [
        GraphNode(
            id=str(e.id),
            label=e.display_name,
            type=e.type.value,
            trust_score=trust_map.get(e.id),
            is_active=e.is_active,
        )
        for e in entities
    ]
    edges = [
        GraphEdge(
            source=str(r.source_entity_id),
            target=str(r.target_entity_id),
            type=r.type.value,
        )
        for r in relationships
    ]

    return GraphResponse(
        nodes=nodes,
        edges=edges,
        node_count=len(nodes),
        edge_count=len(edges),
    )


@router.get(
    "/ego/{entity_id}", response_model=GraphResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_ego_graph(
    entity_id: uuid.UUID,
    depth: int = Query(1, ge=1, le=3),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get the ego graph centered on a specific entity.

    Returns the entity, its direct connections (depth=1),
    and optionally connections of connections (depth=2-3).
    """
    center = await db.get(Entity, entity_id)
    if center is None or not center.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Privacy check on the center entity
    if not await check_privacy_access(center, current_entity, db):
        raise HTTPException(
            status_code=403,
            detail="This entity's graph is private",
        )

    # Collect entity IDs at each depth level
    visited = {entity_id}
    frontier = {entity_id}

    for _ in range(depth):
        if not frontier:
            break
        # Get all relationships where frontier entities are source or target
        outgoing = await db.execute(
            select(EntityRelationship).where(
                EntityRelationship.source_entity_id.in_(frontier),
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
        )
        incoming = await db.execute(
            select(EntityRelationship).where(
                EntityRelationship.target_entity_id.in_(frontier),
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
        )

        new_ids = set()
        for r in outgoing.scalars().all():
            new_ids.add(r.target_entity_id)
        for r in incoming.scalars().all():
            new_ids.add(r.source_entity_id)

        frontier = new_ids - visited
        visited |= frontier

    # Fetch all entities, filtering out PRIVATE-tier unless viewer has access
    from sqlalchemy import or_

    entity_fetch_query = select(Entity).where(
        Entity.id.in_(visited),
        Entity.is_active.is_(True),
    )
    if current_entity is None:
        entity_fetch_query = entity_fetch_query.where(
            Entity.privacy_tier == PrivacyTier.PUBLIC,
        )
    else:
        ego_following_subq = (
            select(EntityRelationship.target_entity_id)
            .where(
                EntityRelationship.source_entity_id == current_entity.id,
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
        )
        ego_privacy = or_(
            Entity.privacy_tier == PrivacyTier.PUBLIC,
            Entity.id == current_entity.id,
        )
        if current_entity.email_verified:
            ego_privacy = ego_privacy | (
                Entity.privacy_tier == PrivacyTier.VERIFIED
            )
        ego_privacy = ego_privacy | (
            (Entity.privacy_tier == PrivacyTier.PRIVATE)
            & Entity.id.in_(ego_following_subq)
        )
        entity_fetch_query = entity_fetch_query.where(ego_privacy)

    result = await db.execute(entity_fetch_query)
    entities = result.scalars().all()
    entity_ids = {e.id for e in entities}

    # Trust scores
    trust_result = await db.execute(
        select(TrustScore).where(
            TrustScore.entity_id.in_(entity_ids),
        )
    )
    trust_map = {ts.entity_id: ts.score for ts in trust_result.scalars().all()}

    # Relationships between visible entities
    rel_result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id.in_(entity_ids),
            EntityRelationship.target_entity_id.in_(entity_ids),
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    relationships = rel_result.scalars().all()

    nodes = [
        GraphNode(
            id=str(e.id),
            label=e.display_name,
            type=e.type.value,
            trust_score=trust_map.get(e.id),
            is_active=e.is_active,
        )
        for e in entities
    ]
    edges = [
        GraphEdge(
            source=str(r.source_entity_id),
            target=str(r.target_entity_id),
            type=r.type.value,
        )
        for r in relationships
    ]

    return GraphResponse(
        nodes=nodes,
        edges=edges,
        node_count=len(nodes),
        edge_count=len(edges),
    )


# --- NEW: Cluster endpoints ---


@router.get(
    "/clusters", response_model=ClustersResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_clusters(
    db: AsyncSession = Depends(get_db),
):
    """Get community clusters with metadata from Louvain detection."""
    from src.graph.community import get_cached_clusters

    data = await get_cached_clusters(db)
    clusters_list = []
    for cid_str, info in data.get("clusters", {}).items():
        clusters_list.append(
            ClusterInfo(
                cluster_id=int(cid_str),
                size=info["size"],
                avg_trust=info["avg_trust"],
                member_count=info["member_count"],
                dominant_type=info["dominant_type"],
            )
        )

    return ClustersResponse(
        clusters=clusters_list,
        total_clusters=data.get("total_clusters", 0),
    )


@router.get(
    "/clusters/{cluster_id}", response_model=ClusterDetailResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_cluster_detail(
    cluster_id: int,
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get a single cluster's members and inter-cluster edges."""
    from src.graph.community import get_cached_clusters

    data = await get_cached_clusters(db)
    cid_str = str(cluster_id)

    if cid_str not in data.get("clusters", {}):
        raise HTTPException(status_code=404, detail="Cluster not found")

    cluster_info = data["clusters"][cid_str]
    member_id_strs = cluster_info["members"]

    member_uuids = []
    for mid_str in member_id_strs:
        try:
            member_uuids.append(uuid.UUID(mid_str))
        except ValueError:
            continue

    if not member_uuids:
        return ClusterDetailResponse(
            cluster_id=cluster_id,
            members=[],
            edges=[],
            size=0,
            avg_trust=cluster_info["avg_trust"],
            dominant_type=cluster_info["dominant_type"],
        )

    entity_result = await db.execute(
        select(Entity).where(
            Entity.id.in_(member_uuids),
            Entity.is_active.is_(True),
            _build_privacy_filter(current_entity),
        )
    )
    entities = entity_result.scalars().all()
    entity_ids = {e.id for e in entities}

    trust_result = await db.execute(
        select(TrustScore).where(TrustScore.entity_id.in_(entity_ids))
    )
    trust_map = {ts.entity_id: ts.score for ts in trust_result.scalars().all()}

    rel_result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id.in_(entity_ids),
            EntityRelationship.target_entity_id.in_(entity_ids),
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    relationships = rel_result.scalars().all()

    nodes = [
        GraphNode(
            id=str(e.id),
            label=e.display_name,
            type=e.type.value,
            trust_score=trust_map.get(e.id),
            is_active=e.is_active,
            cluster_id=cluster_id,
            avatar_url=e.avatar_url,
        )
        for e in entities
    ]
    edges = [
        GraphEdge(
            source=str(r.source_entity_id),
            target=str(r.target_entity_id),
            type=r.type.value,
        )
        for r in relationships
    ]

    return ClusterDetailResponse(
        cluster_id=cluster_id,
        members=nodes,
        edges=edges,
        size=len(nodes),
        avg_trust=cluster_info["avg_trust"],
        dominant_type=cluster_info["dominant_type"],
    )


# --- NEW: Trust flow endpoint ---


@router.get(
    "/trust-flow/{entity_id}",
    dependencies=[Depends(rate_limit_reads)],
)
async def get_trust_flow(
    entity_id: uuid.UUID,
    depth: int = Query(2, ge=1, le=5),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get the trust attestation chain for an entity."""
    target = await db.get(Entity, entity_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    if not await check_privacy_access(target, current_entity, db):
        raise HTTPException(
            status_code=403,
            detail="This entity's trust data is private",
        )

    from src.graph.trust_flow import compute_trust_flow

    result = await compute_trust_flow(db, entity_id, max_depth=depth)
    return result


# --- NEW: Lineage tree endpoint ---


@router.get(
    "/lineage-tree/{entity_id}",
    dependencies=[Depends(rate_limit_reads)],
)
async def get_lineage_tree(
    entity_id: uuid.UUID,
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get the evolution fork tree for an entity."""
    target = await db.get(Entity, entity_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    if not await check_privacy_access(target, current_entity, db):
        raise HTTPException(
            status_code=403,
            detail="This entity's lineage data is private",
        )

    from src.graph.lineage import compute_lineage_tree

    result = await compute_lineage_tree(db, entity_id)
    return result


# --- NEW: Rich graph helper ---


async def _build_rich_graph(
    db: AsyncSession,
    entity_ids: set,
    entities: list,
    current_entity: Entity | None,
) -> GraphResponse:
    """Build a rich graph response with multi-edge types and cluster IDs."""
    from src.graph.community import get_cached_clusters

    trust_result = await db.execute(
        select(TrustScore).where(TrustScore.entity_id.in_(entity_ids))
    )
    trust_map = {ts.entity_id: ts.score for ts in trust_result.scalars().all()}

    cluster_data = await get_cached_clusters(db)
    node_cluster_map: dict[str, int] = {}
    for cid_str, info in cluster_data.get("clusters", {}).items():
        for mid_str in info.get("members", []):
            node_cluster_map[mid_str] = int(cid_str)

    all_rel_types = [
        RelationshipType.FOLLOW,
        RelationshipType.OPERATOR_AGENT,
        RelationshipType.COLLABORATION,
        RelationshipType.SERVICE,
    ]
    rel_result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id.in_(entity_ids),
            EntityRelationship.target_entity_id.in_(entity_ids),
            EntityRelationship.type.in_(all_rel_types),
        )
    )
    relationships = rel_result.scalars().all()

    att_result = await db.execute(
        select(TrustAttestation).where(
            TrustAttestation.attester_entity_id.in_(entity_ids),
            TrustAttestation.target_entity_id.in_(entity_ids),
        )
    )
    attestations = att_result.scalars().all()

    nodes = [
        GraphNode(
            id=str(e.id),
            label=e.display_name,
            type=e.type.value,
            trust_score=trust_map.get(e.id),
            is_active=e.is_active,
            cluster_id=node_cluster_map.get(str(e.id)),
            avatar_url=e.avatar_url,
        )
        for e in entities
    ]

    edges: list[GraphEdge] = [
        GraphEdge(
            source=str(r.source_entity_id),
            target=str(r.target_entity_id),
            type=r.type.value,
        )
        for r in relationships
    ]
    for att in attestations:
        edges.append(
            GraphEdge(
                source=str(att.attester_entity_id),
                target=str(att.target_entity_id),
                type="attestation",
                weight=att.weight,
                attestation_type=att.attestation_type,
            )
        )

    return GraphResponse(
        nodes=nodes, edges=edges,
        node_count=len(nodes), edge_count=len(edges),
    )


@router.get(
    "/rich", response_model=GraphResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_rich_graph(
    limit: int = Query(500, ge=1, le=2000),
    entity_type: str | None = Query(None, pattern="^(human|agent)$"),
    min_trust: float | None = Query(None, ge=0.0, le=1.0),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Full graph with multi-edge types, cluster IDs, and avatar_url."""
    entity_query = select(Entity).where(
        Entity.is_active.is_(True),
    ).where(_build_privacy_filter(current_entity))
    if entity_type:
        entity_query = entity_query.where(Entity.type == entity_type)
    entity_query = entity_query.limit(limit)
    result = await db.execute(entity_query)
    entities = result.scalars().all()
    entity_ids = {e.id for e in entities}
    if min_trust is not None:
        trust_result = await db.execute(
            select(TrustScore).where(TrustScore.entity_id.in_(entity_ids))
        )
        trust_map = {
            ts.entity_id: ts.score for ts in trust_result.scalars().all()
        }
        entities = [
            e for e in entities if trust_map.get(e.id, 0.0) >= min_trust
        ]
        entity_ids = {e.id for e in entities}
    return await _build_rich_graph(db, entity_ids, entities, current_entity)


@router.get(
    "/ego/{entity_id}/rich", response_model=GraphResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_rich_ego_graph(
    entity_id: uuid.UUID,
    depth: int = Query(1, ge=1, le=3),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Enhanced ego graph with multi-edge types and cluster IDs."""
    center = await db.get(Entity, entity_id)
    if center is None or not center.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    if not await check_privacy_access(center, current_entity, db):
        raise HTTPException(
            status_code=403,
            detail="This entity's graph is private",
        )

    visited = {entity_id}
    frontier = {entity_id}

    for _ in range(depth):
        if not frontier:
            break
        outgoing = await db.execute(
            select(EntityRelationship).where(
                EntityRelationship.source_entity_id.in_(frontier),
            )
        )
        incoming = await db.execute(
            select(EntityRelationship).where(
                EntityRelationship.target_entity_id.in_(frontier),
            )
        )

        new_ids = set()
        for r in outgoing.scalars().all():
            new_ids.add(r.target_entity_id)
        for r in incoming.scalars().all():
            new_ids.add(r.source_entity_id)

        frontier = new_ids - visited
        visited |= frontier

    entity_fetch_query = select(Entity).where(
        Entity.id.in_(visited),
        Entity.is_active.is_(True),
    ).where(_build_privacy_filter(current_entity))

    result = await db.execute(entity_fetch_query)
    entities = result.scalars().all()
    entity_ids = {e.id for e in entities}

    return await _build_rich_graph(db, entity_ids, entities, current_entity)


@router.get(
    "/mutual/{entity_a_id}/{entity_b_id}",
    dependencies=[Depends(rate_limit_reads)],
)
async def get_mutual_follows(
    entity_a_id: uuid.UUID,
    entity_b_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get entities that both A and B follow (mutual connections)."""
    from sqlalchemy.orm import aliased

    for eid in (entity_a_id, entity_b_id):
        e = await db.get(Entity, eid)
        if e is None or not e.is_active:
            raise HTTPException(status_code=404, detail=f"Entity {eid} not found")

    rel_a = aliased(EntityRelationship)
    rel_b = aliased(EntityRelationship)

    query = (
        select(Entity.id, Entity.display_name, Entity.type)
        .join(rel_a, rel_a.target_entity_id == Entity.id)
        .join(rel_b, rel_b.target_entity_id == Entity.id)
        .where(
            rel_a.source_entity_id == entity_a_id,
            rel_a.type == RelationshipType.FOLLOW,
            rel_b.source_entity_id == entity_b_id,
            rel_b.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
        )
        .limit(limit)
    )
    result = await db.execute(query)
    mutuals = [
        {
            "id": str(row[0]),
            "display_name": row[1],
            "type": row[2].value if hasattr(row[2], "value") else row[2],
        }
        for row in result.all()
    ]
    return {
        "entity_a": str(entity_a_id),
        "entity_b": str(entity_b_id),
        "mutual_follows": mutuals,
        "count": len(mutuals),
    }


@router.get(
    "/path/{source_id}/{target_id}",
    dependencies=[Depends(rate_limit_reads)],
)
async def get_shortest_path(
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    max_depth: int = Query(4, ge=1, le=6),
    db: AsyncSession = Depends(get_db),
):
    """Find shortest follow-path between two entities via BFS."""
    for eid in (source_id, target_id):
        e = await db.get(Entity, eid)
        if e is None or not e.is_active:
            raise HTTPException(status_code=404, detail=f"Entity {eid} not found")

    if source_id == target_id:
        return {"path": [str(source_id)], "length": 0}

    # BFS
    visited: dict[uuid.UUID, uuid.UUID | None] = {source_id: None}
    frontier = {source_id}

    for _ in range(max_depth):
        if not frontier:
            break
        result = await db.execute(
            select(
                EntityRelationship.source_entity_id,
                EntityRelationship.target_entity_id,
            ).where(
                EntityRelationship.source_entity_id.in_(frontier),
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
        )
        next_frontier: set[uuid.UUID] = set()
        for src, tgt in result.all():
            if tgt not in visited:
                visited[tgt] = src
                next_frontier.add(tgt)
                if tgt == target_id:
                    # Reconstruct path
                    path = []
                    current: uuid.UUID | None = target_id
                    while current is not None:
                        path.append(str(current))
                        current = visited[current]
                    path.reverse()
                    return {"path": path, "length": len(path) - 1}
        frontier = next_frontier

    return {"path": [], "length": -1, "message": "No path found within depth limit"}


@router.get(
    "/stats", response_model=NetworkStatsResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_network_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get network-level statistics for the social graph.

    Excludes PRIVATE-tier entities from counts.
    """
    total_entities = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.is_active.is_(True),
            Entity.privacy_tier != PrivacyTier.PRIVATE,
        )
    ) or 0

    total_humans = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.is_active.is_(True),
            Entity.type == EntityType.HUMAN,
            Entity.privacy_tier != PrivacyTier.PRIVATE,
        )
    ) or 0

    total_agents = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.is_active.is_(True),
            Entity.type == EntityType.AGENT,
            Entity.privacy_tier != PrivacyTier.PRIVATE,
        )
    ) or 0

    total_follows = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    ) or 0

    # In a global view, avg_followers == avg_following because each follow
    # edge is one outgoing and one incoming relationship, but we compute
    # them separately for clarity and to avoid copy-paste confusion.
    avg_followers = (
        total_follows / total_entities if total_entities > 0 else 0.0
    )
    avg_following = (
        total_follows / total_entities if total_entities > 0 else 0.0
    )

    # Most followed entities (exclude PRIVATE)
    most_followed_q = (
        select(
            Entity.id,
            Entity.display_name,
            Entity.type,
            func.count(EntityRelationship.id).label("follower_count"),
        )
        .join(
            EntityRelationship,
            EntityRelationship.target_entity_id == Entity.id,
        )
        .where(
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
            Entity.privacy_tier != PrivacyTier.PRIVATE,
        )
        .group_by(Entity.id, Entity.display_name, Entity.type)
        .order_by(func.count(EntityRelationship.id).desc())
        .limit(10)
    )
    most_followed_result = await db.execute(most_followed_q)
    most_followed = [
        {
            "id": str(row[0]),
            "display_name": row[1],
            "type": row[2].value if hasattr(row[2], "value") else row[2],
            "follower_count": row[3],
        }
        for row in most_followed_result.fetchall()
    ]

    # Most connected (followers + following, exclude PRIVATE)
    most_connected_q = (
        select(
            Entity.id,
            Entity.display_name,
            Entity.type,
            func.count(EntityRelationship.id).label("connection_count"),
        )
        .join(
            EntityRelationship,
            (EntityRelationship.source_entity_id == Entity.id)
            | (EntityRelationship.target_entity_id == Entity.id),
        )
        .where(
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
            Entity.privacy_tier != PrivacyTier.PRIVATE,
        )
        .group_by(Entity.id, Entity.display_name, Entity.type)
        .order_by(func.count(EntityRelationship.id).desc())
        .limit(10)
    )
    most_connected_result = await db.execute(most_connected_q)
    most_connected = [
        {
            "id": str(row[0]),
            "display_name": row[1],
            "type": row[2].value if hasattr(row[2], "value") else row[2],
            "connection_count": row[3],
        }
        for row in most_connected_result.fetchall()
    ]

    return NetworkStatsResponse(
        total_entities=total_entities,
        total_humans=total_humans,
        total_agents=total_agents,
        total_follows=total_follows,
        avg_followers=round(avg_followers, 2),
        avg_following=round(avg_following, 2),
        most_followed=most_followed,
        most_connected=most_connected,
    )


@router.get(
    "/public-stats", response_model=PublicPlatformStats,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_public_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get lightweight public platform statistics for the landing page."""
    cached = await cache.get("public_stats")
    if cached is not None:
        return cached

    total_humans = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.is_active.is_(True),
            Entity.type == EntityType.HUMAN,
        )
    ) or 0

    total_agents = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.is_active.is_(True),
            Entity.type == EntityType.AGENT,
        )
    ) or 0

    total_posts = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.is_hidden.is_(False),
            Post.parent_post_id.is_(None),
        )
    ) or 0

    total_communities = await db.scalar(
        select(func.count()).select_from(Submolt).where(
            Submolt.is_active.is_(True),
        )
    ) or 0

    total_listings = await db.scalar(
        select(func.count()).select_from(Listing).where(
            Listing.is_active.is_(True),
        )
    ) or 0

    result = PublicPlatformStats(
        total_humans=total_humans,
        total_agents=total_agents,
        total_posts=total_posts,
        total_communities=total_communities,
        total_listings=total_listings,
    )
    await cache.set("public_stats", result.model_dump(), ttl=cache.TTL_MEDIUM)
    return result
