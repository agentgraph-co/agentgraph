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

ADMIN = {
    "email": "cleanup_admin@example.com",
    "password": "Str0ngP@ss",
    "display_name": "CleanupAdmin",
}
USER = {
    "email": "cleanup_user@example.com",
    "password": "Str0ngP@ss",
    "display_name": "CleanupUser",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_admin(db, email: str):
    from sqlalchemy import select

    from src.models import Entity

    result = await db.execute(select(Entity).where(Entity.email == email))
    entity = result.scalar_one()
    entity.is_admin = True
    await db.flush()


async def _setup_admin(client: AsyncClient, db) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=ADMIN)
    resp = await client.post(
        LOGIN_URL, json={"email": ADMIN["email"], "password": ADMIN["password"]}
    )
    token = resp.json()["access_token"]
    await _make_admin(db, ADMIN["email"])
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


async def _setup_user(client: AsyncClient) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL, json={"email": USER["email"], "password": USER["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


@pytest.mark.asyncio
async def test_export_has_rate_limit(client: AsyncClient, db):
    """Export endpoint is rate limited."""
    token, _ = await _setup_user(client)

    resp = await client.get("/api/v1/export/me", headers=_auth(token))
    assert resp.status_code == 200
    # Should have rate limit headers
    assert "X-RateLimit-Limit" in resp.headers


@pytest.mark.asyncio
async def test_admin_cleanup_token_blacklist(client: AsyncClient, db):
    """Admin can run token blacklist cleanup."""
    admin_token, _ = await _setup_admin(client, db)

    resp = await client.post(
        "/api/v1/admin/cleanup/token-blacklist",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert "removed" in resp.json()


@pytest.mark.asyncio
async def test_non_admin_cannot_cleanup(client: AsyncClient, db):
    """Non-admin users cannot run cleanup."""
    token, _ = await _setup_user(client)

    resp = await client.post(
        "/api/v1/admin/cleanup/token-blacklist",
        headers=_auth(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_old_verification_tokens_invalidated(client: AsyncClient, db):
    """Creating a new verification token invalidates old ones."""
    from src.api.auth_service import create_verification_token, verify_email_token

    # Register user
    await client.post(REGISTER_URL, json=USER)
    from sqlalchemy import select

    from src.models import Entity

    result = await db.execute(select(Entity).where(Entity.email == USER["email"]))
    entity = result.scalar_one()

    # Create first token
    token1 = await create_verification_token(db, entity.id)

    # Create second token (should invalidate first)
    token2 = await create_verification_token(db, entity.id)

    # First token should no longer work
    result1 = await verify_email_token(db, token1)
    assert result1 is None

    # Second token should work
    result2 = await verify_email_token(db, token2)
    assert result2 is not None
    assert result2.id == entity.id
