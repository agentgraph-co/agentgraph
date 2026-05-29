"""PulseMCP server directory fetcher for source imports.

PulseMCP (https://www.pulsemcp.com) is another third-party MCP server
directory. Added to the Q3 2026 scan corpus per
docs/internal/execution-plan-rebalance.md week of Jun 22 (#111).

Scaffold: URL parsing + fetch contract matching the huggingface_fetcher
pattern. Full crawl + per-server scan integration land with the Q3 scan
run.

API reference: PulseMCP serves per-server pages at
https://www.pulsemcp.com/servers/<slug> with structured data in <meta>
tags + JSON-LD; their public API at https://api.pulsemcp.com/v0beta/servers
returns paginated server lists (no auth required for reads).
"""
from __future__ import annotations

import logging
import re

import httpx

from src.source_import.errors import SourceFetchError, SourceParseError
from src.source_import.types import SourceImportResult

logger = logging.getLogger(__name__)

# URL forms:
#   https://www.pulsemcp.com/servers/<slug>
#   https://pulsemcp.com/servers/<slug>
_PULSEMCP_URL_RE = re.compile(
    r"https?://(?:www\.)?pulsemcp\.com/servers/(?P<slug>[^?#/]+)",
)

_REQUEST_TIMEOUT = 15.0


def parse_pulsemcp_url(url: str) -> str:
    """Extract the server slug from a PulseMCP server URL.

    Raises:
        SourceParseError: if the URL does not match the expected shape.
    """
    match = _PULSEMCP_URL_RE.search(url)
    if not match:
        raise SourceParseError(
            f"Cannot parse PulseMCP server slug from URL: {url}",
        )
    return match.group("slug")


async def fetch_pulsemcp(slug: str, url: str) -> SourceImportResult:
    """Fetch PulseMCP server metadata and return a SourceImportResult.

    Args:
        slug: identifier returned by ``parse_pulsemcp_url``.
        url: original URL provided by the caller (preserved as ``source_url``).

    Raises:
        SourceFetchError: if PulseMCP returns non-200 or the response is
            unexpectedly empty.
    """
    api_url = f"https://api.pulsemcp.com/v0beta/servers/{slug}"
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.get(api_url, headers={"Accept": "application/json"})
    except httpx.RequestError as exc:
        raise SourceFetchError(f"PulseMCP fetch failed: {exc}") from exc

    if resp.status_code != 200:
        raise SourceFetchError(
            f"PulseMCP returned HTTP {resp.status_code} for {slug}",
        )

    data = resp.json()
    server = data.get("server", data)  # API may wrap or not
    display_name = server.get("name") or slug
    bio = server.get("short_description") or server.get("description") or ""

    tools = server.get("tools") or []
    capability_names = [
        t.get("name", "") if isinstance(t, dict) else str(t)
        for t in tools
    ]

    return SourceImportResult(
        source_type="pulsemcp",
        source_url=url,
        display_name=display_name,
        bio=bio,
        capabilities=capability_names,
        detected_framework="mcp",
        community_signals={
            "pulsemcp_stars": server.get("github_stars", 0),
            "pulsemcp_listed_at": server.get("listed_at"),
        },
        raw_metadata=server,
        readme_excerpt=(server.get("readme") or "")[:2000],
    )
