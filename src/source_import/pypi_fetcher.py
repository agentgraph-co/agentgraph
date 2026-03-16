"""PyPI package metadata fetcher for source imports."""
from __future__ import annotations

import logging

import httpx

from src.source_import.types import SourceImportResult

logger = logging.getLogger(__name__)

_FRAMEWORK_PATTERNS: list[tuple[str, str]] = [
    ("langchain", "langchain"),
    ("crewai", "crewai"),
    ("autogen", "autogen"),
    ("mcp", "mcp"),
    ("openai", "openai"),
]


async def fetch_pypi(package_name: str, url: str) -> SourceImportResult:
    """Fetch PyPI package metadata and return a SourceImportResult.

    Raises:
        ValueError: If the package is not found.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"https://pypi.org/pypi/{package_name}/json")
        if resp.status_code == 404:
            raise ValueError(f"PyPI package not found: {package_name}")
        package_data = resp.json() if resp.status_code == 200 else {}

    info = package_data.get("info", {})
    releases = package_data.get("releases", {})
    classifiers = info.get("classifiers", [])
    requires_dist = info.get("requires_dist", []) or []

    # Use classifiers as capability hints
    capabilities = _classifiers_to_capabilities(classifiers)

    # Detect framework from requires_dist
    detected_framework = _detect_framework(requires_dist)

    community_signals = {
        "release_count": len(releases),
        "classifiers": len(classifiers),
    }

    return SourceImportResult(
        source_type="pypi",
        source_url=url,
        display_name=info.get("name", package_name),
        bio=info.get("summary", "") or "",
        capabilities=capabilities,
        detected_framework=detected_framework,
        community_signals=community_signals,
        raw_metadata={
            "author": info.get("author"),
            "author_email": info.get("author_email"),
            "license": info.get("license"),
            "home_page": info.get("home_page"),
            "project_urls": info.get("project_urls"),
            "python_requires": info.get("requires_python"),
        },
        version=info.get("version"),
    )


def _classifiers_to_capabilities(classifiers: list[str]) -> list[str]:
    """Extract meaningful capability hints from PyPI classifiers."""
    capabilities: list[str] = []
    for c in classifiers:
        # Topic :: ... classifiers are most relevant
        if c.startswith("Topic ::"):
            parts = c.split(" :: ")
            if len(parts) >= 3:
                capabilities.append(parts[-1])
    return capabilities[:20]


def _detect_framework(requires_dist: list[str]) -> str | None:
    """Detect framework from requires_dist entries."""
    if not requires_dist:
        return None
    joined = " ".join(requires_dist).lower()
    for pattern, framework in _FRAMEWORK_PATTERNS:
        if pattern in joined:
            return framework
    return None
