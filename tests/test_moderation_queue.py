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
    "email": "modq_admin@example.com",
    "password": "Str0ngP@ss",
    "display_name": "ModQAdmin",
}
USER = {
    "email": "modq_user@example.com",
    "password": "Str0ngP@ss",
    "display_name": "ModQUser",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


async def _make_admin(db, email: str):
    from sqlalchemy import select

    from src.models import Entity

    result = await db.execute(select(Entity).where(Entity.email == email))
    entity = result.scalar_one()
    entity.is_admin = True
    await db.flush()


@pytest.mark.asyncio
async def test_flags_pagination(client: AsyncClient, db):
    """Flag listing supports pagination with offset/limit."""
    admin_token, _ = await _setup(client, ADMIN)
    await _make_admin(db, ADMIN["email"])
    user_token, user_id = await _setup(client, USER)

    # Admin flags user
    flag_resp = await client.post(
        "/api/v1/moderation/flag",
        json={
            "target_type": "entity",
            "target_id": user_id,
            "reason": "spam",
            "details": "Spamming posts",
        },
        headers=_auth(admin_token),
    )
    assert flag_resp.status_code == 201

    resp = await client.get(
        "/api/v1/moderation/flags",
        params={"limit": 10, "offset": 0},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "has_more" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_flags_filter_by_status(client: AsyncClient, db):
    """Flag listing supports filtering by status."""
    admin_token, _ = await _setup(client, ADMIN)
    await _make_admin(db, ADMIN["email"])

    resp = await client.get(
        "/api/v1/moderation/flags",
        params={"status": "pending"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_stats_detailed_breakdown(client: AsyncClient, db):
    """Moderation stats include reason and status breakdowns."""
    admin_token, _ = await _setup(client, ADMIN)
    await _make_admin(db, ADMIN["email"])
    user_token, user_id = await _setup(client, USER)

    # Admin flags user
    flag_resp = await client.post(
        "/api/v1/moderation/flag",
        json={
            "target_type": "entity",
            "target_id": user_id,
            "reason": "spam",
        },
        headers=_auth(admin_token),
    )
    assert flag_resp.status_code == 201

    resp = await client.get(
        "/api/v1/moderation/stats", headers=_auth(admin_token)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "by_reason" in data
    assert "by_status" in data
    assert "by_target_type" in data
    assert data["total_flags"] >= 1


@pytest.mark.asyncio
async def test_non_admin_cannot_view_stats(client: AsyncClient, db):
    """Non-admins cannot access moderation stats."""
    user_token, _ = await _setup(client, USER)

    resp = await client.get(
        "/api/v1/moderation/stats", headers=_auth(user_token)
    )
    assert resp.status_code == 403
