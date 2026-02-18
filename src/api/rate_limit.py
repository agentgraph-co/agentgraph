from __future__ import annotations

import time

from fastapi import HTTPException, Request, status

from src.config import settings


class InMemoryRateLimiter:
    """Simple in-memory rate limiter using sliding window.

    Uses dict-based storage. Will be replaced with Redis when
    Redis integration is added for production.
    """

    def __init__(self):
        self._windows: dict[str, list[float]] = {}

    def _clean_window(self, key: str, window_seconds: int) -> None:
        now = time.time()
        if key in self._windows:
            self._windows[key] = [
                t for t in self._windows[key] if now - t < window_seconds
            ]

    def check(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        """Returns True if request is allowed, False if rate limited."""
        self._clean_window(key, window_seconds)
        if key not in self._windows:
            self._windows[key] = []
        if len(self._windows[key]) >= limit:
            return False
        self._windows[key].append(time.time())
        return True

    def get_remaining(self, key: str, limit: int, window_seconds: int = 60) -> int:
        """Return how many requests remain in the current window."""
        self._clean_window(key, window_seconds)
        used = len(self._windows.get(key, []))
        return max(0, limit - used)

    def get_reset_time(self, key: str, window_seconds: int = 60) -> int:
        """Return seconds until the oldest request in the window expires."""
        if key not in self._windows or not self._windows[key]:
            return 0
        oldest = min(self._windows[key])
        return max(0, int(window_seconds - (time.time() - oldest)))


# Global instance
_limiter = InMemoryRateLimiter()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


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


def _set_rate_limit_headers(
    request: Request, key: str, limit: int, window: int = 60,
) -> None:
    """Store rate limit info on request state for middleware to add to response."""
    remaining = _limiter.get_remaining(key, limit, window)
    reset = _limiter.get_reset_time(key, window)
    request.state.rate_limit_limit = limit
    request.state.rate_limit_remaining = remaining
    request.state.rate_limit_reset = reset


async def rate_limit_reads(request: Request) -> None:
    ip = _get_client_ip(request)
    limit = settings.rate_limit_reads_per_minute
    key = f"read:{ip}"
    if not _limiter.check(key, limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers=_rate_limit_response(0, limit),
        )
    _set_rate_limit_headers(request, key, limit)
    # Per-entity limit (2x IP limit to be generous)
    entity_id = _get_entity_id(request)
    if entity_id:
        entity_limit = limit * 2
        if not _limiter.check(f"read:entity:{entity_id}", entity_limit):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers=_rate_limit_response(0, entity_limit),
            )


async def rate_limit_writes(request: Request) -> None:
    ip = _get_client_ip(request)
    limit = settings.rate_limit_writes_per_minute
    key = f"write:{ip}"
    if not _limiter.check(key, limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers=_rate_limit_response(0, limit),
        )
    _set_rate_limit_headers(request, key, limit)
    entity_id = _get_entity_id(request)
    if entity_id:
        entity_limit = limit * 2
        if not _limiter.check(f"write:entity:{entity_id}", entity_limit):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers=_rate_limit_response(0, entity_limit),
            )


async def rate_limit_auth(request: Request) -> None:
    """Stricter limit for auth endpoints."""
    ip = _get_client_ip(request)
    limit = settings.rate_limit_auth_per_minute
    key = f"auth:{ip}"
    if not _limiter.check(key, limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
            headers=_rate_limit_response(0, limit),
        )
    _set_rate_limit_headers(request, key, limit)
