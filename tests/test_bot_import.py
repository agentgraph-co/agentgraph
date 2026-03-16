"""Tests for bot source import endpoints."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"

AUTH_USER = {
    "email": "bot_import_user@example.com",
    "password": "Str0ngP@ss",
    "display_name": "BotImportUser",
}


async def _get_auth_headers(client: AsyncClient) -> dict:
    """Register and log in a user, return Authorization headers."""
    await client.post(REGISTER_URL, json=AUTH_USER)
    resp = await client.post(LOGIN_URL, json={
        "email": AUTH_USER["email"],
        "password": AUTH_USER["password"],
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def auth_client(client):
    """An AsyncClient with authentication headers set."""
    headers = await _get_auth_headers(client)
    client.headers.update(headers)
    yield client


@pytest.mark.asyncio
class TestSourcePreview:
    async def test_preview_invalid_url(self, client: AsyncClient):
        resp = await client.post("/api/v1/bots/preview-source", json={
            "source_url": "not-a-url",
        })
        assert resp.status_code == 400

    async def test_preview_private_url(self, client: AsyncClient):
        resp = await client.post("/api/v1/bots/preview-source", json={
            "source_url": "http://localhost:8000/secret",
        })
        assert resp.status_code == 400

    async def test_preview_unsupported_url(self, client: AsyncClient):
        resp = await client.post("/api/v1/bots/preview-source", json={
            "source_url": "https://example.com/random",
        })
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestImportSource:
    async def test_import_invalid_url(self, client: AsyncClient):
        resp = await client.post("/api/v1/bots/import-source", json={
            "source_url": "not-a-url",
        })
        assert resp.status_code == 400

    async def test_import_unsupported_url(self, client: AsyncClient):
        resp = await client.post("/api/v1/bots/import-source", json={
            "source_url": "https://example.com/random",
        })
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestBootstrapAutoOwn:
    async def test_bootstrap_with_auth_auto_owns(self, auth_client: AsyncClient):
        """Authenticated users should auto-own bots without operator_email."""
        resp = await auth_client.post("/api/v1/bots/bootstrap", json={
            "display_name": "Auto-Owned Bot",
            "capabilities": ["test"],
        })
        assert resp.status_code == 201
        data = resp.json()
        # Should not be provisional since the user is authenticated
        assert data["claim_token"] is None

    async def test_bootstrap_without_auth_is_provisional(self, client: AsyncClient):
        """Unauthenticated bootstrap should create provisional agent."""
        resp = await client.post("/api/v1/bots/bootstrap", json={
            "display_name": "Provisional Bot",
            "capabilities": ["test"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["claim_token"] is not None


@pytest.mark.asyncio
class TestA2AImport:
    async def test_a2a_import_invalid_url(self, client: AsyncClient):
        resp = await client.post("/api/v1/a2a/agent-card/import", json={
            "card_url": "not-a-url",
        })
        assert resp.status_code == 400
