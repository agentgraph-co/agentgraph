from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.database import get_db
from src.main import app
from src.models import EmailVerification


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


async def _get_latest_verification_token(db) -> str:
    """Fetch the most recent unused verification token from the DB."""
    result = await db.execute(
        select(EmailVerification)
        .where(EmailVerification.is_used.is_(False))
        .order_by(EmailVerification.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one()
    return record.token


@pytest.mark.asyncio
async def test_register_returns_verification_token(client: AsyncClient, db):
    resp = await client.post(REGISTER_URL, json=USER)
    assert resp.status_code == 201
    data = resp.json()
    msg = data["message"].lower()
    assert "check your email" in msg or "verification" in msg

    # Verify token was created in DB
    token = await _get_latest_verification_token(db)
    assert len(token) > 20


@pytest.mark.asyncio
async def test_verify_email(client: AsyncClient, db):
    # Register
    await client.post(REGISTER_URL, json=USER)
    v_token = await _get_latest_verification_token(db)

    # Verify email
    resp = await client.post(VERIFY_URL, params={"token": v_token})
    assert resp.status_code == 200
    assert "verified" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_verify_invalid_token(client: AsyncClient):
    resp = await client.post(VERIFY_URL, params={"token": "bad-token"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_verify_token_cannot_be_reused(client: AsyncClient, db):
    await client.post(REGISTER_URL, json=USER)
    v_token = await _get_latest_verification_token(db)

    # First use — success
    resp = await client.post(VERIFY_URL, params={"token": v_token})
    assert resp.status_code == 200

    # Second use — fail
    resp = await client.post(VERIFY_URL, params={"token": v_token})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resend_verification(client: AsyncClient, db):
    await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL, json={"email": USER["email"], "password": USER["password"]},
    )
    jwt_token = resp.json()["access_token"]

    resp = await client.post(RESEND_URL, headers=_auth(jwt_token))
    assert resp.status_code == 200
    msg = resp.json()["message"].lower()
    assert "email" in msg or "verification" in msg


@pytest.mark.asyncio
async def test_resend_after_verified_fails(client: AsyncClient, db):
    await client.post(REGISTER_URL, json=USER)
    v_token = await _get_latest_verification_token(db)

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
