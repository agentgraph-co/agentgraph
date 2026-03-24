"""Monitor target accounts for new posts to reply to."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from src.database import async_session
from src.models import ReplyOpportunity, ReplyTarget

logger = logging.getLogger(__name__)

# Keywords that boost relevance score when found in a post
_RELEVANCE_KEYWORDS = [
    "ai agent", "mcp server", "agent trust", "autonomous agent",
    "tool use", "agentic", "agent identity", "did", "verifiable",
    "agent framework", "langchain", "crewai", "autogen", "agent orchestration",
    "trust score", "agent verification",
]


async def monitor_all_targets() -> dict:
    """Check all active targets for new posts. Returns stats."""
    async with async_session() as db:
        targets = (
            await db.scalars(
                select(ReplyTarget)
                .where(ReplyTarget.is_active.is_(True))
                .order_by(
                    ReplyTarget.priority_tier,
                    ReplyTarget.last_checked_at.asc().nullsfirst(),
                )
            )
        ).all()

    stats: dict = {"checked": 0, "new_opportunities": 0, "errors": 0}
    for target in targets:
        try:
            count = await _check_target(target)
            stats["checked"] += 1
            stats["new_opportunities"] += count
        except Exception:
            logger.exception(
                "Error checking target %s/%s", target.platform, target.handle,
            )
            stats["errors"] += 1

    logger.info("Reply monitor: %s", stats)
    return stats


async def _check_target(target: ReplyTarget) -> int:
    """Check a single target for new posts. Returns number of new opportunities."""
    since = target.last_checked_at or (
        datetime.now(timezone.utc) - timedelta(hours=24)
    )

    if target.platform == "bluesky":
        posts = await _fetch_bluesky_posts(target.handle, since)
    elif target.platform == "twitter":
        posts = await _fetch_twitter_posts(target.handle, since)
    else:
        return 0

    new_count = 0
    async with async_session() as db:
        for post in posts:
            # Dedup check
            existing = await db.scalar(
                select(ReplyOpportunity).where(
                    ReplyOpportunity.platform == target.platform,
                    ReplyOpportunity.post_uri == post["uri"],
                )
            )
            if existing:
                continue

            urgency = _calculate_urgency(post, target)
            opp = ReplyOpportunity(
                target_id=target.id,
                platform=target.platform,
                post_uri=post["uri"],
                post_content=post.get("text", ""),
                post_timestamp=post["timestamp"],
                status="new",
                urgency_score=urgency,
                engagement_count=post.get("likes", 0),
            )
            db.add(opp)
            new_count += 1

        # Update last_checked_at
        await db.execute(
            update(ReplyTarget)
            .where(ReplyTarget.id == target.id)
            .values(last_checked_at=datetime.now(timezone.utc))
        )
        await db.commit()

    return new_count


def _calculate_urgency(post: dict, target: ReplyTarget) -> float:
    """Calculate urgency score for a reply opportunity.

    Higher = should reply sooner.
    Components: time decay, priority tier, topic relevance, engagement.
    """
    now = datetime.now(timezone.utc)
    post_time = post["timestamp"]
    if post_time.tzinfo is None:
        post_time = post_time.replace(tzinfo=timezone.utc)

    hours_since = (now - post_time).total_seconds() / 3600
    # Exponential decay: 15min=~1.0, 1hr=~0.6, 4hr=~0.13
    time_decay = math.exp(-0.5 * max(hours_since, 0))

    tier_multiplier = {1: 3.0, 2: 2.0, 3: 1.0}.get(target.priority_tier, 1.0)

    # Topic relevance
    text_lower = post.get("text", "").lower()
    relevance = 0.5 if any(kw in text_lower for kw in _RELEVANCE_KEYWORDS) else 0.0

    # Engagement boost (capped)
    engagement = min(1.0, post.get("likes", 0) / 100)

    return time_decay * tier_multiplier + relevance + engagement


async def _fetch_bluesky_posts(handle: str, since: datetime) -> list:
    """Fetch recent posts from a Bluesky account."""
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed",
                params={
                    "actor": handle,
                    "limit": 30,
                    "filter": "posts_no_replies",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Bluesky getAuthorFeed failed for %s: %s",
                    handle,
                    resp.status_code,
                )
                return []
            data = resp.json()

        posts = []
        for item in data.get("feed", []):
            post_data = item.get("post", {})
            record = post_data.get("record", {})
            created_str = record.get("createdAt", "")
            if not created_str:
                continue
            # Parse ISO timestamp
            created = datetime.fromisoformat(
                created_str.replace("Z", "+00:00"),
            )
            if created <= since:
                continue
            posts.append({
                "uri": post_data.get("uri", ""),
                "text": record.get("text", ""),
                "timestamp": created,
                "likes": post_data.get("likeCount", 0),
            })
        return posts
    except Exception:
        logger.exception("Failed to fetch Bluesky posts for %s", handle)
        return []


async def _fetch_twitter_posts(handle: str, since: datetime) -> list:
    """Fetch recent posts from a Twitter account.

    NOTE: Twitter API v2 requires elevated access for user timeline.
    This is a placeholder -- returns empty until Twitter API is configured.
    """
    # Twitter API requires OAuth and elevated access for reading other
    # users' timelines.  For now, return empty.  The reply guy system
    # works primarily with Bluesky.
    logger.debug("Twitter timeline fetch not yet implemented for %s", handle)
    return []
