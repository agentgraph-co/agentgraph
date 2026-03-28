"""Tests for cross-source discovery engine."""
from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.source_import.discovery import discover_related_sources
from src.source_import.types import DiscoveredSource, SourceImportResult


def _github_result(
    *,
    owner: str = "myorg",
    repo: str = "myrepo",
    dep_files: dict | None = None,
) -> SourceImportResult:
    """Build a GitHub SourceImportResult for testing."""
    return SourceImportResult(
        source_type="github",
        source_url=f"https://github.com/{owner}/{repo}",
        display_name=f"{owner}/{repo}",
        bio="A test repo",
        raw_metadata={
            "owner": owner,
            "repo": repo,
            "dep_files": dep_files or {},
        },
    )


def _npm_result(*, name: str = "@myorg/mypkg") -> SourceImportResult:
    """Build an npm SourceImportResult for testing."""
    return SourceImportResult(
        source_type="npm",
        source_url=f"https://www.npmjs.com/package/{name}",
        display_name=name,
        bio="An npm package",
        raw_metadata={
            "repository": {"url": "git+https://github.com/myorg/myrepo.git"},
        },
    )


def _pypi_result(*, name: str = "mypackage") -> SourceImportResult:
    """Build a PyPI SourceImportResult for testing."""
    return SourceImportResult(
        source_type="pypi",
        source_url=f"https://pypi.org/project/{name}/",
        display_name=name,
        bio="A PyPI package",
        raw_metadata={
            "project_urls": {
                "Source": "https://github.com/myorg/myrepo",
            },
        },
    )


class TestGitHubDiscovery:
    @pytest.mark.asyncio
    async def test_discovers_npm_from_package_json(self):
        """GitHub → npm: discovers npm package from package.json."""
        pkg_json = json.dumps({"name": "@myorg/mypkg", "version": "1.0.0"})
        primary = _github_result(dep_files={"package.json": pkg_json})

        mock_head_resp = MagicMock(status_code=200)
        mock_dl_resp = MagicMock(status_code=200)
        mock_dl_resp.json.return_value = {"downloads": 5000}

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_head_resp)
        mock_client.get = AsyncMock(return_value=mock_dl_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.source_import.discovery.httpx.AsyncClient", return_value=mock_client), \
             patch("src.source_import.discovery.cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            results = await discover_related_sources(primary)

        npm_results = [r for r in results if r.provider == "npm"]
        assert len(npm_results) >= 1
        assert npm_results[0].identifier == "@myorg/mypkg"
        assert npm_results[0].discovery_method == "package.json name field"

    @pytest.mark.asyncio
    async def test_discovers_pypi_from_pyproject(self):
        """GitHub → PyPI: discovers PyPI package from pyproject.toml."""
        pyproject = '[project]\nname = "my-package"\nversion = "1.0.0"\n'
        primary = _github_result(dep_files={"pyproject.toml": pyproject})

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "info": {"author": "test"},
            "releases": {"1.0": [], "1.1": []},
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.source_import.discovery.httpx.AsyncClient", return_value=mock_client), \
             patch("src.source_import.discovery.cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            results = await discover_related_sources(primary)

        pypi_results = [r for r in results if r.provider == "pypi"]
        assert len(pypi_results) >= 1
        assert pypi_results[0].identifier == "my-package"

    @pytest.mark.asyncio
    async def test_discovers_docker_from_github(self):
        """GitHub → Docker: checks if Docker Hub repo with same owner/name exists."""
        primary = _github_result(owner="myorg", repo="myimage")

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "pull_count": 1000,
            "star_count": 5,
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.source_import.discovery.httpx.AsyncClient", return_value=mock_client), \
             patch("src.source_import.discovery.cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            results = await discover_related_sources(primary)

        docker_results = [r for r in results if r.provider == "docker"]
        assert len(docker_results) >= 1
        assert docker_results[0].identifier == "myorg/myimage"

    @pytest.mark.asyncio
    async def test_no_dep_files_returns_empty_except_docker(self):
        """GitHub with no dep files only checks Docker."""
        primary = _github_result(dep_files={})

        mock_resp = MagicMock(status_code=404)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.source_import.discovery.httpx.AsyncClient", return_value=mock_client), \
             patch("src.source_import.discovery.cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            results = await discover_related_sources(primary)

        assert len(results) == 0


class TestNpmDiscovery:
    @pytest.mark.asyncio
    async def test_discovers_github_from_npm(self):
        """npm → GitHub: discovers GitHub repo from repository.url."""
        primary = _npm_result()

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "stargazers_count": 340,
            "forks_count": 45,
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.source_import.discovery.httpx.AsyncClient", return_value=mock_client), \
             patch("src.source_import.discovery.cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            results = await discover_related_sources(primary)

        gh_results = [r for r in results if r.provider == "github"]
        assert len(gh_results) == 1
        assert gh_results[0].identifier == "myorg/myrepo"


class TestPyPIDiscovery:
    @pytest.mark.asyncio
    async def test_discovers_github_from_pypi(self):
        """PyPI → GitHub: discovers GitHub repo from project_urls."""
        primary = _pypi_result()

        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "stargazers_count": 100,
            "forks_count": 10,
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.source_import.discovery.httpx.AsyncClient", return_value=mock_client), \
             patch("src.source_import.discovery.cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            results = await discover_related_sources(primary)

        gh_results = [r for r in results if r.provider == "github"]
        assert len(gh_results) == 1
        assert gh_results[0].identifier == "myorg/myrepo"


class TestCaching:
    @pytest.mark.asyncio
    async def test_returns_cached_results(self):
        """Discovery results are returned from cache when available."""
        primary = _github_result()
        cached_data = [
            {
                "provider": "npm",
                "identifier": "cached-pkg",
                "source_url": "https://npmjs.com/package/cached-pkg",
                "discovery_method": "cached",
                "community_signals": {},
            }
        ]

        with patch("src.source_import.discovery.cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=cached_data)
            results = await discover_related_sources(primary)

        assert len(results) == 1
        assert results[0].identifier == "cached-pkg"

    @pytest.mark.asyncio
    async def test_unsupported_source_type_returns_empty(self):
        """Unknown source type returns empty list."""
        primary = SourceImportResult(
            source_type="moltbook",
            source_url="https://moltbook.com/agent/123",
            display_name="test",
            bio="",
        )

        with patch("src.source_import.discovery.cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            results = await discover_related_sources(primary)

        assert results == []
