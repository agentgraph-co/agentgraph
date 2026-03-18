"""Telegram adapter — channel posting via Bot API."""
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

_TIMEOUT = 15.0


def _api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{marketing_settings.telegram_bot_token}/{method}"


class TelegramAdapter(AbstractPlatformAdapter):
    platform_name = "telegram"
    max_content_length = 4096
    supports_replies = True
    supports_monitoring = False  # Would need polling/webhook
    rate_limit_posts_per_hour = 20

    async def is_configured(self) -> bool:
        return bool(
            marketing_settings.telegram_bot_token
            and marketing_settings.telegram_channel_id
        )

    async def post(self, content: str, metadata: dict | None = None) -> ExternalPostResult:
        chat_id = (metadata or {}).get(
            "chat_id", marketing_settings.telegram_channel_id,
        )

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    _api_url("sendMessage"),
                    json={
                        "chat_id": chat_id,
                        "text": self.truncate(content),
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": False,
                    },
                )

            if resp.status_code == 429:
                return ExternalPostResult(
                    success=False, error="Rate limited", rate_limited=True,
                )

            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                return ExternalPostResult(
                    success=False, error=data.get("description", "Unknown error"),
                )

            msg_id = str(data.get("result", {}).get("message_id", ""))
            return ExternalPostResult(success=True, external_id=msg_id)
        except Exception as exc:
            logger.exception("Telegram post failed")
            return ExternalPostResult(success=False, error=str(exc))

    async def reply(
        self, parent_id: str, content: str, metadata: dict | None = None,
    ) -> ExternalPostResult:
        chat_id = (metadata or {}).get(
            "chat_id", marketing_settings.telegram_channel_id,
        )
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    _api_url("sendMessage"),
                    json={
                        "chat_id": chat_id,
                        "text": self.truncate(content),
                        "reply_to_message_id": int(parent_id),
                        "parse_mode": "Markdown",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            msg_id = str(data.get("result", {}).get("message_id", ""))
            return ExternalPostResult(success=True, external_id=msg_id)
        except Exception as exc:
            return ExternalPostResult(success=False, error=str(exc))

    async def fetch_mentions(self, since: datetime | None = None) -> list[Mention]:
        return []

    async def fetch_metrics(self, post_external_id: str) -> EngagementMetrics:
        return EngagementMetrics()  # Telegram doesn't expose per-message metrics via Bot API

    async def health_check(self) -> bool:
        if not await self.is_configured():
            return False
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_api_url("getMe"))
                return resp.status_code == 200 and resp.json().get("ok", False)
        except Exception:
            return False
