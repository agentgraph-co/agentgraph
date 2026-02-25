"""Rate limiting using Redis sliding window counters.

Supports per-IP and per-entity limits for reads, writes, and auth.
Falls back to in-memory tracking if Redis is unavailable.
"""
from __future__ import annotations

import logging
import time

from fastapi import HTTPException, Request, status

from src.config import settings

logger = logging.getLogger(__name__)


class RedisRateLimiter:
    """Rate limiter backed by Redis sorted sets (sliding window).

    Each key is a Redis sorted set where members are unique request IDs
    and scores are timestamps. This provides accurate sliding window
    counting that works across multiple Gunicorn workers.

    Falls back to in-memory when Redis is unreachable.
    """

    def __init__(self) -> None:
        self._fallback: dict[str, list[float]] = {}

    async def check(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        """Returns True if request is allowed, False if rate limited."""
        try:
            from src.redis_client import get_redis

            r = get_redis()
            now = time.time()
            redis_key = f"rl:{key}"

            pipe = r.pipeline()
            pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
            pipe.zcard(redis_key)
            pipe.zadd(redis_key, {f"{now}:{id(pipe)}": now})
            pipe.expire(redis_key, window_seconds + 1)
            results = await pipe.execute()

            count = results[1]
            if count >= limit:
                # Remove the entry we just added
                await r.zrem(redis_key, f"{now}:{id(pipe)}")
                return False
            return True
        except Exception:
            return self._check_fallback(key, limit, window_seconds)

    async def get_remaining(self, key: str, limit: int, window_seconds: int = 60) -> int:
        """Return how many requests remain in the current window."""
        try:
            from src.redis_client import get_redis

            r = get_redis()
            now = time.time()
            redis_key = f"rl:{key}"
            await r.zremrangebyscore(redis_key, 0, now - window_seconds)
            count = await r.zcard(redis_key)
            return max(0, limit - count)
        except Exception:
            return self._remaining_fallback(key, limit, window_seconds)

    async def get_reset_time(self, key: str, window_seconds: int = 60) -> int:
        """Return seconds until the oldest request in the window expires."""
        try:
            from src.redis_client import get_redis

            r = get_redis()
            redis_key = f"rl:{key}"
            oldest = await r.zrange(redis_key, 0, 0, withscores=True)
            if not oldest:
                return 0
            return max(0, int(window_seconds - (time.time() - oldest[0][1])))
        except Exception:
            return self._reset_fallback(key, window_seconds)

    # --- In-memory fallbacks ---

    def _clean_window(self, key: str, window_seconds: int) -> None:
        now = time.time()
        if key in self._fallback:
            self._fallback[key] = [
                t for t in self._fallback[key] if now - t < window_seconds
            ]

    def _check_fallback(self, key: str, limit: int, window_seconds: int) -> bool:
        self._clean_window(key, window_seconds)
        if key not in self._fallback:
            self._fallback[key] = []
        if len(self._fallback[key]) >= limit:
            return False
        self._fallback[key].append(time.time())
        return True

    def _remaining_fallback(self, key: str, limit: int, window_seconds: int) -> int:
        self._clean_window(key, window_seconds)
        used = len(self._fallback.get(key, []))
        return max(0, limit - used)

    def _reset_fallback(self, key: str, window_seconds: int) -> int:
        if key not in self._fallback or not self._fallback[key]:
            return 0
        oldest = min(self._fallback[key])
        return max(0, int(window_seconds - (time.time() - oldest)))

    def clear(self) -> None:
        """Clear in-memory fallback. For testing."""
        self._fallback.clear()

    async def clear_all(self) -> None:
        """Clear in-memory fallback AND Redis rate limit keys. For testing."""
        self._fallback.clear()
        try:
            from src.redis_client import get_redis

            r = get_redis()
            keys = await r.keys("rl:*")
            if keys:
                await r.delete(*keys)
        except Exception:
            pass


# Global instance
_limiter = RedisRateLimiter()


def _get_client_ip(request: Request) -> str:
    from src.config import settings

    direct_ip = request.client.host if request.client else "unknown"
    # Only trust X-Forwarded-For when the direct client is a known proxy
    if direct_ip in settings.trusted_proxies:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return direct_ip


def _get_entity_id(request: Request) -> str | None:
    """Extract entity ID from request state if authenticated."""
    return getattr(request.state, "entity_id", None)


def _rate_limit_response(
    remaining: int, limit: int, window: int = 60,
) -> dict[str, str]:
    """Generate rate limit headers."""
    return {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(max(0, remaining)),
        "X-RateLimit-Window": str(window),
    }


async def _set_rate_limit_headers(
    request: Request, key: str, limit: int, window: int = 60,
) -> None:
    """Store rate limit info on request state for middleware to add to response."""
    remaining = await _limiter.get_remaining(key, limit, window)
    reset = await _limiter.get_reset_time(key, window)
    request.state.rate_limit_limit = limit
    request.state.rate_limit_remaining = remaining
    request.state.rate_limit_reset = reset


async def rate_limit_reads(request: Request) -> None:
    ip = _get_client_ip(request)
    limit = settings.rate_limit_reads_per_minute
    key = f"read:{ip}"
    if not await _limiter.check(key, limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers=_rate_limit_response(0, limit),
        )
    entity_id = _get_entity_id(request)
    effective_limit = limit * 3 if entity_id else limit
    await _set_rate_limit_headers(request, key, effective_limit)
    if entity_id:
        if not await _limiter.check(f"read:entity:{entity_id}", effective_limit):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers=_rate_limit_response(0, effective_limit),
            )


async def rate_limit_writes(request: Request) -> None:
    ip = _get_client_ip(request)
    limit = settings.rate_limit_writes_per_minute
    key = f"write:{ip}"
    if not await _limiter.check(key, limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers=_rate_limit_response(0, limit),
        )
    entity_id = _get_entity_id(request)
    effective_limit = limit * 3 if entity_id else limit
    await _set_rate_limit_headers(request, key, effective_limit)
    if entity_id:
        if not await _limiter.check(f"write:entity:{entity_id}", effective_limit):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers=_rate_limit_response(0, effective_limit),
            )


async def rate_limit_export(request: Request) -> None:
    """Very strict limit for heavy export endpoints (5/hour)."""
    ip = _get_client_ip(request)
    key = f"export:{ip}"
    limit = 5
    window = 3600
    if not await _limiter.check(key, limit, window):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Export rate limit exceeded. Try again later.",
            headers=_rate_limit_response(0, limit, window),
        )
    entity_id = _get_entity_id(request)
    if entity_id:
        ekey = f"export:entity:{entity_id}"
        if not await _limiter.check(ekey, limit, window):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Export rate limit exceeded. Try again later.",
                headers=_rate_limit_response(0, limit, window),
            )
    await _set_rate_limit_headers(request, key, limit, window)


async def rate_limit_auth(request: Request) -> None:
    """Stricter limit for auth endpoints."""
    ip = _get_client_ip(request)
    limit = settings.rate_limit_auth_per_minute
    key = f"auth:{ip}"
    if not await _limiter.check(key, limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
            headers=_rate_limit_response(0, limit),
        )
    await _set_rate_limit_headers(request, key, limit)
