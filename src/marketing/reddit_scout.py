"""Reddit Scout — read-only monitoring via public .json endpoints.

Scrapes public Reddit feeds without API keys (Reddit killed
self-service API access Nov 2025). Uses the /<subreddit>.json
public endpoint which requires no authentication.

Returns structured thread data filtered by configurable keywords.
"""
from __future__ import annotations

import asyncio
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
    url = f"https://old.reddit.com/r/{subreddit}/{sort}.json"
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
    """Scan subreddits for threads matching keywords.

    Args:
        subreddits: List of subreddit names (defaults to SCOUT_SUBREDDITS).
        keywords: Keywords to filter by (defaults to SCOUT_KEYWORDS).
        sort: Sort order — hot, new, top, rising.
        limit_per_sub: Max posts to fetch per subreddit.
        min_score: Minimum score threshold.

    Returns:
        List of RedditThread objects sorted by score descending.
    """
    subs = subreddits or SCOUT_SUBREDDITS
    kws = keywords or SCOUT_KEYWORDS
    threads: list[RedditThread] = []

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        for i, sub in enumerate(subs):
            if i > 0:
                await asyncio.sleep(_DELAY_BETWEEN_REQUESTS)

            posts = await _fetch_subreddit_json(
                client, sub, sort=sort, limit=limit_per_sub,
            )

            for post in posts:
                title = post.get("title", "")
                selftext = post.get("selftext", "")
                combined = f"{title} {selftext}"

                matched = _matches_keywords(combined, kws)
                if not matched:
                    continue

                score = post.get("score", 0)
                if score < min_score:
                    continue

                permalink = post.get("permalink", "")
                threads.append(RedditThread(
                    title=title,
                    url=f"https://old.reddit.com{permalink}",
                    permalink=permalink,
                    subreddit=post.get("subreddit", sub),
                    score=score,
                    num_comments=post.get("num_comments", 0),
                    created_utc=post.get("created_utc", 0),
                    selftext_preview=selftext[:300] if selftext else "",
                    author=post.get("author", "[deleted]"),
                    keywords_matched=matched,
                ))

    # Sort by score descending
    threads.sort(key=lambda t: t.score, reverse=True)
    return threads


async def fetch_thread_detail(thread_url: str) -> dict | None:
    """Fetch full details for a specific Reddit thread via .json endpoint.

    Args:
        thread_url: Full Reddit URL (e.g. https://old.reddit.com/r/...)

    Returns:
        Dict with title, selftext, author, score, num_comments, subreddit,
        and top comments, or None on failure.
    """
    # Normalize URL: convert www.reddit.com to old.reddit.com, add .json
    url = thread_url.replace("https://www.reddit.com", "https://old.reddit.com")
    url = url.rstrip("/")
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
