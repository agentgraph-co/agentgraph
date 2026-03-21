from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.database import get_db
from src.main import app


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False,
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


def _make_google_state(ts: int | None = None, platform: str = "") -> str:
    """Build a valid HMAC-signed Google OAuth state parameter."""
    if ts is None:
        ts = int(time.time())
    state_data = f"{ts}:{platform}"
    sig = hmac.new(
        settings.jwt_secret.encode(), state_data.encode(), hashlib.sha256,
    ).hexdigest()[:32]
    return f"{state_data}:{sig}"


def _make_github_state(ts: int | None = None, platform: str = "") -> str:
    """Build a valid HMAC-signed GitHub OAuth state parameter (login flow)."""
    if ts is None:
        ts = int(time.time())
    state_data = f"login:{ts}:{platform}"
    sig = hmac.new(
        settings.jwt_secret.encode(), state_data.encode(), hashlib.sha256,
    ).hexdigest()[:32]
    return f"{state_data}:{sig}"


# ---------------------------------------------------------------------------
# Google OAuth — /api/v1/auth/google
# ---------------------------------------------------------------------------


class TestGoogleOAuthRedirect:
    """GET /api/v1/auth/google returns a redirect to Google consent screen."""

    @pytest.mark.asyncio
    async def test_redirect_contains_state_and_client_id(self, client: AsyncClient):
        settings.google_client_id = "test-google-id"
        settings.google_client_secret = "test-google-secret"
        try:
            resp = await client.get("/api/v1/auth/google")
            assert resp.status_code == 307
            location = resp.headers["location"]
            assert "accounts.google.com" in location
            assert "client_id=test-google-id" in location
            assert "state=" in location
        finally:
            settings.google_client_id = None
            settings.google_client_secret = None

    @pytest.mark.asyncio
    async def test_redirect_with_platform_param(self, client: AsyncClient):
        settings.google_client_id = "test-google-id"
        settings.google_client_secret = "test-google-secret"
        try:
            resp = await client.get("/api/v1/auth/google?platform=ios")
            assert resp.status_code == 307
            location = resp.headers["location"]
            assert "state=" in location
        finally:
            settings.google_client_id = None
            settings.google_client_secret = None

    @pytest.mark.asyncio
    async def test_returns_501_when_not_configured(self, client: AsyncClient):
        settings.google_client_id = None
        resp = await client.get("/api/v1/auth/google")
        assert resp.status_code == 501
        assert "not configured" in resp.json()["detail"]


