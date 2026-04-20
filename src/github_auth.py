"""GitHub authentication — GitHub App with PAT fallback.

Strategy:

1. If ``GITHUB_APP_ID`` + ``GITHUB_APP_PRIVATE_KEY`` + ``GITHUB_APP_INSTALLATION_ID``
   are configured, mint a short-lived JWT (10 min), exchange it for a
   1-hour installation access token, and cache that token in-process.
2. Otherwise, fall back to the legacy ``GITHUB_TOKEN`` / ``GITHUB_OUTREACH_TOKEN``
   personal access tokens. This keeps dev/staging working without app creds
   and lets prod roll forward without a flag-day cutover.

The App path is preferred because:
- The *private key* never expires (rotatable, but no clock ticking down)
- Not tied to a personal account — AgentGraph-co owns the credential
- Rate limit scales with installations (future: private-repo scanning on opt-in)
- Permissions are scoped at install time (Contents: read only)

Callers should always ``await get_github_token()`` and never read ``settings.github_token``
directly. A single cached token is shared across all callers in-process.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx
import jwt

from src.config import settings

logger = logging.getLogger(__name__)

# JWT lifetime for the app-to-GitHub auth step. Max 10 min per GitHub spec.
# We use 9 to leave headroom for clock skew.
_JWT_TTL_SECONDS = 9 * 60

# Installation tokens last 1 hour. Refresh slightly early.
_INSTALLATION_TOKEN_REFRESH_BEFORE = 5 * 60  # refresh 5 min before expiry

# Where GitHub's installation-token endpoint lives
_INSTALLATION_TOKEN_URL_TMPL = (
    "https://api.github.com/app/installations/{installation_id}/access_tokens"
)


@dataclass
class _CachedToken:
    token: str
    expires_at: float  # unix timestamp


_cache: _CachedToken | None = None
_cache_lock = asyncio.Lock()


def _app_configured() -> bool:
    """True iff all three App credentials are present."""
    return bool(
        getattr(settings, "github_app_id", None)
        and getattr(settings, "github_app_private_key", None)
        and getattr(settings, "github_app_installation_id", None)
    )


def _mint_app_jwt() -> str:
    """Mint the short-lived JWT used to authenticate as the App itself."""
    now = int(time.time())
    payload = {
        # iat 60s in the past to tolerate small clock skew
        "iat": now - 60,
        "exp": now + _JWT_TTL_SECONDS,
        "iss": settings.github_app_id,
    }
    private_key = settings.github_app_private_key
    # Support PEMs stored as escaped \n in env vars
    if "\\n" in private_key:
        private_key = private_key.replace("\\n", "\n")
    return jwt.encode(payload, private_key, algorithm="RS256")


async def _fetch_installation_token() -> _CachedToken:
    """Exchange an App JWT for a 1-hour installation access token."""
    app_jwt = _mint_app_jwt()
    url = _INSTALLATION_TOKEN_URL_TMPL.format(
        installation_id=settings.github_app_installation_id,
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {app_jwt}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers)
    if resp.status_code != 201:
        raise RuntimeError(
            f"GitHub App installation-token exchange failed: "
            f"HTTP {resp.status_code} {resp.text}"
        )
    data = resp.json()
    # expires_at is ISO-8601; trust 1-hour default and use monotonic math
    return _CachedToken(
        token=data["token"],
        expires_at=time.time() + 3600,
    )


async def get_github_token() -> str | None:
    """Return a valid GitHub token, or ``None`` if nothing is configured.

    Prefers an installation token from the GitHub App. Falls back to the
    legacy PAT. Returned tokens are suitable for ``Authorization: Bearer <token>``.
    """
    global _cache

    # Fast path: App not configured, just return the PAT (may be None).
    if not _app_configured():
        return settings.github_token or settings.github_outreach_token

    now = time.time()
    cached = _cache
    if cached and cached.expires_at - now > _INSTALLATION_TOKEN_REFRESH_BEFORE:
        return cached.token

    async with _cache_lock:
        # Re-check under lock in case another coroutine refreshed while we waited
        cached = _cache
        if cached and cached.expires_at - now > _INSTALLATION_TOKEN_REFRESH_BEFORE:
            return cached.token
        try:
            fresh = await _fetch_installation_token()
        except Exception as exc:
            logger.warning(
                "GitHub App token fetch failed, falling back to PAT: %s", exc,
            )
            return settings.github_token or settings.github_outreach_token
        _cache = fresh
        logger.info("Minted new GitHub App installation token (expires in 1h)")
        return fresh.token


async def get_github_auth_header() -> dict[str, str]:
    """Convenience: return the ``Authorization`` header dict, empty if no token."""
    token = await get_github_token()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}
