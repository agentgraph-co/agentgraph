"""Tests for Docker Hub fetcher."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.source_import.docker_fetcher import fetch_docker, parse_docker_url
from src.source_import.errors import SourceFetchError, SourceParseError


class TestParseDockerUrl:
    def test_standard_repo(self):
        ns, name = parse_docker_url("https://hub.docker.com/r/langchain/langchain")
        assert ns == "langchain"
        assert name == "langchain"

    def test_official_image(self):
        ns, name = parse_docker_url("https://hub.docker.com/_/python")
        assert ns == "library"
        assert name == "python"

    def test_with_trailing_slash(self):
        ns, name = parse_docker_url("https://hub.docker.com/r/owner/repo/")
        assert ns == "owner"
        assert name == "repo"

    def test_invalid_url(self):
        with pytest.raises(SourceParseError):
            parse_docker_url("https://example.com/not-docker")

    def test_github_url_raises(self):
        with pytest.raises(SourceParseError):
            parse_docker_url("https://github.com/owner/repo")


class TestFetchDocker:
    @pytest.mark.asyncio
    async def test_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "pull_count": 50000,
            "star_count": 42,
            "description": "A great image",
            "full_description": "Full description here",
            "last_updated": "2026-03-01T00:00:00Z",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.source_import.docker_fetcher.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_docker("myorg", "myimage", "https://hub.docker.com/r/myorg/myimage")

        assert result.source_type == "docker"
        assert result.display_name == "myorg/myimage"
        assert result.community_signals["pulls"] == 50000
        assert result.community_signals["stars"] == 42
        assert result.bio == "A great image"

    @pytest.mark.asyncio
    async def test_official_image_display_name(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "pull_count": 1000000,
            "star_count": 100,
            "description": "Official Python image",
            "full_description": "",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.source_import.docker_fetcher.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_docker("library", "python", "https://hub.docker.com/_/python")

        assert result.display_name == "python"
        assert result.raw_metadata["is_official"] is True

    @pytest.mark.asyncio
    async def test_not_found(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.source_import.docker_fetcher.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(SourceFetchError, match="not found"):
                await fetch_docker("ns", "nonexistent", "https://hub.docker.com/r/ns/nonexistent")

    @pytest.mark.asyncio
    async def test_server_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.source_import.docker_fetcher.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(SourceFetchError, match="status 500"):
                await fetch_docker("ns", "repo", "https://hub.docker.com/r/ns/repo")
