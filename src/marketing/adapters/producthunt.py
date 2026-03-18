"""Product Hunt adapter — draft queue only (human-in-the-loop).

Product Hunt launches require human submission.
This adapter generates drafts for the launch.
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


class ProductHuntAdapter(AbstractPlatformAdapter):
    platform_name = "producthunt"
    max_content_length = 5000
    supports_replies = False
    supports_monitoring = False
    requires_human_approval = True
    rate_limit_posts_per_hour = 0

    async def is_configured(self) -> bool:
        return True  # Always available for draft generation

    async def post(self, content: str, metadata: dict | None = None) -> ExternalPostResult:
        return ExternalPostResult(
            success=False, error="Product Hunt requires human submission — use draft queue",
        )

    async def reply(
        self, parent_id: str, content: str, metadata: dict | None = None,
    ) -> ExternalPostResult:
        return ExternalPostResult(success=False, error="PH requires human submission")

    async def fetch_mentions(self, since: datetime | None = None) -> list[Mention]:
        return []

    async def fetch_metrics(self, post_external_id: str) -> EngagementMetrics:
        return EngagementMetrics()

    async def health_check(self) -> bool:
        return True
