"""Tests for Tasks #169-170: auth register content filtering,
rate limiting on auth refresh/me/logout."""
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

USER_A = {
    "email": "batch169a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch169A",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    data = resp.json()
    token = data["access_token"]
    refresh = data.get("refresh_token", "")
    await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, refresh


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Task #169: Content filtering on registration display_name ---


@pytest.mark.asyncio
async def test_register_spam_display_name_rejected(client, db):
    """Registration with spam display name should be rejected."""
    resp = await client.post(
        REGISTER_URL,
        json={
            "email": "spammer169@test.com",
            "password": "Str0ngP@ss",
            "display_name": "Buy cheap viagra click here",
        },
    )
    assert resp.status_code == 400
    assert "display name rejected" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_clean_display_name_accepted(client, db):
    """Registration with clean display name should succeed."""
    resp = await client.post(
        REGISTER_URL,
        json={
            "email": "clean169@test.com",
            "password": "Str0ngP@ss",
            "display_name": "NormalUser",
        },
    )
    assert resp.status_code == 201


# --- Task #170: Rate limiting on auth endpoints ---


@pytest.mark.asyncio
async def test_auth_me_has_rate_limit_headers(client, db):
    """GET /auth/me should have rate limit headers."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.get(
        ME_URL, headers=_auth(token),
    )
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers


@pytest.mark.asyncio
async def test_auth_refresh_has_rate_limit_headers(client, db):
    """POST /auth/refresh should have rate limit headers."""
    token, refresh_token = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers


@pytest.mark.asyncio
async def test_auth_logout_has_rate_limit_headers(client, db):
    """POST /auth/logout should have rate limit headers."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/auth/logout",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers
