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

USER = {
    "email": "privacy_tier@example.com",
    "password": "Str0ngP@ss",
    "display_name": "PrivacyUser",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: AsyncClient) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL,
        json={"email": USER["email"], "password": USER["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


@pytest.mark.asyncio
async def test_update_privacy_to_public(client: AsyncClient, db):
    """User can set privacy tier to public."""
    token, entity_id = await _setup(client)

    resp = await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"privacy_tier": "public"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["privacy_tier"] == "public"


@pytest.mark.asyncio
async def test_update_privacy_to_private(client: AsyncClient, db):
    """User can set privacy tier to private."""
    token, entity_id = await _setup(client)

    resp = await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"privacy_tier": "private"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["privacy_tier"] == "private"


@pytest.mark.asyncio
async def test_verified_tier_requires_email(client: AsyncClient, db):
    """Cannot set verified tier without verified email."""
    token, entity_id = await _setup(client)

    resp = await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"privacy_tier": "verified"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "email" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_verified_tier_with_verified_email(client: AsyncClient, db):
    """Can set verified tier with verified email."""
    token, entity_id = await _setup(client)

    # Verify email directly in DB
    from src.models import Entity
    entity = await db.get(Entity, entity_id)
    entity.email_verified = True
    await db.flush()

    resp = await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"privacy_tier": "verified"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["privacy_tier"] == "verified"
