"""Unified pairwise interaction history recording.

Provides a single helper to record any entity-to-entity interaction
into the interaction_events table. Called from various routers after
successful actions (follow, unfollow, vote, reply, DM, etc.).
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import InteractionEvent

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
