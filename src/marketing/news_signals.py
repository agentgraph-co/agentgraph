"""Gather trending news signals for campaign planning.

Sources:
1. Local news-digest project (digest_history.json) — recent articles
2. HN Algolia API — AI agent and security stories
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Path to the news-digest history file:
# - Local (Mac Mini): ~/projects/news-digest/digest_history.json
# - EC2 (prod): ~/agentgraph/digest_history.json (synced via scp)
_DIGEST_PATHS = [
    Path.home() / "projects" / "news-digest" / "digest_history.json",
    Path.home() / "agentgraph" / "digest_history.json",
    Path("/home/ec2-user/agentgraph/digest_history.json"),
]

_HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
_HN_QUERIES = ["AI agent", "agent security", "decentralized identity"]
_HN_TIMEOUT = 10.0


def _find_digest_file() -> Path | None:
    """Find the digest history file from known paths."""
    for p in _DIGEST_PATHS:
        if p.exists():
            return p
    return None


def _parse_digest_history(
    limit: int = 10,
) -> list[dict]:
    """Read recent articles from the news-digest history file."""
    digest_path = _find_digest_file()
    if not digest_path:
        logger.info("News digest history not found in any path")
        return []

    try:
        data = json.loads(digest_path.read_text())
    except (json.JSONDecodeError, OSError):
        logger.warning(
            "Failed to parse digest_history.json", exc_info=True,
        )
        return []

    sent = data.get("sent_articles", {})
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent: list[dict] = []

    for _hash, article in sent.items():
        sent_at = article.get("sent_at", "")
        try:
            ts = datetime.fromisoformat(
                sent_at.replace("Z", "+00:00"),
            )
        except (ValueError, AttributeError):
            continue

        if ts < cutoff:
            continue

        recent.append({
            "title": article.get("title", ""),
            "source": article.get("source", "news-digest"),
            "url": article.get("link", ""),
            "relevance": "news_digest",
            "timestamp": ts.isoformat(),
        })

    recent.sort(key=lambda a: a["timestamp"], reverse=True)
    return recent[:limit]


async def _fetch_hn_stories(
    query: str, limit: int = 5,
) -> list[dict]:
    """Fetch recent HN stories matching a query via Algolia."""
    params = {
        "query": query,
        "tags": "story",
        "numericFilters": (
            "created_at_i>"
            + str(
                int(
                    (
                        datetime.now(timezone.utc)
                        - timedelta(days=3)
                    ).timestamp(),
                ),
            )
        ),
        "hitsPerPage": limit,
    }
    try:
        async with httpx.AsyncClient(
            timeout=_HN_TIMEOUT,
        ) as client:
            resp = await client.get(
                _HN_SEARCH_URL, params=params,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.warning(
            "HN Algolia query failed for %r", query, exc_info=True,
        )
        return []

    results: list[dict] = []
    for hit in data.get("hits", []):
        title = hit.get("title", "")
        url = hit.get("url") or (
            f"https://news.ycombinator.com/item?id="
            f"{hit.get('objectID', '')}"
        )
        results.append({
            "title": title,
            "source": "hackernews",
            "url": url,
            "relevance": query,
            "timestamp": hit.get(
                "created_at", "",
            ),
        })
    return results


def _deduplicate(
    signals: list[dict],
) -> list[dict]:
    """Remove near-duplicate signals by normalised title."""
    seen: set[str] = set()
    unique: list[dict] = []
    for sig in signals:
        key = sig["title"].lower().strip()[:80]
        if key and key not in seen:
            seen.add(key)
            unique.append(sig)
    return unique


async def gather_news_signals(
    limit: int = 20,
) -> list[dict]:
    """Gather and merge news signals from all sources.

    Returns a deduplicated list sorted by recency, capped at
    *limit* items.  Each item is::

        {
            "title": str,
            "source": str,
            "url": str,
            "relevance": str,
        }
    """
    signals: list[dict] = _parse_digest_history(limit=limit)

    for query in _HN_QUERIES:
        hn = await _fetch_hn_stories(query, limit=5)
        signals.extend(hn)

    signals = _deduplicate(signals)

    # Sort by timestamp descending (missing → bottom)
    def _ts(item: dict) -> str:
        return item.get("timestamp", "")

    signals.sort(key=_ts, reverse=True)

    # Strip internal timestamp before returning
    cleaned: list[dict] = []
    for sig in signals[:limit]:
        cleaned.append({
            "title": sig["title"],
            "source": sig["source"],
            "url": sig["url"],
            "relevance": sig["relevance"],
        })
    return cleaned
