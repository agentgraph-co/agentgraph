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
    "email": "ipv6test@example.com",
    "password": "Str0ngP@ss",
    "display_name": "IPv6Tester",
}
ADMIN = {
    "email": "suspend_admin@example.com",
    "password": "Str0ngP@ss",
    "display_name": "SuspendAdmin",
}
SUSPENDED = {
    "email": "suspended@example.com",
    "password": "Str0ngP@ss",
    "display_name": "SuspendedUser",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _grant_trust(db, entity_id: str, score: float = 0.5):
    import uuid as _uuid

    from src.models import TrustScore
    ts = TrustScore(id=_uuid.uuid4(), entity_id=entity_id, score=score, components={})
    db.add(ts)
    await db.flush()


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


# --- IPv6 SSRF Tests ---


@pytest.mark.asyncio
async def test_avatar_rejects_ipv6_loopback(client: AsyncClient, db):
    """Avatar URL blocks IPv6 loopback ::1."""
    token, entity_id = await _setup(client, USER)

    resp = await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"avatar_url": "http://[::1]:8080/avatar.png"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_avatar_rejects_ipv6_link_local(client: AsyncClient, db):
    """Avatar URL blocks IPv6 link-local fe80:: addresses."""
    token, entity_id = await _setup(client, USER)

    resp = await client.patch(
        f"/api/v1/profiles/{entity_id}",
        json={"avatar_url": "http://[fe80::1]:8080/avatar.png"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_avatar_rejects_ipv6_private(client: AsyncClient, db):
    """Avatar URL blocks IPv6 private fc00::/fd addresses."""
    token, entity_id = await _setup(client, USER)

    for url in [
        "http://[fc00::1]/avatar.png",
        "http://[fd12:3456::1]/avatar.png",
    ]:
        resp = await client.patch(
            f"/api/v1/profiles/{entity_id}",
            json={"avatar_url": url},
            headers=_auth(token),
        )
        assert resp.status_code == 422, f"Expected 422 for {url}"


@pytest.mark.asyncio
async def test_webhook_rejects_ipv6_loopback(client: AsyncClient, db):
    """Webhook blocks IPv6 loopback."""
    token, entity_id = await _setup(client, USER)
    await _grant_trust(db, entity_id)

    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "http://[::1]:9000/hook",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422


# --- Suspension Auto-Reactivation Test ---


@pytest.mark.asyncio
async def test_suspended_user_auto_reactivated_after_expiry(client: AsyncClient, db):
    """Suspended user is auto-reactivated when suspension expires."""
    admin_token, _ = await _setup(client, ADMIN)
    await _make_admin(db, ADMIN["email"])
    user_token, user_id = await _setup(client, SUSPENDED)

    # Suspend for 1 day
    resp = await client.patch(
        f"/api/v1/admin/entities/{user_id}/suspend",
        params={"days": 1},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200

    # User should be blocked now
    resp = await client.get("/api/v1/auth/me", headers=_auth(user_token))
    assert resp.status_code == 401

    # Set suspended_until to the past to simulate time passing
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from src.models import Entity

    result = await db.execute(select(Entity).where(Entity.email == SUSPENDED["email"]))
    entity = result.scalar_one()
    entity.suspended_until = datetime.now(timezone.utc) - timedelta(hours=1)
    await db.flush()

    # Now the user should be auto-reactivated on next auth check
    resp = await client.get("/api/v1/auth/me", headers=_auth(user_token))
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "SuspendedUser"

    # Verify entity is active again
    await db.refresh(entity)
    assert entity.is_active is True
    assert entity.suspended_until is None
