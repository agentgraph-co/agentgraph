"""Louvain community detection for the AgentGraph social network.

Uses networkx + python-louvain to detect communities (clusters) in the
follow graph.  Results are cached in Redis for fast retrieval.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any

import community as community_louvain
import networkx as nx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src import cache
from src.models import Entity, EntityRelationship, RelationshipType, TrustScore

logger = logging.getLogger(__name__)

CACHE_KEY = "graph:clusters"


async def detect_communities(db: AsyncSession) -> dict[str, Any]:
    """Load follow graph from DB, run Louvain community detection, return clusters.

    Returns::

        {
            "clusters": {
                "0": {"members": [uuid_str, ...], "size": N, "avg_trust": float},
                ...
            },
            "total_clusters": int,
        }
    """
    # 1. Load active entities
    entity_result = await db.execute(
        select(Entity.id, Entity.type, Entity.display_name).where(
            Entity.is_active.is_(True),
        )
    )
    entities = entity_result.all()

    if not entities:
        return {"clusters": {}, "total_clusters": 0}

    entity_ids = {row[0] for row in entities}
    entity_type_map: dict[Any, str] = {
        row[0]: row[1].value if hasattr(row[1], "value") else str(row[1])
        for row in entities
    }

    # 2. Load FOLLOW relationships
    rel_result = await db.execute(
        select(
            EntityRelationship.source_entity_id,
            EntityRelationship.target_entity_id,
        ).where(
            EntityRelationship.type == RelationshipType.FOLLOW,
            EntityRelationship.source_entity_id.in_(entity_ids),
            EntityRelationship.target_entity_id.in_(entity_ids),
        )
    )
    relationships = rel_result.all()

    # 3. Build undirected networkx graph
    graph = nx.Graph()
    for eid in entity_ids:
        graph.add_node(str(eid))

    for src, tgt in relationships:
        graph.add_edge(str(src), str(tgt))

    # 4. Run Louvain
    if len(graph.nodes) == 0:
        return {"clusters": {}, "total_clusters": 0}

    if len(graph.edges) == 0:
        # No edges — each node is its own cluster
        partition: dict[str, int] = {
            node: idx for idx, node in enumerate(graph.nodes)
        }
    else:
        partition = community_louvain.best_partition(graph)

    # 5. Load trust scores for avg_trust calculation
    trust_result = await db.execute(
        select(TrustScore.entity_id, TrustScore.score).where(
            TrustScore.entity_id.in_(entity_ids),
        )
    )
    trust_map: dict[Any, float] = {row[0]: row[1] for row in trust_result.all()}

    # 6. Group by cluster
    clusters_raw: dict[int, list[str]] = {}
    for node_id_str, cluster_id in partition.items():
        clusters_raw.setdefault(cluster_id, []).append(node_id_str)

    clusters: dict[str, dict[str, Any]] = {}
    for cluster_id, members in clusters_raw.items():
        trust_scores = []
        type_counts: dict[str, int] = {}
        for mid_str in members:
            try:
                mid = _uuid.UUID(mid_str)
            except ValueError:
                continue
            ts = trust_map.get(mid)
            if ts is not None:
                trust_scores.append(ts)
            etype = entity_type_map.get(mid, "human")
            type_counts[etype] = type_counts.get(etype, 0) + 1

        avg_trust = (
            round(sum(trust_scores) / len(trust_scores), 4)
            if trust_scores
            else 0.0
        )
        dominant_type = (
            max(type_counts, key=type_counts.get) if type_counts else "human"
        )

        clusters[str(cluster_id)] = {
            "members": members,
            "size": len(members),
            "member_count": len(members),
            "avg_trust": avg_trust,
            "dominant_type": dominant_type,
        }

    result = {
        "clusters": clusters,
        "total_clusters": len(clusters),
    }

    # 7. Cache result
    await cache.set(CACHE_KEY, result, ttl=cache.TTL_MEDIUM)

    return result


async def get_cached_clusters(db: AsyncSession) -> dict[str, Any]:
    """Try to get clusters from cache, falling back to computation."""
    cached = await cache.get(CACHE_KEY)
    if cached is not None:
        return cached
    return await detect_communities(db)
