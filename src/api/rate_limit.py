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


# Global instance
_limiter = InMemoryRateLimiter()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def rate_limit_reads(request: Request) -> None:
    ip = _get_client_ip(request)
    if not _limiter.check(f"read:{ip}", settings.rate_limit_reads_per_minute):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )


async def rate_limit_writes(request: Request) -> None:
    ip = _get_client_ip(request)
    if not _limiter.check(f"write:{ip}", settings.rate_limit_writes_per_minute):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )


async def rate_limit_auth(request: Request) -> None:
    """Stricter limit for auth endpoints: 5/min per IP."""
    ip = _get_client_ip(request)
    if not _limiter.check(f"auth:{ip}", 5):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
        )
