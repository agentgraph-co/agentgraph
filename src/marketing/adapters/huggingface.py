"""HuggingFace Discussions adapter — comment on trending model pages."""
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

_API_BASE = "https://huggingface.co/api"
_TIMEOUT = 15.0


class HuggingFaceAdapter(AbstractPlatformAdapter):
    platform_name = "huggingface"
    max_content_length = 5000
    supports_replies = True
    supports_monitoring = False
    rate_limit_posts_per_hour = 5

    async def is_configured(self) -> bool:
        return bool(marketing_settings.huggingface_token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {marketing_settings.huggingface_token}"}

    async def post(self, content: str, metadata: dict | None = None) -> ExternalPostResult:
        """Create a discussion on a model/repo page."""
        meta = metadata or {}
        repo_id = meta.get("repo_id")  # e.g. "meta-llama/Llama-3.1-8B"
        title = meta.get("title", "Thoughts on agent identity")

        if not repo_id:
            return ExternalPostResult(success=False, error="No repo_id in metadata")

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{_API_BASE}/models/{repo_id}/discussions",
                    json={"title": title, "description": content},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()

            disc_num = data.get("num", "")
            return ExternalPostResult(
                success=True,
                external_id=str(disc_num),
                url=f"https://huggingface.co/{repo_id}/discussions/{disc_num}",
            )
        except Exception as exc:
            logger.exception("HuggingFace post failed")
            return ExternalPostResult(success=False, error=str(exc))

    async def reply(
        self, parent_id: str, content: str, metadata: dict | None = None,
    ) -> ExternalPostResult:
        meta = metadata or {}
        repo_id = meta.get("repo_id")
        if not repo_id:
            return ExternalPostResult(success=False, error="No repo_id")

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{_API_BASE}/models/{repo_id}/discussions/{parent_id}/comment",
                    json={"comment": content},
                    headers=self._headers(),
                )
                resp.raise_for_status()
            return ExternalPostResult(success=True, external_id=parent_id)
        except Exception as exc:
            return ExternalPostResult(success=False, error=str(exc))

    async def fetch_mentions(self, since: datetime | None = None) -> list[Mention]:
        return []

    async def fetch_metrics(self, post_external_id: str) -> EngagementMetrics:
        return EngagementMetrics()

    async def health_check(self) -> bool:
        if not await self.is_configured():
            return False
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"{_API_BASE}/whoami-v2", headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False
