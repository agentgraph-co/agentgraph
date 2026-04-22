"""Redis caching utilities for AgentGraph.

Provides simple get/set/invalidate with JSON serialization and TTL.
All operations gracefully degrade — cache misses simply fall through
to the database, and Redis failures are silently ignored.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Default TTLs in seconds
TTL_SHORT = 30       # 30 seconds — fast-changing data (feed counts)
TTL_MEDIUM = 300     # 5 minutes — moderate data (trust scores, leaderboard)
TTL_LONG = 3600      # 1 hour — slow-changing data (profile metadata)

_PREFIX = "ag:cache:"


async def get(key: str) -> Any | None:
    """Get a cached value. Returns None on miss or Redis failure."""
    try:
        from src.redis_client import get_redis

        r = get_redis()
        raw = await r.get(f"{_PREFIX}{key}")
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        return None


async def set(key: str, value: Any, ttl: int = TTL_MEDIUM) -> None:
    """Cache a value with TTL. ``ttl<=0`` means persist indefinitely.

    Silently fails if Redis is unavailable. ``ex=0`` is rejected by Redis
    with ``invalid expire time``, so callers passing ``ttl=0`` must be
    translated to an expiry-less ``SET``.
    """
    try:
        from src.redis_client import get_redis

        r = get_redis()
        payload = json.dumps(value, default=str)
        key_full = f"{_PREFIX}{key}"
        if ttl and ttl > 0:
            await r.set(key_full, payload, ex=ttl)
        else:
            await r.set(key_full, payload)
    except Exception:
        pass


async def invalidate(key: str) -> None:
    """Remove a cached value."""
    try:
        from src.redis_client import get_redis

        r = get_redis()
        await r.delete(f"{_PREFIX}{key}")
    except Exception:
        pass


async def invalidate_pattern(pattern: str) -> None:
    """Remove all keys matching a pattern (e.g., 'trust:*')."""
    try:
        from src.redis_client import get_redis

        r = get_redis()
        cursor = 0
        while True:
            cursor, keys = await r.scan(cursor, match=f"{_PREFIX}{pattern}", count=100)
            if keys:
                await r.delete(*keys)
            if cursor == 0:
                break
    except Exception:
        pass
