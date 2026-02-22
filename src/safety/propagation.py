"""Propagation freeze and quarantine checks.

Provides safety controls for freezing network propagation and
quarantining individual entities when security threats are detected.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, TrustScore

logger = logging.getLogger(__name__)

# Redis key for global propagation freeze
_FREEZE_KEY = "safety:propagation_freeze"


async def is_propagation_frozen() -> bool:
    """Check whether a global propagation freeze is active.

    Returns False on Redis failure (graceful degradation).
    """
    try:
        from src.redis_client import get_redis

        r = get_redis()
        val = await r.get(_FREEZE_KEY)
        return val is not None
    except Exception:
        logger.warning("Redis unavailable for freeze check, defaulting to unfrozen")
        return False


async def set_propagation_freeze(active: bool) -> None:
    """Activate or deactivate the global propagation freeze.

    When active, sets a Redis key. When deactivated, removes it.
    """
    try:
        from src.redis_client import get_redis

        r = get_redis()
        if active:
            await r.set(_FREEZE_KEY, "1")
        else:
            await r.delete(_FREEZE_KEY)
    except Exception:
        logger.error("Failed to set propagation freeze in Redis", exc_info=True)
        raise


async def get_freeze_timestamp() -> str | None:
    """Get the freeze value if frozen, else None."""
    try:
        from src.redis_client import get_redis

        r = get_redis()
        val = await r.get(_FREEZE_KEY)
        return val
    except Exception:
        return None


async def is_entity_quarantined(db: AsyncSession, entity_id: uuid.UUID) -> bool:
    """Check whether an entity is currently quarantined."""
    entity = await db.get(Entity, entity_id)
    if entity is None:
        return False
    return bool(getattr(entity, "is_quarantined", False))


async def quarantine_entity(
    db: AsyncSession,
    entity_id: uuid.UUID,
    reason: str,
) -> None:
    """Quarantine an entity and create an audit log entry."""
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise ValueError(f"Entity {entity_id} not found")

    entity.is_quarantined = True
    await db.flush()

    from src.audit import log_action

    await log_action(
        db,
        action="safety.quarantine",
        entity_id=entity_id,
        resource_type="entity",
        resource_id=entity_id,
        details={"reason": reason},
    )


async def release_quarantine(
    db: AsyncSession,
    entity_id: uuid.UUID,
    reason: str,
) -> None:
    """Release an entity from quarantine and create an audit log entry."""
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise ValueError(f"Entity {entity_id} not found")

    entity.is_quarantined = False
    await db.flush()

    from src.audit import log_action

    await log_action(
        db,
        action="safety.release_quarantine",
        entity_id=entity_id,
        resource_type="entity",
        resource_id=entity_id,
        details={"reason": reason},
    )


async def check_min_trust_for_publish(
    db: AsyncSession,
    entity_id: uuid.UUID,
    min_trust: float = 0.3,
) -> bool:
    """Check whether an entity's trust score meets the minimum threshold.

    Returns True if the score meets or exceeds the minimum,
    or if no trust score exists (new entities get benefit of doubt).
    """
    result = await db.execute(
        select(TrustScore.score).where(TrustScore.entity_id == entity_id)
    )
    score = result.scalar_one_or_none()
    if score is None:
        # No trust score yet - allow by default
        return True
    return score >= min_trust
