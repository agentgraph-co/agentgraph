"""Evolution fork tree computation.

Builds a tree of entities connected by evolution forks —
showing how agents were forked from one another and their version history.
"""
from __future__ import annotations

import uuid as _uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, EvolutionRecord


async def compute_lineage_tree(
    db: AsyncSession,
    entity_id: _uuid.UUID,
    max_depth: int = 5,
) -> dict[str, Any]:
    """Build the evolution fork tree rooted at *entity_id*.

    Returns::

        {
            "entity_id": str,
            "entity_name": str,
            "version": str | None,
            "children": [
                {
                    "entity_id": str,
                    "entity_name": str,
                    "version": str | None,
                    "children": [...]
                },
                ...
            ]
        }

    ``max_depth`` limits recursion (1-5).
    """
    max_depth = max(1, min(5, max_depth))

    entity = await db.get(Entity, entity_id)
    if entity is None:
        return {
            "entity_id": str(entity_id),
            "entity_name": "Unknown",
            "version": None,
            "children": [],
        }

    # Get latest version for root entity
    latest_record = await db.execute(
        select(EvolutionRecord.version)
        .where(EvolutionRecord.entity_id == entity_id)
        .order_by(EvolutionRecord.created_at.desc())
        .limit(1)
    )
    latest_version = latest_record.scalar_one_or_none()

    visited: set[_uuid.UUID] = {entity_id}

    async def _build_children(
        parent_entity_id: _uuid.UUID,
        depth: int,
    ) -> list[dict[str, Any]]:
        """Find entities forked from *parent_entity_id* and recurse."""
        if depth <= 0:
            return []

        # Find all evolution records where forked_from_entity_id == parent
        fork_records = await db.execute(
            select(EvolutionRecord.entity_id, EvolutionRecord.version)
            .where(
                EvolutionRecord.forked_from_entity_id == parent_entity_id,
            )
            .distinct(EvolutionRecord.entity_id)
        )
        fork_rows = fork_records.all()

        children: list[dict[str, Any]] = []
        for child_entity_id, child_version in fork_rows:
            if child_entity_id in visited:
                continue
            visited.add(child_entity_id)

            child_entity = await db.get(Entity, child_entity_id)
            child_name = child_entity.display_name if child_entity else "Unknown"

            # Get latest version for this child
            child_latest = await db.execute(
                select(EvolutionRecord.version)
                .where(EvolutionRecord.entity_id == child_entity_id)
                .order_by(EvolutionRecord.created_at.desc())
                .limit(1)
            )
            child_latest_version = (
                child_latest.scalar_one_or_none() or child_version
            )

            sub_children = await _build_children(child_entity_id, depth - 1)

            children.append({
                "entity_id": str(child_entity_id),
                "entity_name": child_name,
                "version": child_latest_version,
                "children": sub_children,
            })

        return children

    children = await _build_children(entity_id, max_depth)

    return {
        "entity_id": str(entity_id),
        "entity_name": entity.display_name,
        "version": latest_version,
        "children": children,
    }
