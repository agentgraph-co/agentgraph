"""Shared Redis client for AgentGraph.

Provides async Redis connections for rate limiting, caching,
pub/sub event distribution, and WebSocket coordination.
"""
from __future__ import annotations

import logging

import redis.asyncio as aioredis

from src.config import settings

logger = logging.getLogger(__name__)

# Shared connection pool — reused across all Redis consumers
_pool: aioredis.ConnectionPool | None = None


def _get_pool() -> aioredis.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=20,
            decode_responses=True,
        )
    return _pool


def get_redis() -> aioredis.Redis:
    """Return a Redis client using the shared connection pool."""
    return aioredis.Redis(connection_pool=_get_pool())


async def check_redis() -> bool:
    """Check Redis connectivity. Returns True if healthy."""
    try:
        r = get_redis()
        return await r.ping()
    except Exception:
        logger.warning("Redis health check failed")
        return False


async def close_redis() -> None:
    """Close the Redis connection pool on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
