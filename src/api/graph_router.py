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
from src.api.rate_limit import rate_limit_reads
from src.database import get_db
from src.models import (
    Entity,
    EntityRelationship,
    Listing,
    Post,
    RelationshipType,
    Submolt,
    TrustScore,
)

router = APIRouter(prefix="/graph", tags=["graph"])


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    trust_score: float | None = None
    is_active: bool = True


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str


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


@router.get(
    "", response_model=GraphResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_full_graph(
    limit: int = Query(500, ge=1, le=2000),
    entity_type: str | None = Query(None, pattern="^(human|agent)$"),
    min_trust: float | None = Query(None, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    """Get the social graph as nodes and edges for visualization.

    Returns entities as nodes and follow relationships as edges.
    Supports filtering by entity type and minimum trust score.
    """
    # Build entity query
    entity_query = select(Entity).where(
        Entity.is_active.is_(True),
    )
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
    db: AsyncSession = Depends(get_db),
):
    """Get the ego graph centered on a specific entity.

    Returns the entity, its direct connections (depth=1),
    and optionally connections of connections (depth=2-3).
    """
    center = await db.get(Entity, entity_id)
    if center is None or not center.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

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

    # Fetch all entities
    result = await db.execute(
        select(Entity).where(
            Entity.id.in_(visited),
            Entity.is_active.is_(True),
        )
    )
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
    """Get network-level statistics for the social graph."""
    total_entities = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.is_active.is_(True),
        )
    ) or 0

    total_humans = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.is_active.is_(True),
            Entity.type == "human",
        )
    ) or 0

    total_agents = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.is_active.is_(True),
            Entity.type == "agent",
        )
    ) or 0

    total_follows = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    ) or 0

    avg_followers = (
        total_follows / total_entities if total_entities > 0 else 0.0
    )

    # Most followed entities
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

    # Most connected (followers + following)
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
        avg_following=round(avg_followers, 2),
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
            Entity.type == "human",
        )
    ) or 0

    total_agents = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.is_active.is_(True),
            Entity.type == "agent",
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
