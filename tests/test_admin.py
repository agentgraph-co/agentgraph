from __future__ import annotations

import uuid

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
ADMIN_URL = "/api/v1/admin"

USER = {
    "email": "user@admin.com",
    "password": "Str0ngP@ss",
    "display_name": "RegularUser",
}
ADMIN = {
    "email": "admin@admin.com",
    "password": "Str0ngP@ss",
    "display_name": "AdminUser",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register + login, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


async def _make_admin(db, entity_id: str):
    from src.models import Entity

    entity = await db.get(Entity, uuid.UUID(entity_id))
    entity.is_admin = True
    await db.flush()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Stats ---


@pytest.mark.asyncio
async def test_platform_stats(client: AsyncClient, db):
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)

    resp = await client.get(f"{ADMIN_URL}/stats", headers=_auth(admin_token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_entities"] >= 1
    assert data["total_humans"] >= 1
    assert "total_posts" in data
    assert "pending_moderation_flags" in data


@pytest.mark.asyncio
async def test_platform_stats_non_admin(client: AsyncClient):
    token, _ = await _setup_user(client, USER)

    resp = await client.get(f"{ADMIN_URL}/stats", headers=_auth(token))
    assert resp.status_code == 403


# --- Entity listing ---


@pytest.mark.asyncio
async def test_list_entities(client: AsyncClient, db):
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)
    await _setup_user(client, USER)

    resp = await client.get(f"{ADMIN_URL}/entities", headers=_auth(admin_token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    assert len(data["entities"]) >= 2


@pytest.mark.asyncio
async def test_list_entities_filter_type(client: AsyncClient, db):
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)

    resp = await client.get(
        f"{ADMIN_URL}/entities",
        params={"type": "human"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    for e in resp.json()["entities"]:
        assert e["type"] == "human"


# --- Deactivate/reactivate ---


@pytest.mark.asyncio
async def test_deactivate_entity(client: AsyncClient, db):
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)
    _, user_id = await _setup_user(client, USER)

    resp = await client.patch(
        f"{ADMIN_URL}/entities/{user_id}/deactivate",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert "deactivated" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_deactivate_self_fails(client: AsyncClient, db):
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)

    resp = await client.patch(
        f"{ADMIN_URL}/entities/{admin_id}/deactivate",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reactivate_entity(client: AsyncClient, db):
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)
    _, user_id = await _setup_user(client, USER)

    await client.patch(
        f"{ADMIN_URL}/entities/{user_id}/deactivate",
        headers=_auth(admin_token),
    )
    resp = await client.patch(
        f"{ADMIN_URL}/entities/{user_id}/reactivate",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert "reactivated" in resp.json()["message"].lower()


# --- Promote ---


@pytest.mark.asyncio
async def test_promote_to_admin(client: AsyncClient, db):
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)
    _, user_id = await _setup_user(client, USER)

    resp = await client.patch(
        f"{ADMIN_URL}/entities/{user_id}/promote",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert "promoted" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_promote_already_admin(client: AsyncClient, db):
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)

    resp = await client.patch(
        f"{ADMIN_URL}/entities/{admin_id}/promote",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 409
