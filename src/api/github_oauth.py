"""GitHub OAuth2 helpers — mirrors google_auth.py pattern."""
from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"


def get_github_auth_url(
    redirect_uri: str, state: str = "", scope: str = "read:user",
) -> str:
    """Build the GitHub OAuth2 consent URL."""
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
    }
    return f"{GITHUB_AUTH_URL}?{urlencode(params)}"


async def exchange_github_code(code: str, redirect_uri: str) -> dict | None:
    """Exchange authorization code for user info.

    Returns dict with keys: id, login, name, avatar_url, bio, public_repos,
    followers, following, created_at.
    Returns None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token_resp = await client.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            if token_resp.status_code != 200:
                logger.error("GitHub token exchange failed: %s", token_resp.text)
                return None

            tokens = token_resp.json()
            access_token = tokens.get("access_token")
            if not access_token:
                logger.error("GitHub token response missing access_token")
                return None

            userinfo_resp = await client.get(
                f"{GITHUB_API_URL}/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            if userinfo_resp.status_code != 200:
                logger.error("GitHub userinfo failed: %s", userinfo_resp.text)
                return None

            user_data = userinfo_resp.json()
            user_data["_access_token"] = access_token
            return user_data
    except Exception:
        logger.exception("GitHub OAuth exchange error")
        return None


async def fetch_github_email(access_token: str) -> str | None:
    """Fetch the user's primary verified email from GitHub."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{GITHUB_API_URL}/user/emails",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            if resp.status_code != 200:
                return None
            emails = resp.json()
            # Prefer primary verified email
            for e in emails:
                if e.get("primary") and e.get("verified"):
                    return e["email"]
            # Fallback: any verified email
            for e in emails:
                if e.get("verified"):
                    return e["email"]
            return None
    except Exception:
        logger.exception("GitHub email fetch error")
        return None


async def fetch_github_repos(access_token: str) -> list[dict]:
    """Fetch user's repos (up to 100, sorted by updated)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{GITHUB_API_URL}/user/repos",
                params={"per_page": 100, "sort": "updated", "type": "owner"},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            if resp.status_code != 200:
                logger.error("GitHub repos fetch failed: %s", resp.text)
                return []
            return resp.json()
    except Exception:
        logger.exception("GitHub repos fetch error")
        return []
