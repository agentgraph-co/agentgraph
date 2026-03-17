"""Tests for source import system — URL parsing, SourceImportResult, preview/import endpoints."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import Entity
from src.source_import.errors import (
    SourceFetchError,
    SourceImportError,
    SourceParseError,
    UnsupportedSourceError,
)
from src.source_import.types import SourceImportResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


PREVIEW_URL = "/api/v1/bots/preview-source"
IMPORT_URL = "/api/v1/bots/import-source"
REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"

HUMAN = {
    "email": "source_import_human@example.com",
    "password": "Str0ngP@ss!1",
    "display_name": "SourceImportHuman",
}


def _make_result(**overrides) -> SourceImportResult:
    """Helper to build a SourceImportResult with sensible defaults."""
    defaults = dict(
        source_type="github",
        source_url="https://github.com/owner/repo",
        display_name="owner/repo",
        bio="A cool agent repo",
        capabilities=["code_review", "testing"],
        detected_framework="langchain",
        autonomy_level=3,
        community_signals={"stars": 100, "forks": 20},
        raw_metadata={"owner": "owner", "repo": "repo"},
        readme_excerpt="# My Repo\nSome text",
        avatar_url="https://avatars.githubusercontent.com/u/12345",
        version=None,
    )
    defaults.update(overrides)
    return SourceImportResult(**defaults)


async def _register_and_login(client: AsyncClient) -> dict:
    """Register a human user, verify email, login, return auth headers."""
    await client.post(REGISTER_URL, json=HUMAN)
    resp = await client.post(LOGIN_URL, json={
        "email": HUMAN["email"],
        "password": HUMAN["password"],
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# 1. Unit tests for resolver URL parsing
# ===========================================================================


class TestResolverUrlParsing:
    """Test _dispatch() URL matching without real network calls."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", [
        "https://github.com/owner/repo",
        "https://github.com/owner/repo.git",
        "https://github.com/owner/repo/",
        "https://github.com/owner/repo/tree/main",
        "https://github.com/owner/repo/tree/main/src",
    ])
    async def test_github_urls_dispatch_to_github_fetcher(self, url):
        """GitHub URLs dispatch to fetch_github."""
        with patch(
            "src.source_import.resolver.validate_url", return_value=url,
        ), patch(
            "src.source_import.resolver.cache",
        ) as mock_cache, patch(
            "src.source_import.github_fetcher.fetch_github",
            new_callable=AsyncMock,
            return_value=_make_result(source_url=url),
        ) as mock_fetch:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()

            from src.source_import.resolver import resolve_source
            result = await resolve_source(url)
            assert result.source_type == "github"
            mock_fetch.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url,expected_pkg", [
        ("https://www.npmjs.com/package/foo", "foo"),
        ("https://www.npmjs.com/package/@org/name", "@org/name"),
        ("https://npmjs.com/package/bar", "bar"),
    ])
    async def test_npm_urls_dispatch_to_npm_fetcher(self, url, expected_pkg):
        """npm URLs dispatch to fetch_npm with correct package name."""
        with patch(
            "src.source_import.resolver.validate_url", return_value=url,
        ), patch(
            "src.source_import.resolver.cache",
        ) as mock_cache, patch(
            "src.source_import.npm_fetcher.fetch_npm",
            new_callable=AsyncMock,
            return_value=_make_result(source_type="npm", source_url=url),
        ) as mock_fetch:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()

            from src.source_import.resolver import resolve_source
            result = await resolve_source(url)
            assert result.source_type == "npm"
            mock_fetch.assert_awaited_once_with(expected_pkg, url)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", [
        "https://pypi.org/project/requests/",
        "https://pypi.org/project/my-package",
    ])
    async def test_pypi_urls_dispatch_to_pypi_fetcher(self, url):
        """PyPI URLs dispatch to fetch_pypi."""
        with patch(
            "src.source_import.resolver.validate_url", return_value=url,
        ), patch(
            "src.source_import.resolver.cache",
        ) as mock_cache, patch(
            "src.source_import.pypi_fetcher.fetch_pypi",
            new_callable=AsyncMock,
            return_value=_make_result(source_type="pypi", source_url=url),
        ) as mock_fetch:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()

            from src.source_import.resolver import resolve_source
            result = await resolve_source(url)
            assert result.source_type == "pypi"
            mock_fetch.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", [
        "https://huggingface.co/org/model",
        "https://huggingface.co/microsoft/phi-3",
    ])
    async def test_huggingface_urls_dispatch_to_hf_fetcher(self, url):
        """HuggingFace URLs dispatch to fetch_huggingface."""
        with patch(
            "src.source_import.resolver.validate_url", return_value=url,
        ), patch(
            "src.source_import.resolver.cache",
        ) as mock_cache, patch(
            "src.source_import.huggingface_fetcher.fetch_huggingface",
            new_callable=AsyncMock,
            return_value=_make_result(source_type="huggingface", source_url=url),
        ) as mock_fetch:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()

            from src.source_import.resolver import resolve_source
            result = await resolve_source(url)
            assert result.source_type == "huggingface"
            mock_fetch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mcp_manifest_url(self):
        """URLs ending in .json dispatch to fetch_mcp."""
        url = "https://example.com/manifest.json"
        with patch(
            "src.source_import.resolver.validate_url", return_value=url,
        ), patch(
            "src.source_import.resolver.cache",
        ) as mock_cache, patch(
            "src.source_import.mcp_fetcher.fetch_mcp",
            new_callable=AsyncMock,
            return_value=_make_result(source_type="mcp_manifest", source_url=url),
        ) as mock_fetch:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()

            from src.source_import.resolver import resolve_source
            result = await resolve_source(url)
            assert result.source_type == "mcp_manifest"
            mock_fetch.assert_awaited_once_with(url)

    @pytest.mark.asyncio
    async def test_a2a_agent_card_url(self):
        """A2A agent.json URLs dispatch to fetch_a2a."""
        url = "https://example.com/.well-known/agent.json"
        with patch(
            "src.source_import.resolver.validate_url", return_value=url,
        ), patch(
            "src.source_import.resolver.cache",
        ) as mock_cache, patch(
            "src.source_import.a2a_fetcher.fetch_a2a",
            new_callable=AsyncMock,
            return_value=_make_result(source_type="a2a_card", source_url=url),
        ) as mock_fetch:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()

            from src.source_import.resolver import resolve_source
            result = await resolve_source(url)
            assert result.source_type == "a2a_card"
            mock_fetch.assert_awaited_once_with(url)

    @pytest.mark.asyncio
    async def test_unsupported_url_raises(self):
        """Unsupported URLs raise UnsupportedSourceError."""
        url = "https://random-site.com/foo"
        with patch(
            "src.source_import.resolver.validate_url", return_value=url,
        ), patch(
            "src.source_import.resolver.cache",
        ) as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)

            from src.source_import.resolver import resolve_source
            with pytest.raises(UnsupportedSourceError, match="Unsupported source URL"):
                await resolve_source(url)


