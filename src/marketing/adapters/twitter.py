"""Twitter/X v2 API adapter using httpx.

Supports Free tier (write-only, 1500 tweets/mo) and Basic tier ($100/mo).
Uses OAuth 1.0a for tweet creation (user context).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
import urllib.parse
import uuid
from base64 import b64encode
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

_API_BASE = "https://api.twitter.com/2"
_TIMEOUT = 15.0


class TwitterAdapter(AbstractPlatformAdapter):
    platform_name = "twitter"
    max_content_length = 280
    supports_replies = True
    supports_monitoring = True  # Requires Basic tier ($100/mo)
    rate_limit_posts_per_hour = 100
    rate_limit_replies_per_hour = 100

    async def is_configured(self) -> bool:
        return bool(
            marketing_settings.twitter_consumer_key
            and marketing_settings.twitter_consumer_key_secret
            and marketing_settings.twitter_access_token
            and marketing_settings.twitter_access_token_secret
        )

    def _oauth1_header(self, method: str, url: str, body: dict | None = None) -> str:
        """Generate OAuth 1.0a Authorization header."""
        oauth_params = {
            "oauth_consumer_key": marketing_settings.twitter_consumer_key or "",
            "oauth_nonce": uuid.uuid4().hex,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": marketing_settings.twitter_access_token or "",
            "oauth_version": "1.0",
        }

        # Combine params for signature base
        all_params = {**oauth_params}
        if body:
            # For JSON body, don't include in signature (Twitter v2 uses JSON)
            pass

        param_string = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted(all_params.items())
        )
        base_string = (
            f"{method.upper()}&"
            f"{urllib.parse.quote(url, safe='')}&"
            f"{urllib.parse.quote(param_string, safe='')}"
        )

        signing_key = (
            f"{urllib.parse.quote(marketing_settings.twitter_consumer_key_secret or '', safe='')}&"
            f"{urllib.parse.quote(marketing_settings.twitter_access_token_secret or '', safe='')}"
        )

        signature = b64encode(
            hmac.new(
                signing_key.encode(), base_string.encode(), hashlib.sha1,
            ).digest()
        ).decode()

        oauth_params["oauth_signature"] = signature

        header = "OAuth " + ", ".join(
            f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(str(v), safe="")}"'
            for k, v in sorted(oauth_params.items())
        )
        return header

    async def post(self, content: str, metadata: dict | None = None) -> ExternalPostResult:
        url = f"{_API_BASE}/tweets"
        body: dict = {"text": self.truncate(content)}

        # If replying in a thread
        if metadata and metadata.get("reply_to"):
            body["reply"] = {"in_reply_to_tweet_id": metadata["reply_to"]}

        auth_header = self._oauth1_header("POST", url, body)

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    url, json=body,
                    headers={
                        "Authorization": auth_header,
                        "Content-Type": "application/json",
                    },
                )

            if resp.status_code == 429:
                return ExternalPostResult(
                    success=False, error="Rate limited", rate_limited=True,
                )

            resp.raise_for_status()
            data = resp.json().get("data", {})
            tweet_id = data.get("id")

            return ExternalPostResult(
                success=True,
                external_id=tweet_id,
                url=f"https://x.com/i/status/{tweet_id}" if tweet_id else None,
            )
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Twitter post failed: %s %s",
                exc.response.status_code, exc.response.text,
            )
            return ExternalPostResult(
                success=False,
                error=f"HTTP {exc.response.status_code}: "
                      f"{exc.response.text[:200]}",
            )
        except Exception as exc:
            logger.exception("Twitter post failed")
            return ExternalPostResult(success=False, error=str(exc))

    async def reply(
        self, parent_id: str, content: str, metadata: dict | None = None,
    ) -> ExternalPostResult:
        return await self.post(content, metadata={"reply_to": parent_id, **(metadata or {})})

    async def fetch_mentions(self, since: datetime | None = None) -> list[Mention]:
        """Fetch mentions — requires Bearer token (Basic tier)."""
        if not marketing_settings.twitter_bearer_token:
            return []

        # Would use search/recent endpoint with query "@AgentGraphBot"
        # Skipping for free tier — implement when upgrading
        return []

    async def fetch_metrics(self, post_external_id: str) -> EngagementMetrics:
        """Fetch tweet metrics — requires Basic tier."""
        if not marketing_settings.twitter_bearer_token:
            return EngagementMetrics()

        url = f"{_API_BASE}/tweets/{post_external_id}"
        params = {"tweet.fields": "public_metrics"}

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    url, params=params,
                    headers={"Authorization": f"Bearer {marketing_settings.twitter_bearer_token}"},
                )
                resp.raise_for_status()
                metrics = resp.json().get("data", {}).get("public_metrics", {})

            return EngagementMetrics(
                likes=metrics.get("like_count", 0),
                comments=metrics.get("reply_count", 0),
                shares=metrics.get("retweet_count", 0),
                impressions=metrics.get("impression_count", 0),
            )
        except Exception:
            logger.debug("Failed to fetch Twitter metrics for %s", post_external_id)
            return EngagementMetrics()

    async def health_check(self) -> bool:
        if not await self.is_configured():
            return False
        # Lightweight check — just verify credentials parse
        return True
