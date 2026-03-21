"""Keyword monitoring — reactive mode.

Scans configured platforms for keyword matches and generates
reply drafts or auto-replies depending on platform policy.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.marketing.adapters.base import AbstractPlatformAdapter
from src.marketing.content.engine import generate_reactive
from src.marketing.models import MarketingPost
from src.marketing.orchestrator import HUMAN_APPROVAL_PLATFORMS, _save_post

logger = logging.getLogger(__name__)

# Keywords to monitor across all platforms
MONITOR_KEYWORDS = [
    "agent identity",
    "agent trust",
    "AI agent security",
    "agent verification",
    "decentralized identity",
    "DID agent",
    "agent social network",
    "moltbook breach",
    "moltbook leaked",
    "openclaw vulnerability",
    "openclaw CVE",
    "agent framework security",
    "agent reputation",
    "agent interoperability",
]


def _get_monitoring_adapters() -> dict[str, AbstractPlatformAdapter]:
    """Get adapters that support keyword monitoring."""
    from src.marketing.adapters.github_discussions import GitHubDiscussionsAdapter
    from src.marketing.adapters.hackernews import HackerNewsAdapter
    from src.marketing.adapters.reddit import RedditAdapter

    adapters: dict[str, AbstractPlatformAdapter] = {
        "reddit": RedditAdapter(),
        "hackernews": HackerNewsAdapter(),
        "github_discussions": GitHubDiscussionsAdapter(),
    }
    # Twitter search requires Basic tier
    return adapters


async def run_monitoring_cycle(db: AsyncSession) -> dict:
    """Scan platforms for keyword mentions and generate responses."""
    adapters = _get_monitoring_adapters()
    since = datetime.now(timezone.utc) - timedelta(hours=6)

    results: dict = {"mentions_found": 0, "replies_generated": 0, "errors": 0}

    for platform_name, adapter in adapters.items():
        if not await adapter.is_configured():
            continue

        try:
            mentions = await adapter.search_keywords(MONITOR_KEYWORDS, since=since)
            results["mentions_found"] += len(mentions)

            for mention in mentions[:5]:  # Cap at 5 per platform per cycle
                # Check if we already replied
                existing = await db.execute(
                    select(MarketingPost.id).where(
                        MarketingPost.platform == platform_name,
                        MarketingPost.parent_external_id == mention.external_id,
                    ).limit(1),
                )
                if existing.scalar_one_or_none():
                    continue

                # Generate reactive content
                content = await generate_reactive(
                    platform_name,
                    mention_content=mention.content[:500],
                    mention_author=mention.author,
                )

                if content.error:
                    results["errors"] += 1
                    continue

                # All platforms require human approval for reactive replies
                # (checked against orchestrator's HUMAN_APPROVAL_PLATFORMS)
                if platform_name in HUMAN_APPROVAL_PLATFORMS:
                    await _save_post(
                        db, content, status="human_review",
                    )
                else:
                    # Fallback: still require human review for safety
                    await _save_post(db, content, status="human_review")

                results["replies_generated"] += 1

        except Exception:
            logger.exception("Monitoring failed for %s", platform_name)
            results["errors"] += 1

    logger.info("Monitor cycle: %s", results)
    return results
