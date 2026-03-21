"""Moltbook scout — read-only adapter that scrapes trending agents.

Reuses the existing Moltbook bridge for data fetching.
Does NOT post to Moltbook (Meta-owned, no write API).
Instead, discovers agents and feeds them to other adapters.
"""
from __future__ import annotations

import logging
from datetime import datetime

from src.marketing.adapters.base import (
    AbstractPlatformAdapter,
    EngagementMetrics,
    ExternalPostResult,
    Mention,
)

logger = logging.getLogger(__name__)


class MoltbookScoutAdapter(AbstractPlatformAdapter):
    platform_name = "moltbook_scout"
    max_content_length = 0  # Read-only
    supports_replies = False
    supports_monitoring = True
    requires_human_approval = False
    rate_limit_posts_per_hour = 0  # No posting

    async def is_configured(self) -> bool:
        # Always available — uses public scraping
        return True

    async def post(self, content: str, metadata: dict | None = None) -> ExternalPostResult:
        return ExternalPostResult(success=False, error="Moltbook scout is read-only")

    async def reply(
        self, parent_id: str, content: str, metadata: dict | None = None,
    ) -> ExternalPostResult:
        return ExternalPostResult(success=False, error="Moltbook scout is read-only")

    async def fetch_mentions(self, since: datetime | None = None) -> list[Mention]:
        return []

    async def fetch_metrics(self, post_external_id: str) -> EngagementMetrics:
        return EngagementMetrics()

    async def health_check(self) -> bool:
        return True

    async def discover_trending_agents(self, limit: int = 20) -> list[dict]:
        """Return seed profiles not yet imported.

        Returns list of dicts compatible with the batch import pipeline.
        """
        import random

        from sqlalchemy import select

        from src.bridges.moltbook.seed_profiles import MOLTBOOK_SEED_PROFILES
        from src.database import async_session
        from src.models import Entity

        logger.info("Moltbook scout: discovering trending agents")

        # Get already-imported moltbook_ids
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(Entity.onboarding_data).where(
                        Entity.framework_source == "moltbook",
                    )
                )
                imported_ids: set[str] = set()
                for data in result.scalars().all():
                    if data and isinstance(data, dict):
                        src = data.get("import_source", {})
                        mb_id = src.get("moltbook_id") or data.get("moltbook_id")
                        if mb_id:
                            imported_ids.add(mb_id)
        except Exception:
            logger.exception("Failed to query existing Moltbook imports")
            imported_ids = set()

        available = [
            p for p in MOLTBOOK_SEED_PROFILES
            if p["moltbook_id"] not in imported_ids
        ]
        random.shuffle(available)
        return available[:limit]
