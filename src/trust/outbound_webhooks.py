"""Outbound scan-change webhooks — notify external providers when scan scores change.

When a security scan result changes for a watched repo, we POST to registered
callback URLs (e.g. MoltBridge). Fire-and-forget with 10s timeout.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from src.signing import canonicalize, create_jws

logger = logging.getLogger(__name__)

# Redis key prefix for webhook subscriptions
_WEBHOOK_PREFIX = "outbound_webhook:"


async def _get_subscriptions(repo: str) -> list[dict]:
    """Look up registered webhook URLs for a repo from Redis.

    Each subscription is stored as a JSON dict:
        {repo, callback_url, provider, registered_at}
    under key ``outbound_webhook:<repo>`` as a Redis list.
    """
    try:
        from src import cache

        data = await cache.get(f"{_WEBHOOK_PREFIX}{repo}")
        if data and isinstance(data, list):
            return data
    except Exception:
        logger.debug("Failed to read webhook subscriptions for %s", repo)
    return []


async def register_subscription(
    repo: str,
    callback_url: str,
    provider: str,
) -> dict:
    """Register an outbound webhook subscription for a repo.

    Stores in Redis as a list of dicts under ``outbound_webhook:<repo>``.
    Returns the subscription record.
    """
    from src import cache

    record = {
        "repo": repo,
        "callback_url": callback_url,
        "provider": provider,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }

    existing = await _get_subscriptions(repo)

    # Deduplicate by callback_url + provider
    existing = [
        s for s in existing
        if not (s.get("callback_url") == callback_url and s.get("provider") == provider)
    ]
    existing.append(record)

    # Store with no expiry (0 = persist)
    await cache.set(f"{_WEBHOOK_PREFIX}{repo}", existing, ttl=0)
    logger.info(
        "Registered outbound webhook: repo=%s provider=%s url=%s",
        repo, provider, callback_url,
    )
    return record


async def notify_scan_change(
    repo: str,
    new_score: int,
    old_score: int | None,
) -> None:
    """Notify registered webhooks that a scan score changed for a repo.

    Sends a signed POST to each registered callback URL. Fire-and-forget:
    failures are logged but do not block the caller.

    Args:
        repo: owner/repo identifier
        new_score: new security scan score (0-100)
        old_score: previous score, or None if first scan
    """
    subscriptions = await _get_subscriptions(repo)
    if not subscriptions:
        return

    now = datetime.now(timezone.utc).isoformat()

    # Build payload and sign it
    payload_dict = {
        "type": "ScanScoreChanged",
        "repo": repo,
        "new_score": new_score,
        "old_score": old_score,
        "changed_at": now,
    }
    payload_bytes = canonicalize(payload_dict)
    jws = create_jws(payload_bytes)

    body = {
        "repo": repo,
        "new_score": new_score,
        "old_score": old_score,
        "changed_at": now,
        "jws": jws,
    }

    for sub in subscriptions:
        callback_url = sub.get("callback_url")
        provider = sub.get("provider", "unknown")
        if not callback_url:
            continue

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    callback_url,
                    json=body,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "AgentGraph-Webhook/1.0",
                        "X-AgentGraph-Event": "scan.score.changed",
                    },
                )
            logger.info(
                "Outbound webhook delivered: repo=%s provider=%s status=%d",
                repo, provider, resp.status_code,
            )
        except httpx.TimeoutException:
            logger.warning(
                "Outbound webhook timeout: repo=%s provider=%s url=%s",
                repo, provider, callback_url,
            )
        except Exception:
            logger.exception(
                "Outbound webhook failed: repo=%s provider=%s url=%s",
                repo, provider, callback_url,
            )
