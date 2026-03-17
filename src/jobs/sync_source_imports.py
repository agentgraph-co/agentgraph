"""Background job to refresh community signals for source-imported bots."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity

logger = logging.getLogger(__name__)

MAX_PER_RUN = 20
STALE_AFTER_HOURS = 24


async def sync_stale_source_imports(session: AsyncSession) -> dict:
    """Re-fetch community signals for entities with stale source data.

    Returns dict like {"synced": 3, "failed": 1, "total": 4}.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_AFTER_HOURS)

    stmt = (
        select(Entity)
        .where(Entity.source_url.isnot(None))
        .where(
            (Entity.source_verified_at.is_(None))
            | (Entity.source_verified_at < cutoff)
        )
        .limit(MAX_PER_RUN)
    )
    result = await session.execute(stmt)
    entities = result.scalars().all()

    synced = 0
    failed = 0

    for entity in entities:
        try:
            from src.source_import.resolver import resolve_source

            fresh = await resolve_source(entity.source_url)

            # Update community signals in onboarding_data
            onboarding = dict(entity.onboarding_data or {})
            import_source = dict(onboarding.get("import_source", {}))
            import_source["community_signals"] = fresh.community_signals
            import_source["fetched_at"] = datetime.now(timezone.utc).isoformat()
            onboarding["import_source"] = import_source
            entity.onboarding_data = onboarding

            entity.source_verified_at = datetime.now(timezone.utc)
            synced += 1
        except Exception:
            logger.warning(
                "Source sync failed for entity %s (%s), marking stale",
                entity.id,
                entity.source_url,
                exc_info=True,
            )
            entity.source_verified_at = None
            failed += 1

    return {"synced": synced, "failed": failed, "total": len(entities)}
