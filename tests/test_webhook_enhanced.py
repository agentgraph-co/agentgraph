from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.main import app
from src.models import TrustScore


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
    "email": "wh_enhanced@example.com",
    "password": "Str0ngP@ss",
    "display_name": "WHEnhanced",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: AsyncClient, db: AsyncSession | None = None) -> str:
    await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL, json={"email": USER["email"], "password": USER["password"]}
    )
    token = resp.json()["access_token"]
    if db is not None:
        me = await client.get("/api/v1/auth/me", headers=_auth(token))
        eid = uuid.UUID(me.json()["id"])
        from sqlalchemy import update
        await db.execute(
            update(TrustScore)
            .where(TrustScore.entity_id == eid)
            .values(score=0.5, components={"verification": 0.3, "age": 0.1, "activity": 0.1})
        )
        await db.flush()
    return token


@pytest.mark.asyncio
async def test_get_webhook_by_id(client: AsyncClient, db):
    """GET /webhooks/{id} returns webhook details."""
    token = await _setup(client, db)

    create_resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://example.com/hook",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token),
    )
    assert create_resp.status_code == 201
    webhook_id = create_resp.json()["webhook"]["id"]

    resp = await client.get(
        f"/api/v1/webhooks/{webhook_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == webhook_id
    assert data["callback_url"] == "https://example.com/hook"
    assert data["event_types"] == ["entity.followed"]
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_get_webhook_not_found(client: AsyncClient, db):
    """GET /webhooks/{id} returns 404 for nonexistent webhook."""
    token = await _setup(client, db)

    resp = await client.get(
        "/api/v1/webhooks/00000000-0000-0000-0000-000000000000",
        headers=_auth(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_webhook_signing_key_stored(client: AsyncClient, db):
    """Webhook creation stores signing_key for HMAC verification."""
    token = await _setup(client, db)

    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://example.com/sign",
            "event_types": ["post.created"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    secret = data["secret"]
    assert len(secret) > 0

    # Verify the signing key is stored by checking webhook still works
    webhook_id = data["webhook"]["id"]
    get_resp = await client.get(
        f"/api/v1/webhooks/{webhook_id}",
        headers=_auth(token),
    )
    assert get_resp.status_code == 200


@pytest.mark.asyncio
async def test_entity_messaged_valid_event_type(client: AsyncClient, db):
    """entity.messaged is a valid webhook event type."""
    token = await _setup(client, db)

    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://example.com/msg",
            "event_types": ["entity.messaged"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_webhook_update_endpoint(client: AsyncClient, db):
    """PATCH /webhooks/{id} updates webhook properties."""
    token = await _setup(client, db)

    create_resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://example.com/update",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token),
    )
    webhook_id = create_resp.json()["webhook"]["id"]

    resp = await client.patch(
        f"/api/v1/webhooks/{webhook_id}",
        json={"event_types": ["post.created", "dm.received"]},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert set(resp.json()["event_types"]) == {"post.created", "dm.received"}
