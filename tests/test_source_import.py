"""Tests for the source import module."""
from __future__ import annotations

import pytest

from src.source_import.types import SourceImportResult


class TestSourceImportResult:
    def test_dataclass_creation(self):
        result = SourceImportResult(
            source_type="github",
            source_url="https://github.com/test/repo",
            display_name="Test Repo",
            bio="A test repository",
        )
        assert result.source_type == "github"
        assert result.display_name == "Test Repo"
        assert result.capabilities == []
        assert result.community_signals == {}

    def test_all_fields(self):
        result = SourceImportResult(
            source_type="npm",
            source_url="https://www.npmjs.com/package/test",
            display_name="test",
            bio="Test package",
            capabilities=["chat", "search"],
            detected_framework="mcp",
            autonomy_level=3,
            community_signals={"downloads_monthly": 1000},
            raw_metadata={"name": "test"},
            readme_excerpt="# Test",
            avatar_url="https://example.com/avatar.png",
            version="1.0.0",
        )
        assert result.detected_framework == "mcp"
        assert len(result.capabilities) == 2
        assert result.community_signals["downloads_monthly"] == 1000


class TestResolver:
    @pytest.mark.asyncio
    async def test_invalid_url_raises(self):
        from src.source_import.resolver import resolve_source

        with pytest.raises(ValueError):
            await resolve_source("not-a-url")

    @pytest.mark.asyncio
    async def test_private_url_raises(self):
        from src.source_import.resolver import resolve_source

        with pytest.raises(ValueError):
            await resolve_source("http://localhost/repo")

    @pytest.mark.asyncio
    async def test_unsupported_url_raises(self):
        from src.source_import.resolver import resolve_source

        with pytest.raises(ValueError, match="Unsupported"):
            await resolve_source("https://example.com/random-page")
