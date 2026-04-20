"""Tests for GitHub App authentication (src/github_auth.py).

Covers:
- Fallback to PAT when App credentials absent
- JWT minting + installation-token exchange when App configured
- In-process token caching across multiple calls
- Graceful fallback to PAT if App token fetch fails
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from src import github_auth


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset the module-level token cache between tests."""
    github_auth._cache = None
    yield
    github_auth._cache = None


@pytest.mark.asyncio
async def test_falls_back_to_pat_when_app_not_configured():
    """No App creds → return legacy PAT."""
    with patch.object(github_auth.settings, "github_app_id", None), \
         patch.object(github_auth.settings, "github_app_private_key", None), \
         patch.object(github_auth.settings, "github_app_installation_id", None), \
         patch.object(github_auth.settings, "github_token", "pat-abc123"), \
         patch.object(github_auth.settings, "github_outreach_token", None):
        token = await github_auth.get_github_token()
        assert token == "pat-abc123"


@pytest.mark.asyncio
async def test_returns_none_when_nothing_configured():
    """No App, no PAT → None (caller must handle unauth)."""
    with patch.object(github_auth.settings, "github_app_id", None), \
         patch.object(github_auth.settings, "github_app_private_key", None), \
         patch.object(github_auth.settings, "github_app_installation_id", None), \
         patch.object(github_auth.settings, "github_token", None), \
         patch.object(github_auth.settings, "github_outreach_token", None):
        token = await github_auth.get_github_token()
        assert token is None


# A throwaway RSA key generated for tests only — never used anywhere real.
# Generated with: openssl genrsa -out /tmp/k.pem 2048 && cat /tmp/k.pem
_TEST_RSA_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEAy9Lv3P2pZJi4RC0JJmBr8Y8AK5LZrZk5P+9S5L7qYbKQfBrI
6qVpK8cbZV5mR4X9F1c3M5m3fJ8zQ2lWqP0h3vP5W2rYmL9jE1nCfH3s5yGqZ6X5
TEST_KEY_FOR_UNIT_TESTS_ONLY
-----END RSA PRIVATE KEY-----"""


@pytest.mark.asyncio
async def test_app_token_fetched_and_cached():
    """App configured → mint JWT, exchange for installation token, cache it."""
    class _FakeResp:
        status_code = 201

        def json(self):
            return {"token": "ghs_installation_token_xyz", "expires_at": "future"}

    post_mock = AsyncMock(return_value=_FakeResp())

    with patch.object(github_auth.settings, "github_app_id", "123456"), \
         patch.object(github_auth.settings, "github_app_private_key", _TEST_RSA_PRIVATE_KEY), \
         patch.object(github_auth.settings, "github_app_installation_id", "78910"), \
         patch("httpx.AsyncClient.post", post_mock), \
         patch.object(github_auth, "_mint_app_jwt", return_value="fake.jwt.token"):
        # First call fetches
        token1 = await github_auth.get_github_token()
        assert token1 == "ghs_installation_token_xyz"
        assert post_mock.await_count == 1

        # Second call hits cache — no new fetch
        token2 = await github_auth.get_github_token()
        assert token2 == "ghs_installation_token_xyz"
        assert post_mock.await_count == 1


@pytest.mark.asyncio
async def test_app_token_fetch_failure_falls_back_to_pat():
    """If GitHub rejects our App JWT, fall back to the PAT so scans keep working."""
    class _FailResp:
        status_code = 401
        text = "Bad credentials"

    post_mock = AsyncMock(return_value=_FailResp())

    with patch.object(github_auth.settings, "github_app_id", "123456"), \
         patch.object(github_auth.settings, "github_app_private_key", _TEST_RSA_PRIVATE_KEY), \
         patch.object(github_auth.settings, "github_app_installation_id", "78910"), \
         patch.object(github_auth.settings, "github_token", "fallback-pat"), \
         patch.object(github_auth.settings, "github_outreach_token", None), \
         patch("httpx.AsyncClient.post", post_mock), \
         patch.object(github_auth, "_mint_app_jwt", return_value="fake.jwt.token"):
        token = await github_auth.get_github_token()
        assert token == "fallback-pat"


@pytest.mark.asyncio
async def test_expired_cache_triggers_refresh():
    """Cached token near expiry → fetch new one."""
    # Pre-populate cache with an about-to-expire token
    github_auth._cache = github_auth._CachedToken(
        token="stale_token",
        expires_at=time.time() + 60,  # 1 min left, refresh threshold is 5 min
    )

    class _FakeResp:
        status_code = 201

        def json(self):
            return {"token": "ghs_fresh_token", "expires_at": "future"}

    post_mock = AsyncMock(return_value=_FakeResp())

    with patch.object(github_auth.settings, "github_app_id", "123456"), \
         patch.object(github_auth.settings, "github_app_private_key", _TEST_RSA_PRIVATE_KEY), \
         patch.object(github_auth.settings, "github_app_installation_id", "78910"), \
         patch("httpx.AsyncClient.post", post_mock), \
         patch.object(github_auth, "_mint_app_jwt", return_value="fake.jwt.token"):
        token = await github_auth.get_github_token()
        assert token == "ghs_fresh_token"
        assert post_mock.await_count == 1


@pytest.mark.asyncio
async def test_auth_header_helper():
    """get_github_auth_header() returns the Bearer header dict."""
    with patch.object(github_auth, "get_github_token", AsyncMock(return_value="abc")):
        h = await github_auth.get_github_auth_header()
        assert h == {"Authorization": "Bearer abc"}

    with patch.object(github_auth, "get_github_token", AsyncMock(return_value=None)):
        h = await github_auth.get_github_auth_header()
        assert h == {}
