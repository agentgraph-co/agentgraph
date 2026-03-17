"""npm package metadata fetcher for source imports."""
from __future__ import annotations

import logging

import httpx

from src.source_import.types import SourceImportResult

logger = logging.getLogger(__name__)

_FRAMEWORK_PATTERNS: list[tuple[str, str]] = [
    ("langchain", "langchain"),
    ("@modelcontextprotocol", "mcp"),
    ("mcp", "mcp"),
    ("openai", "native"),
    ("crewai", "crewai"),
    ("autogen", "autogen"),
]


async def fetch_npm(package_name: str, url: str) -> SourceImportResult:
    """Fetch npm package metadata and return a SourceImportResult.

    Raises:
        ValueError: If the package is not found.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        # Registry metadata
        reg_resp = await client.get(
            f"https://registry.npmjs.org/{package_name}"
        )
        if reg_resp.status_code == 404:
            raise ValueError(f"npm package not found: {package_name}")
        package_data = reg_resp.json() if reg_resp.status_code == 200 else {}

        # Download counts
        downloads_monthly = 0
        try:
            dl_resp = await client.get(
                f"https://api.npmjs.org/downloads/point/last-month/{package_name}"
            )
            if dl_resp.status_code == 200:
                downloads_monthly = dl_resp.json().get("downloads", 0)
        except Exception:
            logger.debug("Failed to fetch npm download stats for %s", package_name)

    # Extract info
    latest_tag = package_data.get("dist-tags", {}).get("latest")
    versions = package_data.get("versions", {})
    latest_data = versions.get(latest_tag, {}) if latest_tag else {}

    keywords = package_data.get("keywords", []) or []
    description = package_data.get("description", "") or ""
    maintainers = package_data.get("maintainers", [])

    # Detect framework from latest version dependencies
    all_deps = {
        **latest_data.get("dependencies", {}),
        **latest_data.get("devDependencies", {}),
    }
    detected_framework = _detect_framework(all_deps)

    community_signals = {
        "downloads_monthly": downloads_monthly,
        "versions": len(versions),
        "maintainers": len(maintainers),
    }

    return SourceImportResult(
        source_type="npm",
        source_url=url,
        display_name=package_data.get("name", package_name),
        bio=description,
        capabilities=keywords[:20],
        detected_framework=detected_framework,
        community_signals=community_signals,
        raw_metadata={
            "latest_version": latest_tag,
            "license": latest_data.get("license"),
            "homepage": package_data.get("homepage"),
            "repository": package_data.get("repository"),
        },
        version=latest_tag,
    )


def _detect_framework(deps: dict) -> str | None:
    """Detect framework from npm dependency names."""
    if not deps:
        return None
    dep_str = " ".join(deps.keys()).lower()
    for pattern, framework in _FRAMEWORK_PATTERNS:
        if pattern in dep_str:
            return framework
    return None
