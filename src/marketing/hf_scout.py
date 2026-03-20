"""HuggingFace Scout — discover relevant discussions on trending model pages.

Scans the HuggingFace API for models tagged with agent/tool-use keywords,
then fetches their open discussions to find threads worth engaging with.
No auth required for read-only model/discussion listing.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://huggingface.co/api"
_TIMEOUT = 15.0
_DELAY = 1.5  # seconds between requests

# Models/repos to scan for discussions
SCOUT_REPOS = [
    # Popular agent/tool-use models
    "meta-llama/Llama-3.3-70B-Instruct",
    "mistralai/Mistral-Small-3.1-24B-Instruct-2503",
    "Qwen/Qwen3-8B",
    "microsoft/Phi-4-mini-instruct",
    "google/gemma-3-27b-it",
    "NousResearch/Hermes-3-Llama-3.1-8B",
    # Agent frameworks & tools
    "huggingface/smolagents",
    "langchain-ai/langchain",
]

# Search terms for discovering additional models
SCOUT_SEARCH_TERMS = [
    "agent",
    "tool-use",
    "function-calling",
    "multi-agent",
    "mcp",
]

# Keywords to filter discussions for relevance
RELEVANCE_KEYWORDS = [
    "agent", "trust", "identity", "verification", "security",
    "multi-agent", "tool use", "function call", "mcp",
    "orchestration", "safety", "permission", "credential",
    "interoperability", "protocol", "decentralized",
]


@dataclass
class HFDiscussion:
    """A HuggingFace discussion thread."""

    title: str
    url: str
    repo_id: str
    discussion_num: int
    author: str
    num_comments: int
    status: str  # open, closed
    created_at: str
    content_preview: str = ""
    keywords_matched: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "repo_id": self.repo_id,
            "discussion_num": self.discussion_num,
            "author": self.author,
            "num_comments": self.num_comments,
            "status": self.status,
            "created_at": self.created_at,
            "content_preview": self.content_preview,
            "keywords_matched": self.keywords_matched,
        }


def _matches_keywords(text: str) -> list[str]:
    """Return list of relevance keywords found in text."""
    text_lower = text.lower()
    return [kw for kw in RELEVANCE_KEYWORDS if kw in text_lower]


async def _fetch_discussions(
    client: httpx.AsyncClient,
    repo_id: str,
    limit: int = 10,
) -> list[dict]:
    """Fetch open discussions for a repo."""
    try:
        resp = await client.get(
            f"{_API_BASE}/models/{repo_id}/discussions",
            params={"limit": limit},
        )
        if resp.status_code in (403, 404, 429):
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("discussions", [])
    except Exception:
        logger.debug("Failed to fetch discussions for %s", repo_id)
        return []


async def _search_models(
    client: httpx.AsyncClient,
    query: str,
    limit: int = 5,
) -> list[str]:
    """Search for models by keyword, return repo IDs."""
    try:
        resp = await client.get(
            f"{_API_BASE}/models",
            params={
                "search": query,
                "sort": "likes",
                "direction": "-1",
                "limit": limit,
            },
        )
        if resp.status_code != 200:
            return []
        models = resp.json()
        return [m.get("id", "") for m in models if m.get("id")]
    except Exception:
        return []


async def scan_hf_discussions(
    repos: list[str] | None = None,
    include_search: bool = True,
    limit_per_repo: int = 10,
) -> list[HFDiscussion]:
    """Scan HuggingFace repos for relevant open discussions.

    Args:
        repos: List of repo IDs to scan (defaults to SCOUT_REPOS).
        include_search: Also search for trending models by keyword.
        limit_per_repo: Max discussions to fetch per repo.

    Returns:
        List of HFDiscussion objects sorted by relevance.
    """
    repo_ids = list(repos or SCOUT_REPOS)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        # Discover additional repos via search
        if include_search:
            for term in SCOUT_SEARCH_TERMS[:3]:
                found = await _search_models(client, term, limit=3)
                for rid in found:
                    if rid not in repo_ids:
                        repo_ids.append(rid)
                await asyncio.sleep(_DELAY)

        # Fetch discussions from all repos
        discussions: list[HFDiscussion] = []
        for i, repo_id in enumerate(repo_ids):
            if i > 0:
                await asyncio.sleep(_DELAY)

            raw = await _fetch_discussions(client, repo_id, limit_per_repo)
            for d in raw:
                title = d.get("title", "")
                status = d.get("status", "open")
                if status != "open":
                    continue

                content = f"{title} {d.get('content', '')}"
                matched = _matches_keywords(content)
                if not matched and repo_id not in (repos or SCOUT_REPOS):
                    continue  # Only show keyword-matched for discovered repos

                disc_num = d.get("num", 0)
                discussions.append(HFDiscussion(
                    title=title,
                    url=f"https://huggingface.co/{repo_id}/discussions/{disc_num}",
                    repo_id=repo_id,
                    discussion_num=disc_num,
                    author=d.get("author", {}).get("name", "unknown"),
                    num_comments=d.get("numComments", 0),
                    status=status,
                    created_at=d.get("createdAt", ""),
                    content_preview=(d.get("content", "") or "")[:300],
                    keywords_matched=matched,
                ))

    # Sort: keyword-matched first, then by comment count
    discussions.sort(
        key=lambda x: (len(x.keywords_matched) > 0, x.num_comments),
        reverse=True,
    )
    return discussions[:30]
