"""HuggingFace model metadata fetcher for source imports."""
from __future__ import annotations

import logging

import httpx

from src.source_import.types import SourceImportResult

logger = logging.getLogger(__name__)


async def fetch_huggingface(model_id: str, url: str) -> SourceImportResult:
    """Fetch HuggingFace model metadata and return a SourceImportResult.

    Raises:
        ValueError: If the model is not found.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"https://huggingface.co/api/models/{model_id}"
        )
        if resp.status_code == 404:
            raise ValueError(f"HuggingFace model not found: {model_id}")
        model_data = resp.json() if resp.status_code == 200 else {}

    pipeline_tag = model_data.get("pipeline_tag", "")
    tags = model_data.get("tags", []) or []
    card_data = model_data.get("cardData", {}) or {}

    # Primary capability from pipeline tag
    capabilities: list[str] = []
    if pipeline_tag:
        capabilities.append(pipeline_tag)

    # Additional capabilities from tags (limit)
    for tag in tags[:10]:
        if tag not in capabilities:
            capabilities.append(tag)
    capabilities = capabilities[:20]

    # Bio from card data or model_id fallback
    bio = ""
    if isinstance(card_data, dict):
        bio = card_data.get("description", "") or card_data.get("summary", "") or ""
    if not bio:
        bio = f"HuggingFace model: {model_id}"

    community_signals = {
        "downloads": model_data.get("downloads", 0),
        "likes": model_data.get("likes", 0),
    }

    return SourceImportResult(
        source_type="huggingface",
        source_url=url,
        display_name=model_data.get("modelId", model_id),
        bio=bio,
        capabilities=capabilities,
        detected_framework=None,
        community_signals=community_signals,
        raw_metadata={
            "pipeline_tag": pipeline_tag,
            "library_name": model_data.get("library_name"),
            "tags": tags,
            "sha": model_data.get("sha"),
            "created_at": model_data.get("createdAt"),
            "last_modified": model_data.get("lastModified"),
        },
        avatar_url=None,
        version=model_data.get("sha"),
    )
