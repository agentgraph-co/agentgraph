from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def get_google_auth_url(redirect_uri: str, state: str = "") -> str:
    """Build the Google OAuth2 consent URL."""
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    if state:
        params["state"] = state
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_google_code(code: str, redirect_uri: str) -> dict | None:
    """Exchange authorization code for user info.

    Returns dict with keys: email, name, picture, id (Google user ID).
    Returns None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            if token_resp.status_code != 200:
                logger.error("Google token exchange failed: %s", token_resp.text)
                return None

            tokens = token_resp.json()
            access_token = tokens.get("access_token")
            if not access_token:
                return None

            userinfo_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_resp.status_code != 200:
                logger.error("Google userinfo failed: %s", userinfo_resp.text)
                return None

            return userinfo_resp.json()
    except Exception:
        logger.exception("Google OAuth exchange error")
        return None
