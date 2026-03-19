"""LinkedIn adapter — company page posting via Posts API (REST)."""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from src.marketing.adapters.base import (
    AbstractPlatformAdapter,
    EngagementMetrics,
    ExternalPostResult,
    Mention,
)
from src.marketing.config import marketing_settings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.linkedin.com"
_TIMEOUT = 15.0


class LinkedInAdapter(AbstractPlatformAdapter):
    platform_name = "linkedin"
    max_content_length = 3000
    supports_replies = False
    supports_monitoring = False
    rate_limit_posts_per_hour = 4

    async def is_configured(self) -> bool:
        return bool(
            marketing_settings.linkedin_access_token
            and marketing_settings.linkedin_org_id
        )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {marketing_settings.linkedin_access_token}",
            "LinkedIn-Version": "202401",
            "Content-Type": "application/json",
        }

    async def post(self, content: str, metadata: dict | None = None) -> ExternalPostResult:
        org_urn = f"urn:li:organization:{marketing_settings.linkedin_org_id}"

        body = {
            "author": org_urn,
            "commentary": self.truncate(content),
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{_API_BASE}/rest/posts", json=body, headers=self._headers(),
                )

            if resp.status_code == 429:
                return ExternalPostResult(
                    success=False, error="Rate limited", rate_limited=True,
                )

            resp.raise_for_status()
            post_id = resp.headers.get("x-restli-id", "")
            url = None
            if post_id:
                url = f"https://www.linkedin.com/feed/update/{post_id}"
            return ExternalPostResult(success=True, external_id=post_id, url=url)
        except Exception as exc:
            logger.exception("LinkedIn post failed")
            return ExternalPostResult(success=False, error=str(exc))

    async def reply(
        self, parent_id: str, content: str, metadata: dict | None = None,
    ) -> ExternalPostResult:
        return ExternalPostResult(success=False, error="LinkedIn replies not supported")

    async def fetch_mentions(self, since: datetime | None = None) -> list[Mention]:
        return []

    async def fetch_metrics(self, post_external_id: str) -> EngagementMetrics:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"{_API_BASE}/rest/socialActions/{post_external_id}",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()

            return EngagementMetrics(
                likes=data.get("likesSummary", {}).get("totalLikes", 0),
                comments=data.get("commentsSummary", {}).get("totalFirstLevelComments", 0),
            )
        except Exception:
            return EngagementMetrics()

    async def health_check(self) -> bool:
        if not await self.is_configured():
            return False
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"{_API_BASE}/rest/me", headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False
