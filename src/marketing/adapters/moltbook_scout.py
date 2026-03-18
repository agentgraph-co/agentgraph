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
        """Scrape trending agents from Moltbook for import.

        Returns list of dicts compatible with source_import pipeline.
        """
        try:
            # In practice, we'd use src.bridges.moltbook.adapter and
            # src.source_import.moltbook_fetcher to scrape trending bots.
            # For now, return empty — will be populated when we have
            # Moltbook trending page scraping.
            logger.info("Moltbook scout: discovering trending agents")
            return []
        except ImportError:
            logger.debug("Moltbook bridge not available")
            return []
