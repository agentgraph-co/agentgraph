from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import APIKey, Entity

logger = logging.getLogger(__name__)


async def expire_provisional_agents(db: AsyncSession) -> dict:
    """Find and deactivate all expired provisional agents.

    An agent is expired when ``is_provisional`` is True and
    ``provisional_expires_at`` is in the past.

    For each expired agent:
    - Sets ``is_active = False``
    - Revokes all associated API keys (``is_active = False``,
      ``revoked_at`` set to now)

    Returns a summary dict:
        expired_count: int   -- number of agents deactivated
        keys_revoked: int    -- number of API keys revoked
        duration_seconds: float
    """
    start = time.monotonic()
    now = datetime.now(timezone.utc)

    # Find all expired provisional entities
    result = await db.execute(
        select(Entity).where(
            Entity.is_provisional.is_(True),
            Entity.provisional_expires_at < now,
            Entity.is_active.is_(True),
        )
    )
    expired_entities = result.scalars().all()

    expired_count = 0
    keys_revoked = 0

    for entity in expired_entities:
        # Deactivate the entity
        entity.is_active = False

        # Revoke all active API keys for this entity
        key_result = await db.execute(
            update(APIKey)
            .where(
                APIKey.entity_id == entity.id,
                APIKey.is_active.is_(True),
            )
            .values(is_active=False, revoked_at=now)
            .returning(APIKey.id)
        )
        revoked_ids = key_result.fetchall()
        keys_revoked += len(revoked_ids)
        expired_count += 1

        logger.info(
            "Expired provisional agent %s (%s), revoked %d API keys",
            entity.id, entity.display_name, len(revoked_ids),
        )

    await db.flush()

    duration = time.monotonic() - start
    summary = {
        "expired_count": expired_count,
        "keys_revoked": keys_revoked,
        "duration_seconds": round(duration, 3),
    }

    logger.info(
        "Provisional expiration complete: %d agents expired, "
        "%d keys revoked, took %.3fs",
        expired_count, keys_revoked, duration,
    )

    return summary
