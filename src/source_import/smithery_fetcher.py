"""Smithery MCP server registry fetcher for source imports.

Smithery (https://smithery.ai) is a third-party MCP server registry —
complementary to the official MCP Registry, Glama, and mcp.so. Added to
the Q3 2026 scan corpus per docs/internal/execution-plan-rebalance.md
week of Jun 22 (#111).

Scaffold: URL parsing + fetch contract that matches huggingface_fetcher.
Full crawl + per-server scan integration land with the Q3 scan run.

API reference (as of 2026-05): Smithery exposes per-server JSON metadata
at https://smithery.ai/server/<server-id> with a JSON-LD <script> tag in
the page head; their REST API at https://api.smithery.ai/v1/servers
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
#   https://smithery.ai/server/<server-id>
#   https://smithery.ai/server/<owner>/<server-id>
_SMITHERY_URL_RE = re.compile(
    r"https?://smithery\.ai/server/(?P<path>[^?#]+)",
)

_REQUEST_TIMEOUT = 15.0


def parse_smithery_url(url: str) -> str:
    """Extract the server identifier from a Smithery server URL.

    Raises:
        SourceParseError: if the URL does not match the expected shape.
    """
    match = _SMITHERY_URL_RE.search(url)
    if not match:
        raise SourceParseError(
            f"Cannot parse Smithery server ID from URL: {url}",
        )
    return match.group("path").rstrip("/")


async def fetch_smithery(server_id: str, url: str) -> SourceImportResult:
    """Fetch Smithery server metadata and return a SourceImportResult.

    Args:
        server_id: identifier returned by ``parse_smithery_url``.
        url: original URL provided by the caller (preserved as ``source_url``).

    Raises:
        SourceFetchError: if Smithery returns non-200 or the response is
            unexpectedly empty.
    """
    api_url = f"https://api.smithery.ai/v1/servers/{server_id}"
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.get(api_url, headers={"Accept": "application/json"})
    except httpx.RequestError as exc:
        raise SourceFetchError(f"Smithery fetch failed: {exc}") from exc

    if resp.status_code != 200:
        raise SourceFetchError(
            f"Smithery returned HTTP {resp.status_code} for {server_id}",
        )

    data = resp.json()
    display_name = data.get("name") or data.get("displayName") or server_id
    bio = data.get("description") or ""
    capabilities = data.get("tools") or []
    if isinstance(capabilities, list):
        capability_names = [
            t.get("name", "") if isinstance(t, dict) else str(t)
            for t in capabilities
        ]
    else:
        capability_names = []

    return SourceImportResult(
        source_type="smithery",
        source_url=url,
        display_name=display_name,
        bio=bio,
        capabilities=capability_names,
        detected_framework="mcp",
        community_signals={
            "smithery_downloads": data.get("downloads", 0),
            "smithery_stars": data.get("stars", 0),
        },
        raw_metadata=data,
        readme_excerpt=(data.get("readme") or "")[:2000],
    )
