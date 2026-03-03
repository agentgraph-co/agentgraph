"""Collusion detection engine for AgentGraph.

Provides three detectors that identify coordinated manipulation patterns:

- **Mutual attestation**: bidirectional attestation pairs (A attests B AND B attests A)
- **Attestation clique**: groups of 3+ entities with fully mutual attestations
- **Voting ring**: entities that consistently upvote each other's posts

All detectors are async, accept an AsyncSession, and return newly-created
AnomalyAlert records.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.models import (
    AnomalyAlert,
    Entity,
    Post,
    TrustAttestation,
    Vote,
    VoteDirection,
)
from src.safety.anomaly import _auto_flag_entity, _create_anomaly_alert

logger = logging.getLogger(__name__)

# Collusion alert types
COLLUSION_ALERT_TYPES = frozenset({
    "mutual_attestation",
    "attestation_cluster",
    "voting_ring",
})


# ---------------------------------------------------------------------------
# Detector 1 — Mutual attestation pairs
# ---------------------------------------------------------------------------


async def detect_mutual_attestation(
    db: AsyncSession,
    *,
    auto_flag: bool = False,
) -> list[AnomalyAlert]:
    """Detect bidirectional attestation pairs.

    Finds cases where entity A attested to B AND B attested to A.
    This is suspicious because it suggests coordinated trust inflation.

    Severity:
    - "medium" for a simple mutual pair
    - "high" if both entities share the same operator_id
    """
    ta1 = aliased(TrustAttestation, name="ta1")
    ta2 = aliased(TrustAttestation, name="ta2")

    # Self-join to find bidirectional attestation pairs
    result = await db.execute(
        select(
            ta1.attester_entity_id,
            ta1.target_entity_id,
            ta1.attestation_type.label("type_a_to_b"),
            ta2.attestation_type.label("type_b_to_a"),
            ta1.created_at.label("created_a_to_b"),
            ta2.created_at.label("created_b_to_a"),
        )
        .join(
            ta2,
            and_(
                ta1.attester_entity_id == ta2.target_entity_id,
                ta1.target_entity_id == ta2.attester_entity_id,
            ),
        )
        # Avoid duplicate pairs: only keep the pair where A < B (by UUID string)
        .where(ta1.attester_entity_id < ta1.target_entity_id)
    )
    rows = result.all()

    if not rows:
        return []

    # Collect unique entity IDs to check operator_id
    entity_ids: set[_uuid.UUID] = set()
    for row in rows:
        entity_ids.add(row[0])
        entity_ids.add(row[1])

    # Fetch operator_id for involved entities
    operator_result = await db.execute(
        select(Entity.id, Entity.operator_id).where(Entity.id.in_(entity_ids))
    )
    operator_map: dict[_uuid.UUID, _uuid.UUID | None] = {
        eid: op_id for eid, op_id in operator_result.all()
    }

    # Group by unique pair to avoid duplicate alerts for multiple attestation types
    pair_details: dict[tuple[_uuid.UUID, _uuid.UUID], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        entity_a = row[0]
        entity_b = row[1]
        pair_key = (entity_a, entity_b)
        pair_details[pair_key].append({
            "type_a_to_b": row[2],
            "type_b_to_a": row[3],
            "created_a_to_b": row[4].isoformat() if row[4] else None,
            "created_b_to_a": row[5].isoformat() if row[5] else None,
        })

    alerts: list[AnomalyAlert] = []
    for (entity_a, entity_b), attestation_pairs in pair_details.items():
        # Determine severity based on shared operator
        op_a = operator_map.get(entity_a)
        op_b = operator_map.get(entity_b)
        same_operator = (
            op_a is not None and op_b is not None and op_a == op_b
        )
        severity = "high" if same_operator else "medium"

        details: dict[str, Any] = {
            "entity_a": str(entity_a),
            "entity_b": str(entity_b),
            "same_operator": same_operator,
            "attestation_pairs": attestation_pairs,
        }
        if same_operator:
            details["operator_id"] = str(op_a)

        # Create alert for entity A
        alert = await _create_anomaly_alert(
            db,
            entity_id=entity_a,
            alert_type="mutual_attestation",
            z_score=0.0,
            severity=severity,
            details=details,
        )
        alerts.append(alert)

        if auto_flag:
            await _auto_flag_entity(
                db, entity_a,
                f"Collusion: mutual attestation with entity {entity_b}",
            )
            await _auto_flag_entity(
                db, entity_b,
                f"Collusion: mutual attestation with entity {entity_a}",
            )

    return alerts


# ---------------------------------------------------------------------------
# Detector 2 — Attestation cliques
# ---------------------------------------------------------------------------


async def detect_attestation_clique(
    db: AsyncSession,
    *,
    min_clique_size: int = 3,
    auto_flag: bool = False,
) -> list[AnomalyAlert]:
    """Detect groups of entities where all pairs have mutual attestations.

    Builds an undirected graph from mutual attestation pairs and finds
    cliques (fully connected subgraphs) of size >= min_clique_size.

    Severity: always "high" for cliques of 3+.
    """
    ta1 = aliased(TrustAttestation, name="ta1")
    ta2 = aliased(TrustAttestation, name="ta2")

    # Find all mutual pairs (A < B to deduplicate)
    result = await db.execute(
        select(
            ta1.attester_entity_id,
            ta1.target_entity_id,
        )
        .join(
            ta2,
            and_(
                ta1.attester_entity_id == ta2.target_entity_id,
                ta1.target_entity_id == ta2.attester_entity_id,
            ),
        )
        .where(ta1.attester_entity_id < ta1.target_entity_id)
        .distinct()
    )
    mutual_pairs = result.all()

    if not mutual_pairs:
        return []

    # Build adjacency graph (undirected)
    adjacency: dict[_uuid.UUID, set[_uuid.UUID]] = defaultdict(set)
    all_nodes: set[_uuid.UUID] = set()
    for entity_a, entity_b in mutual_pairs:
        adjacency[entity_a].add(entity_b)
        adjacency[entity_b].add(entity_a)
        all_nodes.add(entity_a)
        all_nodes.add(entity_b)

    # Find cliques using a simple approach:
    # For each node, check if its neighbors form cliques
    found_cliques: list[frozenset[_uuid.UUID]] = []

    # Use Bron-Kerbosch-like approach for small graphs
    # For each connected component, try all subsets of size >= min_clique_size
    # and verify they are cliques
    visited: set[_uuid.UUID] = set()

    for start_node in all_nodes:
        if start_node in visited:
            continue

        # BFS to find connected component
        component: set[_uuid.UUID] = set()
        queue = [start_node]
        while queue:
            node = queue.pop()
            if node in component:
                continue
            component.add(node)
            for neighbor in adjacency[node]:
                if neighbor not in component:
                    queue.append(neighbor)

        visited.update(component)

        # For the component, find maximal cliques
        # Use a simple approach: iterate over subsets of increasing size
        component_list = sorted(component)

        # Cap component size to avoid combinatorial explosion
        if len(component_list) > 50:
            # For large components, only check local neighborhoods
            component_list = component_list[:50]

        # Find all maximal cliques in this component
        _find_cliques_bk(
            adjacency, set(), set(component_list), set(),
            min_clique_size, found_cliques,
        )

    if not found_cliques:
        return []

    # Remove duplicate cliques (subsets of larger cliques)
    # Sort by size descending, then filter subsets
    found_cliques.sort(key=len, reverse=True)
    maximal_cliques: list[frozenset[_uuid.UUID]] = []
    for clique in found_cliques:
        if not any(clique.issubset(existing) for existing in maximal_cliques):
            maximal_cliques.append(clique)

    # Count total attestations between clique members
    alerts: list[AnomalyAlert] = []
    for clique in maximal_cliques:
        clique_list = sorted(str(eid) for eid in clique)

        # Count attestations between clique members
        clique_ids = list(clique)
        att_count_result = await db.execute(
            select(func.count()).select_from(TrustAttestation).where(
                TrustAttestation.attester_entity_id.in_(clique_ids),
                TrustAttestation.target_entity_id.in_(clique_ids),
            )
        )
        total_attestations = att_count_result.scalar() or 0

        details: dict[str, Any] = {
            "clique_size": len(clique),
            "entity_ids": clique_list,
            "total_attestations": total_attestations,
        }

        # Create an alert for the first entity in the clique
        # (representative alert for the whole group)
        first_entity = min(clique)
        alert = await _create_anomaly_alert(
            db,
            entity_id=first_entity,
            alert_type="attestation_cluster",
            z_score=0.0,
            severity="high",
            details=details,
        )
        alerts.append(alert)

        if auto_flag:
            for eid in clique:
                await _auto_flag_entity(
                    db, eid,
                    f"Collusion: member of attestation clique (size={len(clique)})",
                )

    return alerts


def _find_cliques_bk(
    adjacency: dict[_uuid.UUID, set[_uuid.UUID]],
    r: set[_uuid.UUID],
    p: set[_uuid.UUID],
    x: set[_uuid.UUID],
    min_size: int,
    results: list[frozenset[_uuid.UUID]],
    max_results: int = 100,
) -> None:
    """Bron-Kerbosch algorithm for finding maximal cliques.

    Args:
        adjacency: adjacency map (node -> set of neighbors)
        r: current clique being built
        p: candidates that could extend the clique
        x: already-processed nodes (for maximality)
        min_size: minimum clique size to report
        results: output list of cliques found
        max_results: safety cap to avoid runaway computation
    """
    if len(results) >= max_results:
        return

    if not p and not x:
        # r is a maximal clique
        if len(r) >= min_size:
            results.append(frozenset(r))
        return

    # Pick pivot vertex from p | x with most connections to p
    pivot_candidates = p | x
    pivot = max(pivot_candidates, key=lambda v: len(adjacency[v] & p))

    for v in list(p - adjacency[pivot]):
        if len(results) >= max_results:
            return
        neighbors = adjacency[v]
        _find_cliques_bk(
            adjacency,
            r | {v},
            p & neighbors,
            x & neighbors,
            min_size,
            results,
            max_results,
        )
        p = p - {v}
        x = x | {v}


# ---------------------------------------------------------------------------
# Detector 3 — Voting rings
# ---------------------------------------------------------------------------


async def detect_voting_ring(
    db: AsyncSession,
    *,
    window_days: int = 30,
    overlap_threshold: float = 0.8,
    min_votes: int = 5,
    auto_flag: bool = False,
) -> list[AnomalyAlert]:
    """Detect entities that consistently upvote each other's posts.

    For each pair (A, B): computes what percentage of A's upvotes went to B's
    posts, and vice versa. If both percentages exceed overlap_threshold AND
    each has >= min_votes, the pair is flagged.

    Severity: "medium" for pairs, "high" if 3+ entities form a ring.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)

    # Get all upvotes within the window, joined with post author
    result = await db.execute(
        select(
            Vote.entity_id,        # voter
            Post.author_entity_id,  # post author
            func.count(Vote.id).label("vote_count"),
        )
        .join(Post, Vote.post_id == Post.id)
        .where(
            Vote.direction == VoteDirection.UP,
            Vote.created_at >= cutoff,
            # Exclude self-votes
            Vote.entity_id != Post.author_entity_id,
        )
        .group_by(Vote.entity_id, Post.author_entity_id)
    )
    vote_rows = result.all()

    if not vote_rows:
        return []

    # Build vote matrix: voter -> {author -> count}
    vote_matrix: dict[_uuid.UUID, dict[_uuid.UUID, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    # Total upvotes per voter
    total_votes: dict[_uuid.UUID, int] = defaultdict(int)

    for voter_id, author_id, count in vote_rows:
        vote_matrix[voter_id][author_id] = count
        total_votes[voter_id] += count

    # Find pairs where mutual voting overlap exceeds threshold
    ring_pairs: list[tuple[_uuid.UUID, _uuid.UUID, float, float, int, int]] = []
    checked: set[frozenset[_uuid.UUID]] = set()

    for voter_a, targets_a in vote_matrix.items():
        for voter_b in targets_a:
            pair_key = frozenset({voter_a, voter_b})
            if pair_key in checked:
                continue
            checked.add(pair_key)

            # How many of A's upvotes went to B's posts?
            a_to_b = vote_matrix[voter_a].get(voter_b, 0)
            # How many of B's upvotes went to A's posts?
            b_to_a = vote_matrix.get(voter_b, {}).get(voter_a, 0)

            if a_to_b < min_votes or b_to_a < min_votes:
                continue

            total_a = total_votes[voter_a]
            total_b = total_votes.get(voter_b, 0)

            if total_a == 0 or total_b == 0:
                continue

            overlap_a = a_to_b / total_a  # % of A's votes that went to B
            overlap_b = b_to_a / total_b  # % of B's votes that went to A

            if overlap_a >= overlap_threshold and overlap_b >= overlap_threshold:
                ring_pairs.append((
                    voter_a, voter_b,
                    overlap_a, overlap_b,
                    a_to_b, b_to_a,
                ))

    if not ring_pairs:
        return []

    # Build a graph from ring pairs to detect larger rings (3+ entities)
    ring_adjacency: dict[_uuid.UUID, set[_uuid.UUID]] = defaultdict(set)
    for entity_a, entity_b, _, _, _, _ in ring_pairs:
        ring_adjacency[entity_a].add(entity_b)
        ring_adjacency[entity_b].add(entity_a)

    # Find connected components in the ring graph
    ring_visited: set[_uuid.UUID] = set()
    components: list[set[_uuid.UUID]] = []
    for node in ring_adjacency:
        if node in ring_visited:
            continue
        component: set[_uuid.UUID] = set()
        queue = [node]
        while queue:
            curr = queue.pop()
            if curr in component:
                continue
            component.add(curr)
            for neighbor in ring_adjacency[curr]:
                if neighbor not in component:
                    queue.append(neighbor)
        ring_visited.update(component)
        components.append(component)

    # Determine severity: 3+ entities in a connected component = "high"
    large_ring_entities: set[_uuid.UUID] = set()
    for comp in components:
        if len(comp) >= 3:
            large_ring_entities.update(comp)

    alerts: list[AnomalyAlert] = []
    for entity_a, entity_b, overlap_a, overlap_b, count_a, count_b in ring_pairs:
        severity = "high" if (
            entity_a in large_ring_entities or entity_b in large_ring_entities
        ) else "medium"

        details: dict[str, Any] = {
            "entity_a": str(entity_a),
            "entity_b": str(entity_b),
            "overlap_a_to_b": round(overlap_a, 4),
            "overlap_b_to_a": round(overlap_b, 4),
            "votes_a_to_b": count_a,
            "votes_b_to_a": count_b,
            "window_days": window_days,
            "overlap_threshold": overlap_threshold,
        }

        alert = await _create_anomaly_alert(
            db,
            entity_id=entity_a,
            alert_type="voting_ring",
            z_score=0.0,
            severity=severity,
            details=details,
        )
        alerts.append(alert)

        if auto_flag:
            await _auto_flag_entity(
                db, entity_a,
                f"Collusion: voting ring with entity {entity_b} "
                f"(overlap={overlap_a:.0%}/{overlap_b:.0%})",
            )
            await _auto_flag_entity(
                db, entity_b,
                f"Collusion: voting ring with entity {entity_a} "
                f"(overlap={overlap_b:.0%}/{overlap_a:.0%})",
            )

    return alerts


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------


async def run_all_collusion_detectors(
    db: AsyncSession,
    *,
    auto_flag: bool = False,
) -> list[AnomalyAlert]:
    """Run all collusion detectors and return combined alerts."""
    alerts: list[AnomalyAlert] = []
    alerts.extend(await detect_mutual_attestation(db, auto_flag=auto_flag))
    alerts.extend(await detect_attestation_clique(db, auto_flag=auto_flag))
    alerts.extend(await detect_voting_ring(db, auto_flag=auto_flag))
    return alerts
