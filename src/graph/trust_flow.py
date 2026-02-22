"""Trust propagation chain computation via BFS.

Starting from a target entity, walks outward through TrustAttestations
to show who attests trust and how that trust propagates through the network.
"""
from __future__ import annotations

import uuid as _uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, TrustAttestation, TrustScore


async def compute_trust_flow(
    db: AsyncSession,
    entity_id: _uuid.UUID,
    max_depth: int = 2,
) -> dict[str, Any]:
    """Compute the trust attestation tree rooted at *entity_id*.

    Returns a tree structure::

        {
            "entity_id": str,
            "trust_score": float | None,
            "attestations": [
                {
                    "attester_id": str,
                    "attester_name": str,
                    "attestation_type": str,
                    "weight": float,
                    "children": [ ... ]   # recursive
                },
                ...
            ]
        }

    ``max_depth`` controls how many hops outward from the target are
    followed (1-5, clamped).
    """
    max_depth = max(1, min(5, max_depth))

    # Get root entity trust score
    ts_row = await db.execute(
        select(TrustScore.score).where(TrustScore.entity_id == entity_id)
    )
    root_trust = ts_row.scalar_one_or_none()

    visited: set[_uuid.UUID] = {entity_id}

    async def _build_level(
        target_id: _uuid.UUID,
        depth: int,
    ) -> list[dict[str, Any]]:
        """Return attestation children for *target_id* up to *depth* levels."""
        if depth <= 0:
            return []

        att_result = await db.execute(
            select(TrustAttestation).where(
                TrustAttestation.target_entity_id == target_id,
            )
        )
        attestations = att_result.scalars().all()

        children: list[dict[str, Any]] = []
        for att in attestations:
            if att.attester_entity_id in visited:
                continue
            visited.add(att.attester_entity_id)

            # Get attester info
            attester = await db.get(Entity, att.attester_entity_id)
            attester_name = attester.display_name if attester else "Unknown"

            # Recurse
            sub_children = await _build_level(att.attester_entity_id, depth - 1)

            children.append({
                "attester_id": str(att.attester_entity_id),
                "attester_name": attester_name,
                "attestation_type": att.attestation_type,
                "weight": att.weight,
                "children": sub_children,
            })

        return children

    attestations = await _build_level(entity_id, max_depth)

    return {
        "entity_id": str(entity_id),
        "trust_score": root_trust,
        "attestations": attestations,
    }
