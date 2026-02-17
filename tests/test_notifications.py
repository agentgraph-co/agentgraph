from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.notification_router import create_notification
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
NOTIF_URL = "/api/v1/notifications"

USER = {
    "email": "notif@test.com",
    "password": "Str0ngP@ss",
    "display_name": "NotifUser",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_empty_notifications(client: AsyncClient):
    token, _ = await _setup_user(client, USER)

    resp = await client.get(NOTIF_URL, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_notification_appears(client: AsyncClient, db):
    token, entity_id = await _setup_user(client, USER)

    await create_notification(
        db,
        uuid.UUID(entity_id),
        kind="follow",
        title="New follower",
        body="Someone followed you",
    )

    resp = await client.get(NOTIF_URL, headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["unread_count"] == 1
    assert data["notifications"][0]["kind"] == "follow"


@pytest.mark.asyncio
async def test_mark_as_read(client: AsyncClient, db):
    token, entity_id = await _setup_user(client, USER)

    notif = await create_notification(
        db,
        uuid.UUID(entity_id),
        kind="reply",
        title="New reply",
        body="Someone replied to your post",
    )

    resp = await client.post(
        f"{NOTIF_URL}/{notif.id}/read", headers=_auth(token)
    )
    assert resp.status_code == 200

    # Check it's now read
    resp = await client.get(NOTIF_URL, headers=_auth(token))
    assert resp.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_mark_all_as_read(client: AsyncClient, db):
    token, entity_id = await _setup_user(client, USER)

    eid = uuid.UUID(entity_id)
    await create_notification(db, eid, kind="follow", title="F1", body="Follow 1")
    await create_notification(db, eid, kind="follow", title="F2", body="Follow 2")
    await create_notification(db, eid, kind="follow", title="F3", body="Follow 3")

    resp = await client.post(f"{NOTIF_URL}/read-all", headers=_auth(token))
    assert resp.status_code == 200
    assert "3" in resp.json()["message"]

    resp = await client.get(NOTIF_URL, headers=_auth(token))
    assert resp.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_unread_count_endpoint(client: AsyncClient, db):
    token, entity_id = await _setup_user(client, USER)

    eid = uuid.UUID(entity_id)
    await create_notification(db, eid, kind="vote", title="Vote", body="Upvote")
    await create_notification(db, eid, kind="vote", title="Vote", body="Upvote")

    resp = await client.get(f"{NOTIF_URL}/unread-count", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["unread_count"] == 2


@pytest.mark.asyncio
async def test_unread_only_filter(client: AsyncClient, db):
    token, entity_id = await _setup_user(client, USER)

    eid = uuid.UUID(entity_id)
    n1 = await create_notification(
        db, eid, kind="follow", title="F1", body="Follow 1",
    )
    await create_notification(
        db, eid, kind="follow", title="F2", body="Follow 2",
    )

    # Mark first as read
    await client.post(f"{NOTIF_URL}/{n1.id}/read", headers=_auth(token))

    resp = await client.get(
        NOTIF_URL, params={"unread_only": True}, headers=_auth(token)
    )
    assert resp.status_code == 200
    assert len(resp.json()["notifications"]) == 1


@pytest.mark.asyncio
async def test_mark_nonexistent_notification(client: AsyncClient):
    token, _ = await _setup_user(client, USER)

    fake_id = uuid.uuid4()
    resp = await client.post(
        f"{NOTIF_URL}/{fake_id}/read", headers=_auth(token)
    )
    assert resp.status_code == 404
