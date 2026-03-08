"""Unified pairwise interaction history recording.

Provides a single helper to record any entity-to-entity interaction
into the interaction_events table. Called from various routers after
successful actions (follow, unfollow, vote, reply, DM, etc.).
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, InteractionEvent

logger = logging.getLogger(__name__)

VALID_INTERACTION_TYPES = frozenset({
    "follow",
    "unfollow",
    "attestation",
    "endorsement",
    "delegation",
    "recurring_delegation",
    "service_contract",
    "vote",
    "reply",
    "dm",
    "review",
    "block",
})


async def _enrich_framework_pair(
    db: AsyncSession,
    entity_a_id: uuid.UUID,
    entity_b_id: uuid.UUID,
    context: dict | None,
) -> dict:
    """Task #213: Enrich interaction context with framework pair info.

    When two agents from different frameworks interact, logs the framework pair
    (e.g. 'openclaw' <-> 'langchain') in the interaction context.
    """
    enriched = dict(context) if context else {}

    # Fetch framework_source for both entities in a single query
    result = await db.execute(
        select(Entity.id, Entity.framework_source).where(
            Entity.id.in_([entity_a_id, entity_b_id]),
        )
    )
    fw_map = {row[0]: row[1] for row in result.all()}

    fw_a = fw_map.get(entity_a_id)
    fw_b = fw_map.get(entity_b_id)

    if fw_a or fw_b:
        enriched["initiator_framework"] = fw_a
        enriched["target_framework"] = fw_b
        enriched["is_cross_framework"] = (
            fw_a is not None and fw_b is not None and fw_a != fw_b
        )

    return enriched


async def record_interaction(
    db: AsyncSession,
    entity_a_id: uuid.UUID,
    entity_b_id: uuid.UUID,
    interaction_type: str,
    context: dict | None = None,
) -> InteractionEvent:
    """Record a pairwise interaction event.

    Parameters
    ----------
    db : AsyncSession
        Active database session (caller manages commit).
    entity_a_id : UUID
        The entity that initiated the interaction.
    entity_b_id : UUID
        The entity that received / was the target of the interaction.
    interaction_type : str
        One of the VALID_INTERACTION_TYPES values.
    context : dict, optional
        Additional metadata (e.g. reference_id, post_id, etc.).

    Returns
    -------
    InteractionEvent
        The newly created interaction event record.
    """
    if interaction_type not in VALID_INTERACTION_TYPES:
        logger.warning(
            "Unknown interaction_type %r — recording anyway", interaction_type,
        )

    # Task #213: Enrich with framework pair tracking
    try:
        context = await _enrich_framework_pair(db, entity_a_id, entity_b_id, context)
    except Exception:
        logger.warning("Best-effort framework pair enrichment failed", exc_info=True)

    event = InteractionEvent(
        id=uuid.uuid4(),
        entity_a_id=entity_a_id,
        entity_b_id=entity_b_id,
        interaction_type=interaction_type,
        context=context,
    )
    db.add(event)
    await db.flush()
    return event