# ===========================================================================
# 2. Unit tests for SourceImportResult dataclass
# ===========================================================================


class TestSourceImportResult:
    """Tests for the SourceImportResult dataclass."""

    def test_defaults(self):
        """Required fields only; optional fields get default values."""
        result = SourceImportResult(
            source_type="github",
            source_url="https://github.com/owner/repo",
            display_name="owner/repo",
            bio="A description",
        )
        assert result.capabilities == []
        assert result.detected_framework is None
        assert result.autonomy_level is None
        assert result.community_signals == {}
        assert result.raw_metadata == {}
        assert result.readme_excerpt == ""
        assert result.avatar_url is None
        assert result.version is None

    def test_all_fields(self):
        """All fields populate correctly."""
        result = _make_result(
            source_type="npm",
            version="1.2.3",
            autonomy_level=4,
        )
        assert result.source_type == "npm"
        assert result.version == "1.2.3"
        assert result.autonomy_level == 4
        assert result.display_name == "owner/repo"
        assert result.bio == "A cool agent repo"
        assert len(result.capabilities) == 2
        assert result.detected_framework == "langchain"
        assert result.community_signals["stars"] == 100
        assert result.raw_metadata["owner"] == "owner"
        assert result.readme_excerpt.startswith("# My Repo")
        assert result.avatar_url is not None

    def test_mutable_defaults_independent(self):
        """Each instance gets its own mutable default lists/dicts."""
        a = SourceImportResult(
            source_type="a", source_url="u", display_name="n", bio="b",
        )
        b = SourceImportResult(
            source_type="b", source_url="u2", display_name="n2", bio="b2",
        )
        a.capabilities.append("x")
        assert "x" not in b.capabilities
        a.community_signals["k"] = 1
        assert "k" not in b.community_signals


