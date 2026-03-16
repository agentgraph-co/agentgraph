"""MCP manifest fetcher for source imports."""
from __future__ import annotations

import logging

import httpx

from src.source_import.types import SourceImportResult

logger = logging.getLogger(__name__)


async def fetch_mcp(manifest_url: str) -> SourceImportResult:
    """Fetch an MCP manifest JSON and return a SourceImportResult.

    Expects the manifest to contain a ``tools`` array where each item
    has at least ``name`` and optionally ``description``.

    Raises:
        ValueError: If the manifest cannot be fetched or is invalid.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(manifest_url)
        if resp.status_code != 200:
            raise ValueError(
                f"Failed to fetch MCP manifest: HTTP {resp.status_code}"
            )

    try:
        data = resp.json()
    except Exception:
        raise ValueError("MCP manifest URL did not return valid JSON")

    if not isinstance(data, dict):
        raise ValueError("MCP manifest must be a JSON object")

    tools = data.get("tools")
    if not isinstance(tools, list):
        raise ValueError("MCP manifest must contain a 'tools' array")

    # Each tool name+description → capability
    capabilities: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name", "")
        desc = tool.get("description", "")
        cap = f"{name}: {desc}".strip(": ") if desc else name
        if cap:
            capabilities.append(cap)
    capabilities = capabilities[:50]

    display_name = data.get("name", "") or data.get("title", "") or "MCP Server"
    bio = data.get("description", "") or ""

    return SourceImportResult(
        source_type="mcp_manifest",
        source_url=manifest_url,
        display_name=display_name,
        bio=bio,
        capabilities=capabilities,
        detected_framework="mcp",
        community_signals={},
        raw_metadata=data,
        version=data.get("version"),
    )
