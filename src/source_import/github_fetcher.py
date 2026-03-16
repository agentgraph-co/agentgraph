"""GitHub repository metadata fetcher for source imports."""
from __future__ import annotations

import logging
import re

import httpx

from src.source_import.types import SourceImportResult

logger = logging.getLogger(__name__)

# Framework detection: dependency string → framework name
_FRAMEWORK_PATTERNS: list[tuple[str, str]] = [
    ("langchain", "langchain"),
    ("crewai", "crewai"),
    ("autogen", "autogen"),
    ("@modelcontextprotocol", "mcp"),
    ("mcp", "mcp"),
    ("openai", "openai"),
]


async def fetch_github(owner: str, repo: str, url: str) -> SourceImportResult:
    """Fetch GitHub repo metadata and return a SourceImportResult.

    Raises:
        ValueError: If the repository is not found.
    """
    api_base = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {"Accept": "application/vnd.github+json"}

    async with httpx.AsyncClient(timeout=10) as client:
        # Fetch repo metadata
        repo_resp = await client.get(api_base, headers=headers)
        if repo_resp.status_code == 404:
            raise ValueError(f"GitHub repository not found: {owner}/{repo}")
        repo_data = repo_resp.json() if repo_resp.status_code == 200 else {}

        # Fetch README
        readme_text = ""
        readme_resp = await client.get(
            f"{api_base}/readme",
            headers={"Accept": "application/vnd.github.raw"},
        )
        if readme_resp.status_code == 200:
            readme_text = readme_resp.text

        # Fetch dependency files for framework detection
        dep_contents = await _fetch_dependency_files(client, api_base, headers)

    # Extract capabilities from README
    capabilities = _extract_capabilities(readme_text)

    # Detect framework from dependencies
    detected_framework = _detect_framework(dep_contents)

    # Build community signals
    owner_data = repo_data.get("owner", {})
    community_signals = {
        "stars": repo_data.get("stargazers_count", 0),
        "forks": repo_data.get("forks_count", 0),
        "open_issues": repo_data.get("open_issues_count", 0),
        "language": repo_data.get("language"),
        "topics": repo_data.get("topics", []),
    }

    return SourceImportResult(
        source_type="github",
        source_url=url,
        display_name=repo_data.get("full_name", f"{owner}/{repo}"),
        bio=repo_data.get("description", "") or "",
        capabilities=capabilities,
        detected_framework=detected_framework,
        community_signals=community_signals,
        raw_metadata={
            "owner": owner,
            "repo": repo,
            "default_branch": repo_data.get("default_branch"),
            "license": (repo_data.get("license") or {}).get("spdx_id"),
            "created_at": repo_data.get("created_at"),
            "updated_at": repo_data.get("updated_at"),
        },
        readme_excerpt=readme_text[:2000],
        avatar_url=owner_data.get("avatar_url"),
        version=None,
    )


async def _fetch_dependency_files(
    client: httpx.AsyncClient,
    api_base: str,
    headers: dict,
) -> str:
    """Fetch common dependency files and return their concatenated contents."""
    dep_files = ["requirements.txt", "pyproject.toml", "package.json"]
    contents_parts: list[str] = []

    for fname in dep_files:
        resp = await client.get(
            f"{api_base}/contents/{fname}",
            headers={"Accept": "application/vnd.github.raw"},
        )
        if resp.status_code == 200:
            contents_parts.append(resp.text)

    return "\n".join(contents_parts)


def _extract_capabilities(readme: str) -> list[str]:
    """Extract capability bullet points from README sections."""
    capabilities: list[str] = []
    if not readme:
        return capabilities

    # Look for Features/Capabilities sections
    section_pattern = re.compile(
        r"##\s*(?:Features|Capabilities)\s*\n(.*?)(?=\n##|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    match = section_pattern.search(readme)
    if match:
        section_text = match.group(1)
        # Extract bullet items
        for line in section_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                cap = stripped[2:].strip()
                if cap:
                    capabilities.append(cap)

    return capabilities[:20]  # cap at 20


def _detect_framework(dep_contents: str) -> str | None:
    """Detect the primary agent framework from dependency file contents."""
    if not dep_contents:
        return None
    lower = dep_contents.lower()
    for pattern, framework in _FRAMEWORK_PATTERNS:
        if pattern in lower:
            return framework
    return None
