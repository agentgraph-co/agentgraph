"""Tests for Tasks #175-178: DID validation, webhook/marketplace rate limiting."""
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
ME_URL = "/api/v1/auth/me"
DID_URL = "/api/v1/did"

USER = {
    "email": "batch175@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch175",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_did_service_rejects_http_url(client, db):
    """DID update should reject http:// serviceEndpoint URLs."""
    token, entity_id = await _setup_user(client, USER)

    resp = await client.patch(
        f"{DID_URL}/entity/{entity_id}",
        json={
            "service": [
                {
                    "id": "did:web:test#api",
                    "type": "AgentAPI",
                    "serviceEndpoint": "http://insecure.example.com/api",
                }
            ],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_did_service_accepts_https_url(client, db):
    """DID update should accept https:// serviceEndpoint URLs."""
    token, entity_id = await _setup_user(client, USER)

    resp = await client.patch(
        f"{DID_URL}/entity/{entity_id}",
        json={
            "service": [
                {
                    "id": "did:web:test#api",
                    "type": "AgentAPI",
                    "serviceEndpoint": "https://secure.example.com/api",
                }
            ],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_did_service_rejects_too_long_endpoint(client, db):
    """DID update should reject serviceEndpoint over max_length."""
    token, entity_id = await _setup_user(client, USER)

    resp = await client.patch(
        f"{DID_URL}/entity/{entity_id}",
        json={
            "service": [
                {
                    "id": "did:web:test#api",
                    "type": "AgentAPI",
                    "serviceEndpoint": "https://example.com/" + "a" * 2100,
                }
            ],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422


# --- Task #177: Rate limiting on webhook and marketplace GET endpoints ---


@pytest.mark.asyncio
async def test_webhook_list_has_rate_limit(client, db):
    """GET /webhooks should have rate limit headers."""
    token, _ = await _setup_user(client, USER)

    resp = await client.get(
        "/api/v1/webhooks", headers=_auth(token),
    )
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers


@pytest.mark.asyncio
async def test_marketplace_purchase_history_has_rate_limit(client, db):
    """GET /marketplace/purchases/history should have rate limit headers."""
    token, _ = await _setup_user(client, USER)

    resp = await client.get(
        "/api/v1/marketplace/purchases/history", headers=_auth(token),
    )
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers
