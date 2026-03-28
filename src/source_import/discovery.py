"""Cross-source discovery engine.

Given a primary SourceImportResult, discovers the same project
across other registries (npm, PyPI, Docker Hub, GitHub, HuggingFace).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re

import httpx

from src import cache
from src.source_import.types import DiscoveredSource, SourceImportResult

logger = logging.getLogger(__name__)

_DISCOVERY_CACHE_TTL = 3600  # 1 hour
_CHECK_TIMEOUT = 5  # seconds per individual check


async def discover_related_sources(
    primary: SourceImportResult,
) -> list[DiscoveredSource]:
    """Discover related sources across registries for a primary import result.

    All existence checks run in parallel with per-check timeouts.
    Returns partial results — individual check failures are logged and skipped.
    """
    cache_key = _cache_key(primary.source_url)
    cached = await cache.get(cache_key)
    if cached is not None:
        return [DiscoveredSource(**item) for item in cached]

    checks: list[asyncio.Task] = []  # type: ignore[type-arg]
    source_type = primary.source_type.lower()

    if source_type == "github":
        checks.extend(_github_discovery_checks(primary))
    elif source_type == "npm":
        checks.extend(_npm_discovery_checks(primary))
    elif source_type == "pypi":
        checks.extend(_pypi_discovery_checks(primary))
    elif source_type == "huggingface":
        checks.extend(_huggingface_discovery_checks(primary))

    if not checks:
        return []

    results = await asyncio.gather(*checks, return_exceptions=True)
    discovered: list[DiscoveredSource] = []
    for result in results:
        if isinstance(result, DiscoveredSource):
            discovered.append(result)
        elif isinstance(result, Exception):
            logger.debug("Discovery check failed: %s", result)

    # Cache results
    await cache.set(
        cache_key,
        [
            {
                "provider": d.provider,
                "identifier": d.identifier,
                "source_url": d.source_url,
                "discovery_method": d.discovery_method,
                "community_signals": d.community_signals,
            }
            for d in discovered
        ],
        ttl=_DISCOVERY_CACHE_TTL,
    )

    return discovered


def _cache_key(url: str) -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
    return f"source:discovery:{digest}"


# ---------------------------------------------------------------------------
# GitHub → npm, PyPI, Docker
# ---------------------------------------------------------------------------


def _github_discovery_checks(
    primary: SourceImportResult,
) -> list[asyncio.Task]:  # type: ignore[type-arg]
    """Create discovery check tasks for a GitHub source."""
    meta = primary.raw_metadata or {}
    owner = meta.get("owner", "")
    repo = meta.get("repo", "")
    dep_files = meta.get("dep_files", {})
    tasks: list[asyncio.Task] = []  # type: ignore[type-arg]

    # GitHub → npm: parse package.json for name field
    pkg_json = dep_files.get("package.json", "")
    if pkg_json:
        tasks.append(asyncio.create_task(
            _check_npm_from_package_json(pkg_json)
        ))

    # GitHub → PyPI: parse pyproject.toml or setup.py for name
    pyproject = dep_files.get("pyproject.toml", "")
    if pyproject:
        tasks.append(asyncio.create_task(
            _check_pypi_from_pyproject(pyproject)
        ))
    else:
        setup_py = dep_files.get("setup.py", "")
        if setup_py:
            tasks.append(asyncio.create_task(
                _check_pypi_from_setup_py(setup_py)
            ))

    # GitHub → Docker: check if hub.docker.com/r/{owner}/{repo} exists
    if owner and repo:
        tasks.append(asyncio.create_task(
            _check_docker_exists(owner, repo, f"github repo {owner}/{repo}")
        ))

    return tasks


async def _check_npm_from_package_json(content: str) -> DiscoveredSource:
    """Parse package.json content and verify the package exists on npm."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"Invalid package.json: {exc}") from exc

    name = data.get("name")
    if not name or not isinstance(name, str):
        raise ValueError("No 'name' field in package.json")

    async with httpx.AsyncClient(timeout=_CHECK_TIMEOUT) as client:
        resp = await client.head(f"https://registry.npmjs.org/{name}")
        if resp.status_code != 200:
            raise ValueError(f"npm package {name} not found")

        # Fetch signals
        signals: dict = {}
        try:
            dl_resp = await client.get(
                f"https://api.npmjs.org/downloads/point/last-month/{name}"
            )
            if dl_resp.status_code == 200:
                signals["downloads_monthly"] = dl_resp.json().get("downloads", 0)
        except Exception:
            pass

    return DiscoveredSource(
        provider="npm",
        identifier=name,
        source_url=f"https://www.npmjs.com/package/{name}",
        discovery_method="package.json name field",
        community_signals=signals,
    )


async def _check_pypi_from_pyproject(content: str) -> DiscoveredSource:
    """Parse pyproject.toml for [project] name and verify on PyPI."""
    # Simple regex parse — avoids toml dependency
    match = re.search(
        r'^\[project\]\s*\n(?:.*\n)*?name\s*=\s*["\']([^"\']+)["\']',
        content,
        re.MULTILINE,
    )
    if not match:
        raise ValueError("No [project] name in pyproject.toml")

    name = match.group(1)
    return await _verify_pypi_package(name, "pyproject.toml [project] name")


async def _check_pypi_from_setup_py(content: str) -> DiscoveredSource:
    """Parse setup.py for name= and verify on PyPI."""
    match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        raise ValueError("No name= in setup.py")

    name = match.group(1)
    return await _verify_pypi_package(name, "setup.py name argument")


