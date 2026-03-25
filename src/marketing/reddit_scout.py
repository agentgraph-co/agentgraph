"""Reddit Scout — read-only monitoring via public .json endpoints.

Scrapes public Reddit feeds without API keys (Reddit killed
self-service API access Nov 2025). Uses the /<subreddit>.json
public endpoint which requires no authentication.

Returns structured thread data filtered by configurable keywords.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# Subreddits to monitor
SCOUT_SUBREDDITS = [
    "artificial",
    "MachineLearning",
    "LangChain",
    "LocalLLaMA",
    "programming",
    "SideProject",
]

# Keywords to filter for relevance (case-insensitive)
SCOUT_KEYWORDS = [
    "agent identity",
    "agent trust",
    "AI agent security",
    "multi-agent",
    "agent framework",
    "MCP",
    "A2A protocol",
    "agent interoperability",
    "decentralized identity",
    "agent verification",
    "AI agent",
    "autonomous agent",
    "LLM agent",
    "agent orchestration",
    "tool use",
    "function calling",
    "agent marketplace",
    "agent safety",
    "bot trust",
    "agentic",
]

_USER_AGENT = "AgentGraphScout/1.0 (read-only monitoring; +https://agentgraph.co)"
_REQUEST_TIMEOUT = 15.0
_DELAY_BETWEEN_REQUESTS = 2.0  # seconds — be polite


@dataclass
class RedditThread:
    """A single Reddit thread found by the scout."""

    title: str
    url: str
    permalink: str
    subreddit: str
    score: int
    num_comments: int
    created_utc: float
    selftext_preview: str
    author: str
    keywords_matched: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "permalink": self.permalink,
            "subreddit": self.subreddit,
            "score": self.score,
            "num_comments": self.num_comments,
            "created_utc": self.created_utc,
            "selftext_preview": self.selftext_preview,
            "author": self.author,
            "keywords_matched": self.keywords_matched,
        }


async def _fetch_subreddit_json(
    client: httpx.AsyncClient,
    subreddit: str,
    sort: str = "hot",
    limit: int = 25,
) -> list[dict]:
    """Fetch posts from a subreddit via the public .json endpoint."""
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    try:
        resp = await client.get(
            url,
            params={"limit": limit, "raw_json": 1},
            headers={"User-Agent": _USER_AGENT},
        )
        if resp.status_code in (403, 429):
            logger.info(
                "Reddit returned %s for r/%s (datacenter IP likely blocked)",
                resp.status_code, subreddit,
            )
            return []
        resp.raise_for_status()
        data = resp.json()
        children = data.get("data", {}).get("children", [])
        return [child.get("data", {}) for child in children]
    except Exception:
        logger.exception("Failed to fetch r/%s", subreddit)
        return []


def _matches_keywords(
    text: str,
    keywords: list[str] | None = None,
) -> list[str]:
    """Return list of keywords that match in the given text."""
    kws = keywords or SCOUT_KEYWORDS
    text_lower = text.lower()
    return [kw for kw in kws if kw.lower() in text_lower]


async def scan_subreddits(
    subreddits: list[str] | None = None,
    keywords: list[str] | None = None,
    sort: str = "hot",
    limit_per_sub: int = 25,
    min_score: int = 0,
) -> list[RedditThread]:
    """Return cached Reddit threads without making any HTTP requests.

    Live scanning is disabled — the news-digest running on the Windows
    server handles Reddit monitoring separately and pushes data to Redis.
    AgentGraph should never make outbound HTTP requests to Reddit.

    Args:
        subreddits: Ignored (kept for API compatibility).
        keywords: Ignored (kept for API compatibility).
        sort: Ignored (kept for API compatibility).
        limit_per_sub: Ignored (kept for API compatibility).
        min_score: Minimum score threshold (still applied to cached data).

    Returns:
        Cached RedditThread objects sorted by score descending.
    """
    logger.debug("scan_subreddits: returning cached data only (live scanning disabled)")
    threads = await get_cached_threads()
    if min_score > 0:
        threads = [t for t in threads if t.score >= min_score]
    return threads


async def fetch_thread_detail(thread_url: str) -> dict | None:
    """Fetch full details for a specific Reddit thread via .json endpoint.

    Args:
        thread_url: Full Reddit URL (e.g. https://www.reddit.com/r/...)

    Returns:
        Dict with title, selftext, author, score, num_comments, subreddit,
        and top comments, or None on failure.
    """
    # Normalize URL and add .json suffix
    url = thread_url.rstrip("/")
    if not url.endswith(".json"):
        url = url + ".json"

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.get(
                url,
                params={"raw_json": 1},
                headers={"User-Agent": _USER_AGENT},
            )
            if resp.status_code == 429:
                logger.warning("Rate limited fetching thread detail")
                return None
            resp.raise_for_status()
            data = resp.json()

        # Reddit returns a list: [post_listing, comments_listing]
        if not isinstance(data, list) or len(data) < 1:
            return None

        post_data = (
            data[0].get("data", {}).get("children", [{}])[0].get("data", {})
        )

        # Extract top comments if available
        top_comments: list[dict] = []
        if len(data) > 1:
            comment_children = (
                data[1].get("data", {}).get("children", [])
            )
            for c in comment_children[:5]:
                cd = c.get("data", {})
                if cd.get("body"):
                    top_comments.append({
                        "author": cd.get("author", "[deleted]"),
                        "body": cd.get("body", "")[:500],
                        "score": cd.get("score", 0),
                    })

        return {
            "title": post_data.get("title", ""),
            "selftext": post_data.get("selftext", ""),
            "author": post_data.get("author", "[deleted]"),
            "score": post_data.get("score", 0),
            "num_comments": post_data.get("num_comments", 0),
            "subreddit": post_data.get("subreddit", ""),
            "created_utc": post_data.get("created_utc", 0),
            "url": thread_url,
            "top_comments": top_comments,
        }
    except Exception:
        logger.exception("Failed to fetch thread detail: %s", thread_url)
        return None


# Redis cache key for scout results
_CACHE_KEY = "ag:mktg:reddit_scout"
_CACHE_TTL = 86400  # 24 hours


async def _cache_threads(threads: list[RedditThread]) -> None:
    """Cache thread results in Redis for cross-machine access."""
    import json

    from src.redis_client import get_redis

    r = get_redis()
    data = json.dumps([t.to_dict() for t in threads[:20]])
    await r.set(_CACHE_KEY, data, ex=_CACHE_TTL)


async def get_cached_threads() -> list[RedditThread]:
    """Read cached Reddit threads from Redis.

    Use this on EC2 where Reddit blocks datacenter IPs.
    The Mac Mini runs scan_subreddits() which writes to this cache.
    """
    import json

    try:
        from src.redis_client import get_redis

        r = get_redis()
        data = await r.get(_CACHE_KEY)
        if not data:
            return []
        items = json.loads(data)
        return [
            RedditThread(
                title=t["title"],
                url=t["url"],
                permalink=t["permalink"],
                subreddit=t["subreddit"],
                score=t["score"],
                num_comments=t["num_comments"],
                created_utc=t["created_utc"],
                selftext_preview=t.get("selftext_preview", ""),
                author=t.get("author", "[deleted]"),
                keywords_matched=t.get("keywords_matched", []),
            )
            for t in items
        ]
    except Exception:
        logger.debug("Failed to read cached Reddit threads")
        return []