# ===========================================================================
# 3. API endpoint tests for /bots/preview-source
# ===========================================================================


class TestPreviewSource:
    """Tests for POST /bots/preview-source endpoint."""

    @pytest.mark.asyncio
    async def test_preview_github_url_200(self, client: AsyncClient):
        """Valid GitHub URL returns 200 with preview data."""
        mock_result = _make_result()
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.post(PREVIEW_URL, json={
                "source_url": "https://github.com/owner/repo",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_type"] == "github"
        assert data["display_name"] == "owner/repo"
        assert data["bio"] == "A cool agent repo"
        assert data["capabilities"] == ["code_review", "testing"]
        assert data["detected_framework"] == "langchain"
        assert data["community_signals"]["stars"] == 100
        assert data["readme_excerpt"].startswith("# My Repo")
        assert data["avatar_url"] is not None

    @pytest.mark.asyncio
    async def test_preview_unsupported_url_400(self, client: AsyncClient):
        """Unsupported URL returns 400."""
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            side_effect=UnsupportedSourceError("Unsupported source URL"),
        ):
            resp = await client.post(PREVIEW_URL, json={
                "source_url": "https://random-site.com/foo",
            })
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_preview_network_error_502(self, client: AsyncClient):
        """Network error returns 502."""
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            side_effect=SourceFetchError("Connection timed out"),
        ):
            resp = await client.post(PREVIEW_URL, json={
                "source_url": "https://github.com/owner/repo",
            })
        assert resp.status_code == 502
        assert "timed out" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_preview_parse_error_422(self, client: AsyncClient):
        """Parse error returns 422."""
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            side_effect=SourceParseError("Invalid JSON"),
        ):
            resp = await client.post(PREVIEW_URL, json={
                "source_url": "https://example.com/manifest.json",
            })
        assert resp.status_code == 422
        assert "Invalid JSON" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_preview_no_auth_required(self, client: AsyncClient):
        """Preview works without authentication (public endpoint)."""
        mock_result = _make_result()
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.post(PREVIEW_URL, json={
                "source_url": "https://github.com/owner/repo",
            })
        # No auth header sent — should still work
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_preview_generic_import_error_400(self, client: AsyncClient):
        """SourceImportError base class returns 400."""
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            side_effect=SourceImportError("Something went wrong"),
        ):
            resp = await client.post(PREVIEW_URL, json={
                "source_url": "https://github.com/owner/repo",
            })
        assert resp.status_code == 400


# ===========================================================================
# 4. API endpoint tests for /bots/import-source
# ===========================================================================