class TestGoogleOAuthCallback:
    """GET /api/v1/auth/google/callback — state validation and user handling."""

    @pytest.mark.asyncio
    async def test_missing_state_returns_400(self, client: AsyncClient):
        settings.google_client_id = "test-google-id"
        settings.google_client_secret = "test-google-secret"
        try:
            resp = await client.get(
                "/api/v1/auth/google/callback?code=fake-code"
            )
            assert resp.status_code == 400
            assert "Missing OAuth state" in resp.json()["detail"]
        finally:
            settings.google_client_id = None
            settings.google_client_secret = None

    @pytest.mark.asyncio
    async def test_invalid_state_format_returns_400(self, client: AsyncClient):
        settings.google_client_id = "test-google-id"
        settings.google_client_secret = "test-google-secret"
        try:
            resp = await client.get(
                "/api/v1/auth/google/callback?code=fake&state=badformat"
            )
            assert resp.status_code == 400
            assert "Invalid OAuth state" in resp.json()["detail"]
        finally:
            settings.google_client_id = None
            settings.google_client_secret = None

    @pytest.mark.asyncio
    async def test_invalid_hmac_signature_returns_400(self, client: AsyncClient):
        settings.google_client_id = "test-google-id"
        settings.google_client_secret = "test-google-secret"
        try:
            ts = str(int(time.time()))
            bad_state = f"{ts}::{'a' * 32}"
            resp = await client.get(
                f"/api/v1/auth/google/callback?code=fake&state={bad_state}"
            )
            assert resp.status_code == 400
            assert "Invalid OAuth state signature" in resp.json()["detail"]
        finally:
            settings.google_client_id = None
            settings.google_client_secret = None

    @pytest.mark.asyncio
    async def test_expired_state_returns_400(self, client: AsyncClient):
        settings.google_client_id = "test-google-id"
        settings.google_client_secret = "test-google-secret"
        try:
            # State from 20 minutes ago (>10 min TTL)
            expired_state = _make_google_state(ts=int(time.time()) - 1200)
            resp = await client.get(
                f"/api/v1/auth/google/callback?code=fake&state={expired_state}"
            )
            assert resp.status_code == 400
            assert "expired" in resp.json()["detail"].lower()
        finally:
            settings.google_client_id = None
            settings.google_client_secret = None

    @pytest.mark.asyncio
    async def test_google_exchange_failure_returns_400(self, client: AsyncClient):
        settings.google_client_id = "test-google-id"
        settings.google_client_secret = "test-google-secret"
        try:
            state = _make_google_state()
            with patch(
                "src.api.auth_router.exchange_google_code",
                new_callable=AsyncMock,
                return_value=None,
            ):
                resp = await client.get(
                    f"/api/v1/auth/google/callback?code=bad-code&state={state}"
                )
                assert resp.status_code == 400
                assert "Google authentication failed" in resp.json()["detail"]
        finally:
            settings.google_client_id = None
            settings.google_client_secret = None

    @pytest.mark.asyncio
    async def test_google_no_email_returns_400(self, client: AsyncClient):
        settings.google_client_id = "test-google-id"
        settings.google_client_secret = "test-google-secret"
        try:
            state = _make_google_state()
            with patch(
                "src.api.auth_router.exchange_google_code",
                new_callable=AsyncMock,
                return_value={"id": "123", "name": "No Email User"},
            ):
                resp = await client.get(
                    f"/api/v1/auth/google/callback?code=ok&state={state}"
                )
                assert resp.status_code == 400
                assert "no email" in resp.json()["detail"].lower()
        finally:
            settings.google_client_id = None
            settings.google_client_secret = None

    @pytest.mark.asyncio
    async def test_successful_new_user_registration(self, client: AsyncClient):
        """Successful Google callback with a new email creates an account
        and returns a redirect with tokens."""
        settings.google_client_id = "test-google-id"
        settings.google_client_secret = "test-google-secret"
        try:
            state = _make_google_state()
            unique_email = f"google-new-{uuid.uuid4().hex[:8]}@example.com"
            with patch(
                "src.api.auth_router.exchange_google_code",
                new_callable=AsyncMock,
                return_value={
                    "id": "goog-12345",
                    "email": unique_email,
                    "name": "Google User",
                    "picture": "https://example.com/pic.jpg",
                },
            ):
                resp = await client.get(
                    f"/api/v1/auth/google/callback?code=valid&state={state}"
                )
                assert resp.status_code == 307
                location = resp.headers["location"]
                assert "access_token=" in location
                assert "refresh_token=" in location
        finally:
            settings.google_client_id = None
            settings.google_client_secret = None

    @pytest.mark.asyncio
    async def test_successful_existing_user_login(self, client: AsyncClient, db):
        """Successful Google callback with an existing email logs in
        the existing user instead of creating a new one."""
        from src.models import Entity, EntityType

        settings.google_client_id = "test-google-id"
        settings.google_client_secret = "test-google-secret"

        existing_email = f"google-exist-{uuid.uuid4().hex[:8]}@example.com"
        entity_id = uuid.uuid4()
        entity = Entity(
            id=entity_id,
            type=EntityType.HUMAN,
            email=existing_email,
            password_hash="hashed",
            display_name="Existing User",
            email_verified=True,
            is_active=True,
            did_web=f"did:web:agentgraph.co:users:{entity_id}",
        )
        db.add(entity)
        await db.flush()

        try:
            state = _make_google_state()
            with patch(
                "src.api.auth_router.exchange_google_code",
                new_callable=AsyncMock,
                return_value={
                    "id": "goog-99999",
                    "email": existing_email,
                    "name": "Existing User",
                    "picture": "https://example.com/avatar.jpg",
                },
            ):
                resp = await client.get(
                    f"/api/v1/auth/google/callback?code=valid&state={state}"
                )
                assert resp.status_code == 307
                location = resp.headers["location"]
                assert "access_token=" in location
        finally:
            settings.google_client_id = None
            settings.google_client_secret = None

    @pytest.mark.asyncio
    async def test_deactivated_user_returns_403(self, client: AsyncClient, db):
        """Google login for a deactivated account returns 403."""
        from src.models import Entity, EntityType

        settings.google_client_id = "test-google-id"
        settings.google_client_secret = "test-google-secret"

        deactivated_email = f"google-deact-{uuid.uuid4().hex[:8]}@example.com"
        deact_id = uuid.uuid4()
        entity = Entity(
            id=deact_id,
            type=EntityType.HUMAN,
            email=deactivated_email,
            password_hash="hashed",
            display_name="Deactivated",
            email_verified=True,
            is_active=False,
            did_web=f"did:web:agentgraph.co:users:{deact_id}",
        )
        db.add(entity)
        await db.flush()

        try:
            state = _make_google_state()
            with patch(
                "src.api.auth_router.exchange_google_code",
                new_callable=AsyncMock,
                return_value={
                    "id": "goog-deact",
                    "email": deactivated_email,
                    "name": "Deactivated",
                },
            ):
                resp = await client.get(
                    f"/api/v1/auth/google/callback?code=valid&state={state}"
                )
                assert resp.status_code == 403
                assert "deactivated" in resp.json()["detail"].lower()
        finally:
            settings.google_client_id = None
            settings.google_client_secret = None

    @pytest.mark.asyncio
    async def test_ios_platform_redirects_to_custom_scheme(
        self, client: AsyncClient,
    ):
        """Google callback with platform=ios in state redirects to
        com.agentgraph.ios:// scheme."""
        settings.google_client_id = "test-google-id"
        settings.google_client_secret = "test-google-secret"
        try:
            state = _make_google_state(platform="ios")
            unique_email = f"google-ios-{uuid.uuid4().hex[:8]}@example.com"
            with patch(
                "src.api.auth_router.exchange_google_code",
                new_callable=AsyncMock,
                return_value={
                    "id": "goog-ios",
                    "email": unique_email,
                    "name": "iOS User",
                },
            ):
                resp = await client.get(
                    f"/api/v1/auth/google/callback?code=valid&state={state}"
                )
                assert resp.status_code == 307
                location = resp.headers["location"]
                assert location.startswith("com.agentgraph.ios://")
        finally:
            settings.google_client_id = None
            settings.google_client_secret = None


