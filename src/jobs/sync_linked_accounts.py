"""Periodic sync for stale linked accounts."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.external_reputation import sync_provider_data
from src.models import LinkedAccount

logger = logging.getLogger(__name__)

# Re-sync accounts that haven't been synced in 6+ hours
SYNC_STALENESS_HOURS = 6


async def sync_stale_linked_accounts(db: AsyncSession) -> dict:
    """Sync linked accounts that haven't been updated recently."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=SYNC_STALENESS_HOURS)

    result = await db.execute(
        select(LinkedAccount).where(
            (LinkedAccount.last_synced_at < cutoff)
            | (LinkedAccount.last_synced_at.is_(None))
        )
    )
    accounts = result.scalars().all()

    synced = 0
    errors = 0
    entity_ids = set()

    for acct in accounts:
        try:
            await sync_provider_data(db, acct)
            entity_ids.add(acct.entity_id)
            synced += 1
        except Exception:
            logger.exception(
                "Failed to sync linked account %s (%s)",
                acct.id, acct.provider,
            )
            errors += 1

    # Recompute trust scores for affected entities
    if entity_ids:
        from src.trust.score import compute_trust_score

        for eid in entity_ids:
            try:
                await compute_trust_score(db, eid)
            except Exception:
                logger.exception("Trust recompute failed for %s", eid)

    return {"synced": synced, "errors": errors, "entities_updated": len(entity_ids)}
