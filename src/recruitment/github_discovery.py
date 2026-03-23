"""GitHub repo discovery pipeline for operator recruitment.

Searches GitHub for MCP servers, AI agent repos, and AI tool repos,
then stores them as recruitment prospects for outreach.
"""
from __future__ import annotations

import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models import RecruitmentProspect

logger = logging.getLogger(__name__)

_TIMEOUT = 15  # seconds

# Search queries with minimum star thresholds and template keys
_SEARCH_QUERIES: list[tuple[str, int, str]] = [
    ("topic:mcp-server", 10, "mcp_server"),
    ("topic:mcp topic:server", 10, "mcp_server"),
    ('"model context protocol" in:readme', 10, "mcp_server"),
    ("topic:ai-agent", 50, "ai_agent"),
    ("topic:autonomous-agent", 50, "ai_agent"),
    ("topic:langchain topic:agent", 30, "ai_agent"),
    ("topic:crewai", 20, "ai_agent"),
    ("topic:autogen", 20, "ai_agent"),
    ("topic:ai-tool", 20, "ai_tool"),
]

# Repos to skip (our own, forks of huge projects, etc.)
_SKIP_OWNERS = {"agentgraph-co", "agentgraph"}


def _github_headers() -> dict[str, str]:
    """Build GitHub API headers with optional auth."""
    headers = {"Accept": "application/vnd.github+json"}
    token = settings.github_outreach_token or settings.github_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _detect_framework(topics: list[str], description: str) -> str | None:
    """Detect agent framework from repo topics and description."""
    text = " ".join(topics) + " " + (description or "")
    text_lower = text.lower()
    if "mcp" in text_lower or "model context protocol" in text_lower:
        return "mcp"
    if "langchain" in text_lower:
        return "langchain"
    if "crewai" in text_lower:
        return "crewai"
    if "autogen" in text_lower:
        return "autogen"
    if "semantic-kernel" in text_lower:
        return "semantic_kernel"
    return None


async def _search_github(
    query: str, min_stars: int,
) -> list[dict]:
    """Search GitHub for repos matching query with at least min_stars."""
    results = []
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        url = "https://api.github.com/search/repositories"
        params = {
            "q": f"{query} stars:>={min_stars}",
            "sort": "stars",
            "order": "desc",
            "per_page": 100,
        }
        resp = await client.get(url, headers=_github_headers(), params=params)

        if resp.status_code == 403:
            logger.warning("GitHub rate limit hit during discovery")
            return results
        if resp.status_code != 200:
            logger.warning(
                "GitHub search returned %d for query: %s",
                resp.status_code, query,
            )
            return results

        data = resp.json()
        for item in data.get("items", []):
            owner = item.get("owner", {}).get("login", "")
            if owner.lower() in _SKIP_OWNERS:
                continue
            if item.get("fork", False):
                continue
            results.append(item)

    return results


async def run_discovery_cycle(db: AsyncSession) -> int:
    """Run one discovery cycle, storing new prospects. Returns count added."""
    added = 0

    for query, min_stars, template_key in _SEARCH_QUERIES:
        try:
            repos = await _search_github(query, min_stars)
        except Exception:
            logger.exception("Discovery search failed: %s", query)
            continue

        for repo in repos:
            full_name = repo["full_name"]
            owner = repo["owner"]["login"]

            # Check if already tracked
            existing = await db.scalar(
                select(RecruitmentProspect).where(
                    RecruitmentProspect.platform == "github",
                    RecruitmentProspect.platform_id == full_name,
                )
            )
            if existing:
                continue

            topics = repo.get("topics", [])
            framework = _detect_framework(
                topics, repo.get("description", "") or "",
            )

            prospect = RecruitmentProspect(
                platform="github",
                platform_id=full_name,
                owner_login=owner,
                repo_name=repo["name"],
                stars=repo.get("stargazers_count", 0),
                description=(repo.get("description") or "")[:2000],
                framework_detected=framework or template_key.replace("_", " "),
                status="discovered",
            )
            db.add(prospect)
            added += 1

    if added > 0:
        await db.flush()

    return added
