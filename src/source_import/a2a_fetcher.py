"""A2A (Agent-to-Agent) card fetcher for source imports."""
from __future__ import annotations

import logging

import httpx

from src.source_import.types import SourceImportResult

logger = logging.getLogger(__name__)


async def fetch_a2a(card_url: str) -> SourceImportResult:
    """Fetch an A2A agent card and return a SourceImportResult.

    The A2A spec defines agent cards at ``/.well-known/agent.json`` with
    fields: name, description, capabilities, url.

    Raises:
        ValueError: If the card cannot be fetched or is invalid.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(card_url)
        if resp.status_code != 200:
            raise ValueError(
                f"Failed to fetch A2A agent card: HTTP {resp.status_code}"
            )

    try:
        data = resp.json()
    except Exception:
        raise ValueError("A2A agent card URL did not return valid JSON")

    if not isinstance(data, dict):
        raise ValueError("A2A agent card must be a JSON object")

    name = data.get("name", "") or "Unknown Agent"
    description = data.get("description", "") or ""

    # Capabilities can be a list of strings or list of dicts with 'name'
    raw_caps = data.get("capabilities", [])
    capabilities: list[str] = []
    if isinstance(raw_caps, list):
        for cap in raw_caps:
            if isinstance(cap, str):
                capabilities.append(cap)
            elif isinstance(cap, dict):
                cap_name = cap.get("name", "")
                if cap_name:
                    capabilities.append(cap_name)
    capabilities = capabilities[:50]

    return SourceImportResult(
        source_type="a2a_card",
        source_url=card_url,
        display_name=name,
        bio=description,
        capabilities=capabilities,
        detected_framework="a2a",
        community_signals={},
        raw_metadata=data,
        avatar_url=data.get("avatar_url") or data.get("iconUrl"),
        version=data.get("version"),
    )