# ---------------------------------------------------------------------------
# GitHub OAuth — /api/v1/auth/github
# ---------------------------------------------------------------------------


class TestGitHubOAuthRedirect:
    """GET /api/v1/auth/github returns a redirect to GitHub consent screen."""

    @pytest.mark.asyncio
    async def test_redirect_contains_state_and_client_id(self, client: AsyncClient):
        settings.github_client_id = "test-github-id"
        settings.github_client_secret = "test-github-secret"
        try:
            resp = await client.get("/api/v1/auth/github")
            assert resp.status_code == 307
            location = resp.headers["location"]
            assert "github.com/login/oauth/authorize" in location
            assert "client_id=test-github-id" in location
            assert "state=" in location
        finally:
            settings.github_client_id = None
            settings.github_client_secret = None

    @pytest.mark.asyncio
    async def test_returns_501_when_not_configured(self, client: AsyncClient):
        settings.github_client_id = None
        resp = await client.get("/api/v1/auth/github")
        assert resp.status_code == 501
        assert "not configured" in resp.json()["detail"]


class TestGitHubOAuthCallback:
    """GET /api/v1/auth/github/callback — state validation and user handling."""

    @pytest.mark.asyncio
    async def test_missing_state_returns_400(self, client: AsyncClient):
        settings.github_client_id = "test-github-id"
        settings.github_client_secret = "test-github-secret"
        try:
            resp = await client.get(
                "/api/v1/auth/github/callback?code=fake-code"
            )
            assert resp.status_code == 400
            assert "Missing OAuth state" in resp.json()["detail"]
        finally:
            settings.github_client_id = None
            settings.github_client_secret = None

    @pytest.mark.asyncio
    async def test_invalid_state_format_returns_400(self, client: AsyncClient):
        settings.github_client_id = "test-github-id"
        settings.github_client_secret = "test-github-secret"
        try:
            resp = await client.get(
                "/api/v1/auth/github/callback?code=fake&state=login:bad"
            )
            assert resp.status_code == 400
            assert "Invalid OAuth state" in resp.json()["detail"]
        finally:
            settings.github_client_id = None
            settings.github_client_secret = None

    @pytest.mark.asyncio
    async def test_invalid_hmac_signature_returns_400(self, client: AsyncClient):
        settings.github_client_id = "test-github-id"
        settings.github_client_secret = "test-github-secret"
        try:
            ts = str(int(time.time()))
            bad_state = f"login:{ts}::{'b' * 32}"
            resp = await client.get(
                f"/api/v1/auth/github/callback?code=fake&state={bad_state}"
            )
            assert resp.status_code == 400
            assert "Invalid OAuth state signature" in resp.json()["detail"]
        finally:
            settings.github_client_id = None
            settings.github_client_secret = None

    @pytest.mark.asyncio
    async def test_expired_state_returns_400(self, client: AsyncClient):
        settings.github_client_id = "test-github-id"
        settings.github_client_secret = "test-github-secret"
        try:
            expired_state = _make_github_state(ts=int(time.time()) - 1200)
            resp = await client.get(
                f"/api/v1/auth/github/callback?code=fake&state={expired_state}"
            )
            assert resp.status_code == 400
            assert "expired" in resp.json()["detail"].lower()
        finally:
            settings.github_client_id = None
            settings.github_client_secret = None

    @pytest.mark.asyncio
    async def test_github_exchange_failure_returns_400(self, client: AsyncClient):
        settings.github_client_id = "test-github-id"
        settings.github_client_secret = "test-github-secret"
        try:
            state = _make_github_state()
            with patch(
                "src.api.auth_router.exchange_github_code",
                new_callable=AsyncMock,
                return_value=None,
            ):
                resp = await client.get(
                    f"/api/v1/auth/github/callback?code=bad&state={state}"
                )
                assert resp.status_code == 400
                assert "GitHub authentication failed" in resp.json()["detail"]
        finally:
            settings.github_client_id = None
            settings.github_client_secret = None

    @pytest.mark.asyncio
    async def test_github_no_email_returns_400(self, client: AsyncClient):
        settings.github_client_id = "test-github-id"
        settings.github_client_secret = "test-github-secret"
        try:
            state = _make_github_state()
            with patch(
                "src.api.auth_router.exchange_github_code",
                new_callable=AsyncMock,
                return_value={
                    "id": 12345,
                    "login": "noemaildude",
                    "name": "No Email",
                    "avatar_url": None,
                },
            ), patch(
                "src.api.auth_router.fetch_github_email",
                new_callable=AsyncMock,
                return_value=None,
            ):
                resp = await client.get(
                    f"/api/v1/auth/github/callback?code=ok&state={state}"
                )
                assert resp.status_code == 400
                assert "no verified email" in resp.json()["detail"].lower()
        finally:
            settings.github_client_id = None
            settings.github_client_secret = None

    @pytest.mark.asyncio
    async def test_successful_new_user_registration(self, client: AsyncClient):
        """Successful GitHub callback with a new email creates an account."""
        settings.github_client_id = "test-github-id"
        settings.github_client_secret = "test-github-secret"
        try:
            state = _make_github_state()
            unique_email = f"github-new-{uuid.uuid4().hex[:8]}@example.com"
            with patch(
                "src.api.auth_router.exchange_github_code",
                new_callable=AsyncMock,
                return_value={
                    "id": 54321,
                    "login": "ghuser",
                    "name": "GitHub User",
                    "avatar_url": "https://avatars.githubusercontent.com/u/54321",
                    "email": unique_email,
                    "_access_token": "gho_faketoken",
                },
            ):
                resp = await client.get(
                    f"/api/v1/auth/github/callback?code=valid&state={state}"
                )
                assert resp.status_code == 307
                location = resp.headers["location"]
                assert "access_token=" in location
                assert "refresh_token=" in location
        finally:
            settings.github_client_id = None
            settings.github_client_secret = None

    @pytest.mark.asyncio
    async def test_successful_existing_user_login(self, client: AsyncClient, db):
        """GitHub callback with existing email logs in the user."""
        from src.models import Entity, EntityType

        settings.github_client_id = "test-github-id"
        settings.github_client_secret = "test-github-secret"

        existing_email = f"github-exist-{uuid.uuid4().hex[:8]}@example.com"
        gh_entity_id = uuid.uuid4()
        entity = Entity(
            id=gh_entity_id,
            type=EntityType.HUMAN,
            email=existing_email,
            password_hash="hashed",
            display_name="Existing GH User",
            email_verified=True,
            is_active=True,
            did_web=f"did:web:agentgraph.co:users:{gh_entity_id}",
        )
        db.add(entity)
        await db.flush()

        try:
            state = _make_github_state()
            with patch(
                "src.api.auth_router.exchange_github_code",
                new_callable=AsyncMock,
                return_value={
                    "id": 77777,
                    "login": "existinggh",
                    "name": "Existing GH User",
                    "avatar_url": None,
                    "email": existing_email,
                    "_access_token": "gho_faketoken",
                },
            ):
                resp = await client.get(
                    f"/api/v1/auth/github/callback?code=valid&state={state}"
                )
                assert resp.status_code == 307
                location = resp.headers["location"]
                assert "access_token=" in location
        finally:
            settings.github_client_id = None
            settings.github_client_secret = None

    @pytest.mark.asyncio
    async def test_email_fetched_from_api_when_not_in_profile(
        self, client: AsyncClient,
    ):
        """When GitHub profile has no email, fetch_github_email is called."""
        settings.github_client_id = "test-github-id"
        settings.github_client_secret = "test-github-secret"
        try:
            state = _make_github_state()
            fallback_email = f"gh-fallback-{uuid.uuid4().hex[:8]}@example.com"
            with patch(
                "src.api.auth_router.exchange_github_code",
                new_callable=AsyncMock,
                return_value={
                    "id": 11111,
                    "login": "noemail",
                    "name": "No Email Profile",
                    "avatar_url": None,
                    # No "email" key — simulates private email
                    "_access_token": "gho_faketoken",
                },
            ), patch(
                "src.api.auth_router.fetch_github_email",
                new_callable=AsyncMock,
                return_value=fallback_email,
            ):
                resp = await client.get(
                    f"/api/v1/auth/github/callback?code=valid&state={state}"
                )
                assert resp.status_code == 307
                assert "access_token=" in resp.headers["location"]
        finally:
            settings.github_client_id = None
            settings.github_client_secret = None

    @pytest.mark.asyncio
    async def test_deactivated_user_returns_403(self, client: AsyncClient, db):
        """GitHub login for a deactivated account returns 403."""
        from src.models import Entity, EntityType

        settings.github_client_id = "test-github-id"
        settings.github_client_secret = "test-github-secret"

        deactivated_email = f"gh-deact-{uuid.uuid4().hex[:8]}@example.com"
        gh_deact_id = uuid.uuid4()
        entity = Entity(
            id=gh_deact_id,
            type=EntityType.HUMAN,
            email=deactivated_email,
            password_hash="hashed",
            display_name="Deactivated GH",
            email_verified=True,
            is_active=False,
            did_web=f"did:web:agentgraph.co:users:{gh_deact_id}",
        )
        db.add(entity)
        await db.flush()

        try:
            state = _make_github_state()
            with patch(
                "src.api.auth_router.exchange_github_code",
                new_callable=AsyncMock,
                return_value={
                    "id": 88888,
                    "login": "deactgh",
                    "name": "Deactivated GH",
                    "avatar_url": None,
                    "email": deactivated_email,
                    "_access_token": "gho_faketoken",
                },
            ):
                resp = await client.get(
                    f"/api/v1/auth/github/callback?code=valid&state={state}"
                )
                assert resp.status_code == 403
                assert "deactivated" in resp.json()["detail"].lower()
        finally:
            settings.github_client_id = None
            settings.github_client_secret = None

    @pytest.mark.asyncio
    async def test_ios_platform_redirects_to_custom_scheme(
        self, client: AsyncClient,
    ):
        """GitHub callback with platform=ios redirects to custom URL scheme."""
        settings.github_client_id = "test-github-id"
        settings.github_client_secret = "test-github-secret"
        try:
            state = _make_github_state(platform="ios")
            unique_email = f"gh-ios-{uuid.uuid4().hex[:8]}@example.com"
            with patch(
                "src.api.auth_router.exchange_github_code",
                new_callable=AsyncMock,
                return_value={
                    "id": 99999,
                    "login": "iosgh",
                    "name": "iOS GH User",
                    "avatar_url": None,
                    "email": unique_email,
                    "_access_token": "gho_faketoken",
                },
            ):
                resp = await client.get(
                    f"/api/v1/auth/github/callback?code=valid&state={state}"
                )
                assert resp.status_code == 307
                location = resp.headers["location"]
                assert location.startswith("com.agentgraph.ios://")
        finally:
            settings.github_client_id = None
            settings.github_client_secret = None

    @pytest.mark.asyncio
    async def test_non_login_state_routes_to_linking(self, client: AsyncClient):
        """State not starting with 'login:' routes to linked-accounts handler."""
        settings.github_client_id = "test-github-id"
        settings.github_client_secret = "test-github-secret"
        try:
            # A state that doesn't start with "login:" triggers account linking
            resp = await client.get(
                "/api/v1/auth/github/callback?code=fake&state=link:something:sig"
            )
            # Should not return 501 (that would mean the route didn't match)
            # The linked-accounts handler will validate and likely reject
            assert resp.status_code != 501
        finally:
            settings.github_client_id = None
            settings.github_client_secret = None
