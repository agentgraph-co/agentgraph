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
WEBHOOKS_URL = "/api/v1/webhooks"

USER = {
    "email": "webhook@test.com",
    "password": "Str0ngP@ss",
    "display_name": "WebhookUser",
}


async def _setup_user(
    client: AsyncClient, user: dict, db: AsyncSession | None = None,
) -> str:
    """Register + login, return token."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    if db is not None:
        me = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
        )
        eid = uuid.UUID(me.json()["id"])
        db.add(TrustScore(
            id=uuid.uuid4(), entity_id=eid, score=0.5,
            components={"verification": 0.3, "age": 0.1, "activity": 0.1},
        ))
        await db.flush()
    return token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Webhook CRUD tests ---


@pytest.mark.asyncio
async def test_create_webhook(client: AsyncClient, db):
    token = await _setup_user(client, USER, db)
    resp = await client.post(
        WEBHOOKS_URL,
        json={
            "callback_url": "https://example.com/webhook",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "secret" in data
    assert len(data["secret"]) > 0
    assert data["webhook"]["is_active"] is True
    assert data["webhook"]["event_types"] == ["entity.followed"]


@pytest.mark.asyncio
async def test_create_webhook_invalid_event_type(client: AsyncClient, db):
    token = await _setup_user(client, USER, db)
    resp = await client.post(
        WEBHOOKS_URL,
        json={
            "callback_url": "https://example.com/webhook",
            "event_types": ["invalid.event"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "Invalid event types" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_webhooks(client: AsyncClient, db):
    token = await _setup_user(client, USER, db)

    # Create two webhooks
    await client.post(
        WEBHOOKS_URL,
        json={
            "callback_url": "https://example.com/hook1",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token),
    )
    await client.post(
        WEBHOOKS_URL,
        json={
            "callback_url": "https://example.com/hook2",
            "event_types": ["post.replied"],
        },
        headers=_auth(token),
    )

    resp = await client.get(WEBHOOKS_URL, headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2


@pytest.mark.asyncio
async def test_delete_webhook(client: AsyncClient, db):
    token = await _setup_user(client, USER, db)
    create_resp = await client.post(
        WEBHOOKS_URL,
        json={
            "callback_url": "https://example.com/webhook",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token),
    )
    webhook_id = create_resp.json()["webhook"]["id"]

    resp = await client.delete(
        f"{WEBHOOKS_URL}/{webhook_id}", headers=_auth(token)
    )
    assert resp.status_code == 204

    # Verify it's gone
    list_resp = await client.get(WEBHOOKS_URL, headers=_auth(token))
    assert list_resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_deactivate_and_reactivate_webhook(client: AsyncClient, db):
    token = await _setup_user(client, USER, db)
    create_resp = await client.post(
        WEBHOOKS_URL,
        json={
            "callback_url": "https://example.com/webhook",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token),
    )
    webhook_id = create_resp.json()["webhook"]["id"]

    # Deactivate
    resp = await client.patch(
        f"{WEBHOOKS_URL}/{webhook_id}/deactivate", headers=_auth(token)
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Reactivate
    resp = await client.patch(
        f"{WEBHOOKS_URL}/{webhook_id}/activate", headers=_auth(token)
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


@pytest.mark.asyncio
async def test_webhook_unauthenticated(client: AsyncClient):
    resp = await client.post(
        WEBHOOKS_URL,
        json={
            "callback_url": "https://example.com/webhook",
            "event_types": ["entity.followed"],
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_other_users_webhook(client: AsyncClient, db):
    token_a = await _setup_user(client, USER, db)
    token_b = await _setup_user(
        client,
        {"email": "other@test.com", "password": "Str0ngP@ss", "display_name": "Other"},
        db,
    )

    create_resp = await client.post(
        WEBHOOKS_URL,
        json={
            "callback_url": "https://example.com/webhook",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token_a),
    )
    webhook_id = create_resp.json()["webhook"]["id"]

    # User B should not be able to delete User A's webhook
    resp = await client.delete(
        f"{WEBHOOKS_URL}/{webhook_id}", headers=_auth(token_b)
    )
    assert resp.status_code == 404
