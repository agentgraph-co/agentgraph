from __future__ import annotations

import re

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
VERIFY_URL = "/api/v1/auth/verify-email"
RESEND_URL = "/api/v1/auth/resend-verification"

USER = {
    "email": "verify@test.com",
    "password": "Str0ngP@ss",
    "display_name": "VerifyUser",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _extract_token(message: str) -> str:
    """Extract verification token from registration message."""
    match = re.search(r"Verification token: (\S+)", message)
    assert match is not None, f"No token found in: {message}"
    return match.group(1)


@pytest.mark.asyncio
async def test_register_returns_verification_token(client: AsyncClient):
    resp = await client.post(REGISTER_URL, json=USER)
    assert resp.status_code == 201
    data = resp.json()
    assert "Verification token:" in data["message"]
    token = _extract_token(data["message"])
    assert len(token) > 20


@pytest.mark.asyncio
async def test_verify_email(client: AsyncClient):
    # Register
    resp = await client.post(REGISTER_URL, json=USER)
    v_token = _extract_token(resp.json()["message"])

    # Verify email
    resp = await client.post(VERIFY_URL, params={"token": v_token})
    assert resp.status_code == 200
    assert "verified" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_verify_invalid_token(client: AsyncClient):
    resp = await client.post(VERIFY_URL, params={"token": "bad-token"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_verify_token_cannot_be_reused(client: AsyncClient):
    resp = await client.post(REGISTER_URL, json=USER)
    v_token = _extract_token(resp.json()["message"])

    # First use — success
    resp = await client.post(VERIFY_URL, params={"token": v_token})
    assert resp.status_code == 200

    # Second use — fail
    resp = await client.post(VERIFY_URL, params={"token": v_token})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resend_verification(client: AsyncClient):
    resp = await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL, json={"email": USER["email"], "password": USER["password"]},
    )
    jwt_token = resp.json()["access_token"]

    resp = await client.post(RESEND_URL, headers=_auth(jwt_token))
    assert resp.status_code == 200
    assert "Verification token:" in resp.json()["message"]


@pytest.mark.asyncio
async def test_resend_after_verified_fails(client: AsyncClient):
    resp = await client.post(REGISTER_URL, json=USER)
    v_token = _extract_token(resp.json()["message"])

    # Verify email
    await client.post(VERIFY_URL, params={"token": v_token})

    # Login and try to resend
    resp = await client.post(
        LOGIN_URL, json={"email": USER["email"], "password": USER["password"]},
    )
    jwt_token = resp.json()["access_token"]

    resp = await client.post(RESEND_URL, headers=_auth(jwt_token))
    assert resp.status_code == 400
    assert "already verified" in resp.json()["detail"].lower()
