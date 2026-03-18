"""Marketing-specific scheduling with per-platform cadences.

Uses Redis timestamps to track when each platform was last posted to,
ensuring we respect rate limits and cadence settings.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# Redis key prefix for schedule tracking
_SCHEDULE_PREFIX = "ag:mktg:schedule"


async def should_post(platform: str, interval_seconds: int) -> bool:
    """Check if enough time has passed since the last post on this platform."""
    try:
        from src.redis_client import get_redis

        r = get_redis()
        key = f"{_SCHEDULE_PREFIX}:{platform}:last_post"
        last = await r.get(key)
        if last is None:
            return True
        return (time.time() - float(last)) >= interval_seconds
    except Exception:
        # If Redis is down, allow the post (better to double-post than miss)
        return True


async def record_post(platform: str) -> None:
    """Record that a post was just made on a platform."""
    try:
        from src.redis_client import get_redis

        r = get_redis()
        key = f"{_SCHEDULE_PREFIX}:{platform}:last_post"
        await r.set(key, str(time.time()), ex=86400 * 7)  # 7 day TTL
    except Exception:
        logger.debug("Failed to record post time for %s", platform)


async def get_recent_topics(platform: str, limit: int = 5) -> list[str]:
    """Get recently used topics for a platform (for cooldown)."""
    try:
        from src.redis_client import get_redis

        r = get_redis()
        key = f"{_SCHEDULE_PREFIX}:{platform}:recent_topics"
        raw = await r.lrange(key, 0, limit - 1)
        return [t.decode() if isinstance(t, bytes) else t for t in raw]
    except Exception:
        return []


async def record_topic(platform: str, topic: str) -> None:
    """Record a topic as recently used on a platform."""
    try:
        from src.redis_client import get_redis

        r = get_redis()
        key = f"{_SCHEDULE_PREFIX}:{platform}:recent_topics"
        pipe = r.pipeline()
        pipe.lpush(key, topic)
        pipe.ltrim(key, 0, 9)  # Keep last 10
        pipe.expire(key, 86400 * 7)
        await pipe.execute()
    except Exception:
        logger.debug("Failed to record topic for %s", platform)


async def get_platform_intervals() -> dict[str, int]:
    """Get configured posting intervals for all platforms."""
    from src.marketing.config import marketing_settings

    return {
        "twitter": marketing_settings.twitter_post_interval,
        "reddit": marketing_settings.reddit_post_interval,
        "discord": marketing_settings.discord_post_interval,
        "linkedin": marketing_settings.linkedin_post_interval,
        "bluesky": marketing_settings.bluesky_post_interval,
        "telegram": marketing_settings.telegram_post_interval,
        "devto": marketing_settings.devto_post_interval,
        "hashnode": marketing_settings.hashnode_post_interval,
    }
