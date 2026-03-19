"""Discord adapter using httpx (REST API, no gateway connection).

Posts to configured channels in AI/ML Discord servers.
Uses Discord bot token for authentication.
"""
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

_API_BASE = "https://discord.com/api/v10"
_TIMEOUT = 15.0


class DiscordAdapter(AbstractPlatformAdapter):
    platform_name = "discord"
    max_content_length = 2000
    supports_replies = True
    supports_monitoring = False  # Would need gateway for real-time
    rate_limit_posts_per_hour = 20
    rate_limit_replies_per_hour = 40

    async def is_configured(self) -> bool:
        return bool(marketing_settings.discord_bot_token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bot {marketing_settings.discord_bot_token}"}

    async def post(self, content: str, metadata: dict | None = None) -> ExternalPostResult:
        channel_id = (
            (metadata or {}).get("channel_id")
            or marketing_settings.discord_default_channel_id
        )
        if not channel_id:
            return ExternalPostResult(success=False, error="No channel_id in metadata or config")

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{_API_BASE}/channels/{channel_id}/messages",
                    json={"content": self.truncate(content)},
                    headers=self._headers(),
                )

            if resp.status_code == 429:
                return ExternalPostResult(
                    success=False, error="Rate limited", rate_limited=True,
                )

            resp.raise_for_status()
            data = resp.json()
            return ExternalPostResult(
                success=True, external_id=data.get("id"),
            )
        except Exception as exc:
            logger.exception("Discord post failed")
            return ExternalPostResult(success=False, error=str(exc))

    async def reply(
        self, parent_id: str, content: str, metadata: dict | None = None,
    ) -> ExternalPostResult:
        channel_id = (metadata or {}).get("channel_id")
        if not channel_id:
            return ExternalPostResult(success=False, error="No channel_id")

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{_API_BASE}/channels/{channel_id}/messages",
                    json={
                        "content": self.truncate(content),
                        "message_reference": {"message_id": parent_id},
                    },
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
            return ExternalPostResult(success=True, external_id=data.get("id"))
        except Exception as exc:
            return ExternalPostResult(success=False, error=str(exc))

    async def fetch_mentions(self, since: datetime | None = None) -> list[Mention]:
        return []  # Requires gateway connection

    async def fetch_metrics(self, post_external_id: str) -> EngagementMetrics:
        return EngagementMetrics()  # Discord doesn't expose message metrics

    async def health_check(self) -> bool:
        if not await self.is_configured():
            return False
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"{_API_BASE}/users/@me", headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False
