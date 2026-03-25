"""Auto-follow reply target accounts on Bluesky.

Reads active reply_targets from the DB, resolves each Bluesky handle
to a DID via the public API, and follows them using the AT Protocol.

Idempotent: checks existing follows before creating new ones.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_PDS_URL = "https://bsky.social/xrpc"
_TIMEOUT = 15.0


async def _create_session(
    handle: str, app_password: str,
) -> tuple[str, str]:
    """Authenticate and return (access_jwt, did)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_PDS_URL}/com.atproto.server.createSession",
            json={"identifier": handle, "password": app_password},
        )
        resp.raise_for_status()
        data = resp.json()
    return data["accessJwt"], data["did"]


async def _resolve_handle(handle: str) -> str | None:
    """Resolve a Bluesky handle to a DID via public API."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_PDS_URL}/com.atproto.identity.resolveHandle",
                params={"handle": handle},
            )
            resp.raise_for_status()
            return resp.json()["did"]
    except Exception as exc:
        logger.warning("Could not resolve handle %s: %s", handle, exc)
        return None


async def _get_existing_follows(
    jwt: str, actor_did: str,
) -> set[str]:
    """Fetch all DIDs the actor currently follows."""
    follows: set[str] = set()
    cursor = None
    while True:
        params: dict[str, str | int] = {
            "actor": actor_did,
            "limit": 100,
        }
        if cursor:
            params["cursor"] = cursor
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"{_PDS_URL}/app.bsky.graph.getFollows",
                    params=params,
                    headers={"Authorization": f"Bearer {jwt}"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Failed to fetch follows page: %s", exc)
            break

        for f in data.get("follows", []):
            did = f.get("did")
            if did:
                follows.add(did)

        cursor = data.get("cursor")
        if not cursor:
            break

    return follows


async def _follow_did(
    jwt: str, actor_did: str, target_did: str,
) -> bool:
    """Create a follow record for the target DID."""
    from datetime import datetime, timezone

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_PDS_URL}/com.atproto.repo.createRecord",
                json={
                    "repo": actor_did,
                    "collection": "app.bsky.graph.follow",
                    "record": {
                        "$type": "app.bsky.graph.follow",
                        "subject": target_did,
                        "createdAt": datetime.now(
                            timezone.utc,
                        ).isoformat(),
                    },
                },
                headers={"Authorization": f"Bearer {jwt}"},
            )
            resp.raise_for_status()
            return True
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Follow failed for %s: HTTP %s — %s",
            target_did,
            exc.response.status_code,
            exc.response.text[:200],
        )
        return False
    except Exception as exc:
        logger.warning("Follow failed for %s: %s", target_did, exc)
        return False


async def run_auto_follow() -> dict[str, int]:
    """Follow all active Bluesky reply targets.

    Returns stats dict with keys: followed, already, failed, skipped.
    """
    from sqlalchemy import text

    from src.database import async_session
    from src.marketing.config import marketing_settings

    handle = marketing_settings.bluesky_handle
    password = marketing_settings.bluesky_app_password
    if not handle or not password:
        logger.debug("Auto-follow skipped: BLUESKY_HANDLE or APP_PASSWORD not set")
        return {"followed": 0, "already": 0, "failed": 0, "skipped": 1}

    # Load active Bluesky targets from DB
    async with async_session() as db:
        result = await db.execute(
            text(
                "SELECT handle, display_name "
                "FROM reply_targets "
                "WHERE is_active = true AND platform = 'bluesky' "
                "ORDER BY priority_tier, handle"
            ),
        )
        targets = result.fetchall()

    if not targets:
        logger.debug("Auto-follow: no active Bluesky targets")
        return {"followed": 0, "already": 0, "failed": 0, "skipped": 0}

    # Authenticate
    jwt, actor_did = await _create_session(handle, password)

    # Get existing follows
    existing = await _get_existing_follows(jwt, actor_did)

    followed = 0
    already = 0
    failed = 0

    for row_handle, display_name in targets:
        target_did = await _resolve_handle(row_handle)
        if not target_did:
            failed += 1
            continue

        if target_did in existing:
            already += 1
            continue

        ok = await _follow_did(jwt, actor_did, target_did)
        if ok:
            logger.info("Auto-followed %s (%s)", row_handle, display_name)
            followed += 1
        else:
            failed += 1

        await asyncio.sleep(0.5)

    return {"followed": followed, "already": already, "failed": failed, "skipped": 0}
