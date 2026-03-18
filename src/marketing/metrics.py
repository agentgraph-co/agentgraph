"""Engagement metric refresh — pulls stats from platform APIs.

Runs every 2 hours, updates marketing_posts.metrics_json for
recent posts (last 7 days).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.marketing.adapters.base import AbstractPlatformAdapter
from src.marketing.models import MarketingPost

logger = logging.getLogger(__name__)


def _get_all_adapters() -> dict[str, AbstractPlatformAdapter]:
    """Load all adapters for metric fetching."""
    from src.marketing.adapters.bluesky import BlueskyAdapter
    from src.marketing.adapters.devto import DevtoAdapter
    from src.marketing.adapters.reddit import RedditAdapter
    from src.marketing.adapters.twitter import TwitterAdapter

    return {
        "twitter": TwitterAdapter(),
        "reddit": RedditAdapter(),
        "bluesky": BlueskyAdapter(),
        "devto": DevtoAdapter(),
    }


async def refresh_metrics(db: AsyncSession) -> dict:
    """Refresh engagement metrics for recent posted content."""
    adapters = _get_all_adapters()
    window = datetime.now(timezone.utc) - timedelta(days=7)

    result = await db.execute(
        select(MarketingPost).where(
            MarketingPost.status == "posted",
            MarketingPost.posted_at >= window,
            MarketingPost.external_id.isnot(None),
        ).order_by(MarketingPost.metrics_updated_at.asc().nullsfirst()).limit(50),
    )
    posts = list(result.scalars().all())

    updated = 0
    errors = 0

    for post in posts:
        adapter = adapters.get(post.platform)
        if not adapter or not await adapter.is_configured():
            continue

        try:
            metrics = await adapter.fetch_metrics(post.external_id)
            post.metrics_json = {
                "likes": metrics.likes,
                "comments": metrics.comments,
                "shares": metrics.shares,
                "impressions": metrics.impressions,
                "clicks": metrics.clicks,
            }
            if metrics.extra:
                post.metrics_json["extra"] = metrics.extra
            post.metrics_updated_at = datetime.now(timezone.utc)
            updated += 1
        except Exception:
            logger.debug("Metric refresh failed for %s/%s", post.platform, post.id)
            errors += 1

    await db.flush()

    logger.info("Metrics refreshed: %d updated, %d errors", updated, errors)
    return {"updated": updated, "errors": errors, "total_checked": len(posts)}
