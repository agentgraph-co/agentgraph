from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.database import get_db
from src.main import app
from src.models import PasswordResetToken


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

USER = {
    "email": "sectest@example.com",
    "password": "Str0ngP@ss",
    "display_name": "SecTester",
}
USER_B = {
    "email": "sectest_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "SecTesterB",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    data = resp.json()
    token = data["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


# --- Password Reset Tests ---


async def _get_latest_reset_token(db) -> str:
    """Fetch the most recent unused password reset token from the DB."""
    result = await db.execute(
        select(PasswordResetToken)
        .where(PasswordResetToken.is_used.is_(False))
        .order_by(PasswordResetToken.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one()
    return record.token


@pytest.mark.asyncio
async def test_forgot_password_returns_token(client: AsyncClient, db):
    """Forgot password creates a reset token (sent via email)."""
    await _setup_user(client, USER)

    resp = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": USER["email"]},
    )
    assert resp.status_code == 200

    # Verify token was created in DB
    token = await _get_latest_reset_token(db)
    assert len(token) > 20


@pytest.mark.asyncio
async def test_forgot_password_nonexistent_email(client: AsyncClient, db):
    """Forgot password with unknown email still returns 200 (no enumeration)."""
    resp = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nonexistent@example.com"},
    )
    assert resp.status_code == 200
    # Should NOT contain "token:" — no reset token generated
    assert "token:" not in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_reset_password_flow(client: AsyncClient, db):
    """Full password reset flow: forgot → reset → login with new password."""
    await _setup_user(client, USER)

    # Request reset
    resp = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": USER["email"]},
    )
    assert resp.status_code == 200

    # Fetch token from DB
    token = await _get_latest_reset_token(db)
    assert token is not None

    # Reset password
    new_password = "NewStr0ngP@ss"
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": new_password},
    )
    assert resp.status_code == 200

    # Login with new password
    resp = await client.post(
        LOGIN_URL, json={"email": USER["email"], "password": new_password},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()

    # Old password should fail
    resp = await client.post(
        LOGIN_URL, json={"email": USER["email"], "password": USER["password"]},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_reset_token_single_use(client: AsyncClient, db):
    """Reset token cannot be reused."""
    await _setup_user(client, USER)

    await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": USER["email"]},
    )
    token = await _get_latest_reset_token(db)

    # Use it once
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "NewStr0ngP@ss"},
    )
    assert resp.status_code == 200

    # Try to use it again
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "AnotherP@ss1"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reset_invalid_token(client: AsyncClient, db):
    """Invalid reset token returns 400."""
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "invalid-token", "new_password": "NewStr0ngP@ss"},
    )
    assert resp.status_code == 400


# --- JWT Logout Tests ---


@pytest.mark.asyncio
async def test_logout(client: AsyncClient, db):
    """Logout revokes the current access token."""
    token, _ = await _setup_user(client, USER)

    # Verify token works
    resp = await client.get("/api/v1/auth/me", headers=_auth(token))
    assert resp.status_code == 200

    # Logout
    resp = await client.post("/api/v1/auth/logout", headers=_auth(token))
    assert resp.status_code == 200

    # Token should now be revoked
    resp = await client.get("/api/v1/auth/me", headers=_auth(token))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_doesnt_affect_other_tokens(client: AsyncClient, db):
    """Logging out with one token doesn't invalidate another."""
    await client.post(REGISTER_URL, json=USER)

    # Get two tokens
    resp1 = await client.post(
        LOGIN_URL, json={"email": USER["email"], "password": USER["password"]},
    )
    token1 = resp1.json()["access_token"]

    resp2 = await client.post(
        LOGIN_URL, json={"email": USER["email"], "password": USER["password"]},
    )
    token2 = resp2.json()["access_token"]

    # Logout with token1
    await client.post("/api/v1/auth/logout", headers=_auth(token1))

    # token2 should still work
    resp = await client.get("/api/v1/auth/me", headers=_auth(token2))
    assert resp.status_code == 200


# --- Content Filter Tests ---


@pytest.mark.asyncio
async def test_dm_content_filtered(client: AsyncClient, db):
    """DM content is filtered for spam/abuse."""
    token_a, _ = await _setup_user(client, USER)
    _, id_b = await _setup_user(client, USER_B)

    # Try sending spam content
    resp = await client.post(
        "/api/v1/messages",
        json={
            "recipient_id": id_b,
            "content": (
                "BUY NOW!!! FREE MONEY!!! http://spam.com "
                "http://spam2.com http://spam3.com http://spam4.com "
                "http://spam5.com http://spam6.com"
            ),
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "rejected" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_dm_normal_content_passes(client: AsyncClient, db):
    """Normal DM content passes the content filter."""
    token_a, _ = await _setup_user(client, USER)
    _, id_b = await _setup_user(client, USER_B)

    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "Hey, how are you doing?"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
