#!/usr/bin/env python3
"""Auto-follow reply target accounts on Bluesky.

Reads active reply_targets from the DB, resolves each Bluesky handle
to a DID via the public API, and follows them using the AT Protocol.
Twitter targets are logged but not followed (requires OAuth).

Idempotent: checks existing follows before creating new ones.

Usage:
    DATABASE_URL=postgresql+asyncpg://localhost:5432/agentgraph_staging \
        python3 scripts/auto_follow_targets.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
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


async def main() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    # --- Validate env ---
    bsky_handle = os.environ.get("BLUESKY_HANDLE", "")
    bsky_password = os.environ.get("BLUESKY_APP_PASSWORD", "")
    if not bsky_handle or not bsky_password:
        logger.error(
            "BLUESKY_HANDLE and BLUESKY_APP_PASSWORD must be set in env",
        )
        sys.exit(1)

    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://localhost:5432/agentgraph_staging",
    )

    # --- Load active targets from DB ---
    engine = create_async_engine(db_url)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False,
    )

    async with async_session() as db:
        result = await db.execute(
            text(
                "SELECT platform, handle, display_name "
                "FROM reply_targets WHERE is_active = true "
                "ORDER BY priority_tier, platform, handle"
            ),
        )
        targets = result.fetchall()

    await engine.dispose()

    bluesky_targets = [
        (h, dn) for p, h, dn in targets if p == "bluesky"
    ]
    twitter_targets = [
        (h, dn) for p, h, dn in targets if p == "twitter"
    ]

    # --- Bluesky follows ---
    if bluesky_targets:
        logger.info(
            "Authenticating as %s on Bluesky...", bsky_handle,
        )
        jwt, actor_did = await _create_session(bsky_handle, bsky_password)
        logger.info("Authenticated. DID: %s", actor_did)

        logger.info("Fetching existing follows...")
        existing = await _get_existing_follows(jwt, actor_did)
        logger.info("Currently following %d accounts", len(existing))

        followed = 0
        skipped = 0
        failed = 0

        for handle, display_name in bluesky_targets:
            target_did = await _resolve_handle(handle)
            if not target_did:
                logger.warning(
                    "  SKIP  %s (%s) — could not resolve DID",
                    handle,
                    display_name,
                )
                failed += 1
                continue

            if target_did in existing:
                logger.info(
                    "  ALREADY  %s (%s)", handle, display_name,
                )
                skipped += 1
                continue

            ok = await _follow_did(jwt, actor_did, target_did)
            if ok:
                logger.info(
                    "  FOLLOWED  %s (%s)", handle, display_name,
                )
                followed += 1
            else:
                failed += 1

            # Small delay to be polite to the API
            await asyncio.sleep(0.5)

        logger.info(
            "Bluesky: %d followed, %d already followed, %d failed",
            followed,
            skipped,
            failed,
        )

    # --- Twitter (log only) ---
    if twitter_targets:
        logger.info(
            "Twitter targets (%d) — logged only, "
            "manual follow required:",
            len(twitter_targets),
        )
        for handle, display_name in twitter_targets:
            logger.info(
                "  @%s (%s) — https://twitter.com/%s",
                handle,
                display_name,
                handle,
            )


if __name__ == "__main__":
    asyncio.run(main())
