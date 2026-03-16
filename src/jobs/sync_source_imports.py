"""Periodic sync of source import data (community signals, verification)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity

logger = logging.getLogger(__name__)


async def sync_stale_source_imports(session: AsyncSession) -> dict:
    """Re-fetch community signals for entities with source URLs.

    Targets entities where source_verified_at is older than 24 hours.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    stmt = select(Entity).where(
        and_(
            Entity.source_url.isnot(None),
            Entity.is_active.is_(True),
            (Entity.source_verified_at.is_(None)) | (Entity.source_verified_at < cutoff),
        )
    ).limit(50)  # Process in batches

    result = await session.execute(stmt)
    entities = result.scalars().all()

    synced = 0
    failed = 0

    for entity in entities:
        try:
            from src.source_import.resolver import resolve_source

            import_result = await resolve_source(entity.source_url)

            # Update community signals in onboarding_data
            onboarding = entity.onboarding_data or {}
            import_source = onboarding.get("import_source", {})
            import_source["community_signals"] = import_result.community_signals
            import_source["fetched_at"] = datetime.now(timezone.utc).isoformat()
            onboarding["import_source"] = import_source
            entity.onboarding_data = onboarding

            entity.source_verified_at = datetime.now(timezone.utc)
            synced += 1

        except ValueError:
            # Source URL is no longer valid (404, etc.)
            entity.source_verified_at = None
            failed += 1
            logger.warning(
                "Source URL no longer valid for entity %s: %s",
                entity.id, entity.source_url,
            )
        except Exception:
            failed += 1
            logger.exception(
                "Failed to sync source import for entity %s", entity.id,
            )

    await session.flush()

    return {"synced": synced, "failed": failed, "total_checked": len(entities)}