class TestImportSource:
    """Tests for POST /bots/import-source endpoint."""

    @pytest.mark.asyncio
    async def test_unauthenticated_import_201_provisional(self, client: AsyncClient):
        """Unauthenticated import creates a provisional entity with claim_token."""
        mock_result = _make_result()
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.post(IMPORT_URL, json={
                "source_url": "https://github.com/owner/repo",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent"]["display_name"] == "owner/repo"
        assert data["api_key"]  # non-empty
        assert data["claim_token"] is not None
        assert data["readiness"] is not None

    @pytest.mark.asyncio
    async def test_authenticated_import_201(self, client: AsyncClient, db):
        """Authenticated import creates entity owned by operator."""
        headers = await _register_and_login(client)
        mock_result = _make_result()
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.post(
                IMPORT_URL,
                json={"source_url": "https://github.com/owner/repo"},
                headers=headers,
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent"]["display_name"] == "owner/repo"
        assert data["api_key"]

    @pytest.mark.asyncio
    async def test_import_with_display_name_override(self, client: AsyncClient):
        """User-provided display_name overrides the fetched one."""
        mock_result = _make_result(display_name="fetched-name")
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.post(IMPORT_URL, json={
                "source_url": "https://github.com/owner/repo",
                "display_name": "MyCustomBot",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent"]["display_name"] == "MyCustomBot"

    @pytest.mark.asyncio
    async def test_import_sets_source_fields_on_entity(self, client: AsyncClient, db):
        """Import sets source_url, source_type, source_verified_at on entity."""
        mock_result = _make_result(
            source_type="github",
            source_url="https://github.com/owner/repo",
        )
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.post(IMPORT_URL, json={
                "source_url": "https://github.com/owner/repo",
            })
        assert resp.status_code == 201
        agent_id = resp.json()["agent"]["id"]

        # Verify in DB
        from sqlalchemy import select
        row = await db.execute(
            select(Entity).where(Entity.id == uuid.UUID(agent_id))
        )
        entity = row.scalar_one()
        assert entity.source_url == "https://github.com/owner/repo"
        assert entity.source_type == "github"
        assert entity.source_verified_at is not None

    @pytest.mark.asyncio
    async def test_import_stores_onboarding_data(self, client: AsyncClient, db):
        """Import stores import_source key in onboarding_data."""
        mock_result = _make_result()
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.post(IMPORT_URL, json={
                "source_url": "https://github.com/owner/repo",
            })
        assert resp.status_code == 201
        agent_id = resp.json()["agent"]["id"]

        from sqlalchemy import select
        row = await db.execute(
            select(Entity).where(Entity.id == uuid.UUID(agent_id))
        )
        entity = row.scalar_one()
        assert "import_source" in (entity.onboarding_data or {})
        import_data = entity.onboarding_data["import_source"]
        assert import_data["url"] == "https://github.com/owner/repo"
        assert import_data["type"] == "github"

    @pytest.mark.asyncio
    async def test_import_unsupported_url_400(self, client: AsyncClient):
        """Unsupported URL on import returns 400."""
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            side_effect=UnsupportedSourceError("Unsupported source URL"),
        ):
            resp = await client.post(IMPORT_URL, json={
                "source_url": "https://random-site.com/foo",
            })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_import_network_error_502(self, client: AsyncClient):
        """Network error on import returns 502."""
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            side_effect=SourceFetchError("GitHub API timeout"),
        ):
            resp = await client.post(IMPORT_URL, json={
                "source_url": "https://github.com/owner/repo",
            })
        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_import_with_capabilities_override(self, client: AsyncClient):
        """User-provided capabilities override fetched ones."""
        mock_result = _make_result(capabilities=["fetched_cap"])
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.post(IMPORT_URL, json={
                "source_url": "https://github.com/owner/repo",
                "capabilities": ["my_cap_1", "my_cap_2"],
            })
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_import_sets_avatar_from_source(self, client: AsyncClient, db):
        """Import sets avatar_url from source when agent has none."""
        mock_result = _make_result(
            avatar_url="https://example.com/avatar.png",
        )
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.post(IMPORT_URL, json={
                "source_url": "https://github.com/owner/repo",
            })
        assert resp.status_code == 201
        agent_id = resp.json()["agent"]["id"]

        from sqlalchemy import select
        row = await db.execute(
            select(Entity).where(Entity.id == uuid.UUID(agent_id))
        )
        entity = row.scalar_one()
        assert entity.avatar_url == "https://example.com/avatar.png"


# ===========================================================================
# 5. Error handling tests
# ===========================================================================


class TestErrorHandling:
    """Tests for SSRF, validation, and edge-case errors."""

    @pytest.mark.asyncio
    async def test_ssrf_internal_ip_400(self, client: AsyncClient):
        """Internal IP in source_url is rejected (SSRF protection)."""
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            side_effect=ValueError("source_url cannot point to internal addresses"),
        ):
            resp = await client.post(PREVIEW_URL, json={
                "source_url": "http://192.168.1.1/manifest.json",
            })
        assert resp.status_code == 400
        assert "internal" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_ssrf_localhost_400(self, client: AsyncClient):
        """localhost in source_url is rejected (SSRF protection)."""
        with patch(
            "src.api.bot_onboarding_router.resolve_source",
            new_callable=AsyncMock,
            side_effect=ValueError("source_url cannot point to internal addresses"),
        ):
            resp = await client.post(PREVIEW_URL, json={
                "source_url": "http://localhost:8000/manifest.json",
            })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_url_422(self, client: AsyncClient):
        """Empty source_url is rejected by Pydantic validation."""
        resp = await client.post(PREVIEW_URL, json={
            "source_url": "",
        })
        # Pydantic may reject empty string or SSRF validator catches it
        assert resp.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_missing_url_field_422(self, client: AsyncClient):
        """Missing source_url field returns 422."""
        resp = await client.post(PREVIEW_URL, json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_ssrf_validate_url_unit(self):
        """Unit test: validate_url rejects private IPs directly."""
        from src.ssrf import validate_url

        with pytest.raises(ValueError, match="internal"):
            validate_url("http://10.0.0.1/foo", field_name="source_url")

        with pytest.raises(ValueError, match="internal"):
            validate_url("http://127.0.0.1/foo", field_name="source_url")

        with pytest.raises(ValueError, match="internal"):
            validate_url("http://192.168.1.1/foo", field_name="source_url")

        with pytest.raises(ValueError, match="internal"):
            validate_url("http://localhost/foo", field_name="source_url")

    @pytest.mark.asyncio
    async def test_ssrf_validate_url_allows_public(self):
        """Unit test: validate_url allows public URLs."""
        from src.ssrf import validate_url

        result = validate_url(
            "https://github.com/owner/repo", field_name="source_url",
        )
        assert result == "https://github.com/owner/repo"

    @pytest.mark.asyncio
    async def test_import_url_too_long_422(self, client: AsyncClient):
        """URL exceeding max_length is rejected."""
        long_url = "https://github.com/" + "a" * 1000
        resp = await client.post(PREVIEW_URL, json={
            "source_url": long_url,
        })
        assert resp.status_code == 422


# ===========================================================================
# 6. GitHub URL parser unit tests
# ===========================================================================


class TestParseGithubUrl:
    """Unit tests for parse_github_url from github_fetcher."""

    def test_simple_url(self):
        from src.source_import.github_fetcher import parse_github_url
        owner, repo = parse_github_url("https://github.com/owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_url_with_dot_git(self):
        from src.source_import.github_fetcher import parse_github_url
        owner, repo = parse_github_url("https://github.com/owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"

    def test_url_with_trailing_slash(self):
        from src.source_import.github_fetcher import parse_github_url
        owner, repo = parse_github_url("https://github.com/owner/repo/")
        assert owner == "owner"
        assert repo == "repo"

    def test_url_with_tree_main(self):
        from src.source_import.github_fetcher import parse_github_url
        owner, repo = parse_github_url("https://github.com/owner/repo/tree/main")
        assert owner == "owner"
        assert repo == "repo"

    def test_url_with_blob_path(self):
        from src.source_import.github_fetcher import parse_github_url
        owner, repo = parse_github_url(
            "https://github.com/owner/repo/blob/main/src/file.py",
        )
        assert owner == "owner"
        assert repo == "repo"

    def test_ssh_url(self):
        from src.source_import.github_fetcher import parse_github_url
        owner, repo = parse_github_url("git@github.com:owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"

    def test_invalid_url_raises(self):
        from src.source_import.github_fetcher import (
            SourceFetchError,
            parse_github_url,
        )
        with pytest.raises(SourceFetchError):
            parse_github_url("https://not-github.com/owner/repo")


# ===========================================================================
# 7. Resolver cache behavior
# ===========================================================================


class TestResolverCache:
    """Test that resolver checks and populates Redis cache."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_fetch(self):
        """When cache has a result, no fetcher is called."""
        url = "https://github.com/cached/repo"
        cached_data = {
            "source_type": "github",
            "source_url": url,
            "display_name": "cached/repo",
            "bio": "cached bio",
            "capabilities": [],
            "detected_framework": None,
            "autonomy_level": None,
            "community_signals": {},
            "raw_metadata": {},
            "readme_excerpt": "",
            "avatar_url": None,
            "version": None,
        }
        with patch(
            "src.source_import.resolver.validate_url", return_value=url,
        ), patch(
            "src.source_import.resolver.cache",
        ) as mock_cache:
            mock_cache.get = AsyncMock(return_value=cached_data)

            from src.source_import.resolver import resolve_source
            result = await resolve_source(url)
            assert result.display_name == "cached/repo"
            # _dispatch should not be called (no fetcher mock needed)

    @pytest.mark.asyncio
    async def test_cache_miss_populates_cache(self):
        """When cache misses, fetcher is called and result is cached."""
        url = "https://github.com/new/repo"
        mock_result = _make_result(source_url=url)
        with patch(
            "src.source_import.resolver.validate_url", return_value=url,
        ), patch(
            "src.source_import.resolver.cache",
        ) as mock_cache, patch(
            "src.source_import.github_fetcher.fetch_github",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()

            from src.source_import.resolver import resolve_source
            result = await resolve_source(url)
            assert result.source_url == url
            mock_cache.set.assert_awaited_once()