async def _verify_pypi_package(
    name: str, method: str
) -> DiscoveredSource:
    """Check if a PyPI package exists and fetch basic signals."""
    async with httpx.AsyncClient(timeout=_CHECK_TIMEOUT) as client:
        resp = await client.get(f"https://pypi.org/pypi/{name}/json")
        if resp.status_code != 200:
            raise ValueError(f"PyPI package {name} not found")

        signals: dict = {}
        try:
            data = resp.json()
            info = data.get("info", {})
            releases = data.get("releases", {})
            signals["release_count"] = len(releases)
            signals["author"] = info.get("author", "")
        except Exception:
            pass

    return DiscoveredSource(
        provider="pypi",
        identifier=name,
        source_url=f"https://pypi.org/project/{name}/",
        discovery_method=method,
        community_signals=signals,
    )


async def _check_docker_exists(
    namespace: str, repo: str, method_context: str
) -> DiscoveredSource:
    """Check if a Docker Hub repository exists."""
    async with httpx.AsyncClient(timeout=_CHECK_TIMEOUT) as client:
        resp = await client.get(
            f"https://hub.docker.com/v2/repositories/{namespace}/{repo}"
        )
        if resp.status_code != 200:
            raise ValueError(f"Docker repo {namespace}/{repo} not found")

        signals: dict = {}
        try:
            data = resp.json()
            signals["pulls"] = data.get("pull_count", 0)
            signals["stars"] = data.get("star_count", 0)
        except Exception:
            pass

    return DiscoveredSource(
        provider="docker",
        identifier=f"{namespace}/{repo}",
        source_url=f"https://hub.docker.com/r/{namespace}/{repo}",
        discovery_method=method_context,
        community_signals=signals,
    )


# ---------------------------------------------------------------------------
# npm → GitHub
# ---------------------------------------------------------------------------


def _npm_discovery_checks(
    primary: SourceImportResult,
) -> list[asyncio.Task]:  # type: ignore[type-arg]
    """Create discovery check tasks for an npm source."""
    meta = primary.raw_metadata or {}
    repository = meta.get("repository")
    tasks: list[asyncio.Task] = []  # type: ignore[type-arg]

    if repository:
        repo_url = repository.get("url", "") if isinstance(repository, dict) else str(repository)
        tasks.append(asyncio.create_task(
            _check_github_from_url(repo_url, "npm repository.url")
        ))

    return tasks


# ---------------------------------------------------------------------------
# PyPI → GitHub
# ---------------------------------------------------------------------------


def _pypi_discovery_checks(
    primary: SourceImportResult,
) -> list[asyncio.Task]:  # type: ignore[type-arg]
    """Create discovery check tasks for a PyPI source."""
    meta = primary.raw_metadata or {}
    tasks: list[asyncio.Task] = []  # type: ignore[type-arg]

    # project_urls may contain Source, Repository, GitHub links
    project_urls = meta.get("project_urls") or {}
    for key in ("Source", "Repository", "GitHub", "Homepage", "Source Code"):
        url = project_urls.get(key, "")
        if "github.com" in url:
            tasks.append(asyncio.create_task(
                _check_github_from_url(url, f"PyPI project_urls[{key}]")
            ))
            break  # Only need one

    return tasks


# ---------------------------------------------------------------------------
# HuggingFace → GitHub
# ---------------------------------------------------------------------------


def _huggingface_discovery_checks(
    primary: SourceImportResult,
) -> list[asyncio.Task]:  # type: ignore[type-arg]
    """Create discovery check tasks for a HuggingFace source."""
    tasks: list[asyncio.Task] = []  # type: ignore[type-arg]

    # Scan readme for GitHub URLs
    readme = primary.readme_excerpt or ""
    gh_match = re.search(r"https?://github\.com/([^/\s]+)/([^/\s#?.]+)", readme)
    if gh_match:
        url = f"https://github.com/{gh_match.group(1)}/{gh_match.group(2)}"
        tasks.append(asyncio.create_task(
            _check_github_from_url(url, "HuggingFace README github.com link")
        ))

    return tasks


# ---------------------------------------------------------------------------
# Shared: GitHub existence check
# ---------------------------------------------------------------------------


async def _check_github_from_url(
    raw_url: str, method: str
) -> DiscoveredSource:
    """Verify a GitHub repo URL resolves and fetch basic signals."""
    # Normalize git:// and git+https:// URLs
    url = raw_url.replace("git+https://", "https://").replace("git://", "https://")
    url = re.sub(r"\.git$", "", url)

    match = re.search(r"github\.com/([^/]+)/([^/\s#?]+)", url)
    if not match:
        raise ValueError(f"Cannot extract GitHub owner/repo from {raw_url}")

    owner, repo = match.group(1), match.group(2)

    async with httpx.AsyncClient(timeout=_CHECK_TIMEOUT) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers={"Accept": "application/vnd.github+json"},
        )
        if resp.status_code != 200:
            raise ValueError(f"GitHub repo {owner}/{repo} not found")

        signals: dict = {}
        try:
            data = resp.json()
            signals["stars"] = data.get("stargazers_count", 0)
            signals["forks"] = data.get("forks_count", 0)
        except Exception:
            pass

    return DiscoveredSource(
        provider="github",
        identifier=f"{owner}/{repo}",
        source_url=f"https://github.com/{owner}/{repo}",
        discovery_method=method,
        community_signals=signals,
    )
