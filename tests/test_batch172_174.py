"""Tests for Tasks #172-173: rate limiting on submolt and admin GET endpoints."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import Entity


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

ADMIN_USER = {
    "email": "batch172admin@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch172Admin",
}
USER_A = {
    "email": "batch172a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch172A",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


async def _make_admin(db, entity_id: str):
    entity = await db.get(Entity, uuid.UUID(entity_id))
    entity.is_admin = True
    await db.flush()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Task #172: Rate limiting on submolt GET endpoints ---


@pytest.mark.asyncio
async def test_submolt_list_has_rate_limit(client, db):
    """GET /submolts should have rate limit headers."""
    resp = await client.get("/api/v1/submolts")
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers


@pytest.mark.asyncio
async def test_submolt_feed_has_rate_limit(client, db):
    """GET /submolts/{name}/feed should have rate limit headers."""
    token, _ = await _setup_user(client, USER_A)

    # Create a submolt first
    resp = await client.post(
        "/api/v1/submolts",
        json={"name": "ratefeedtest", "display_name": "Rate Feed Test"},
        headers=_auth(token),
    )
    assert resp.status_code == 201

    resp = await client.get("/api/v1/submolts/ratefeedtest/feed")
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers


@pytest.mark.asyncio
async def test_submolt_get_has_rate_limit(client, db):
    """GET /submolts/{name} should have rate limit headers."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/submolts",
        json={"name": "rategettest", "display_name": "Rate Get Test"},
        headers=_auth(token),
    )
    assert resp.status_code == 201

    resp = await client.get("/api/v1/submolts/rategettest")
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers


# --- Task #173: Rate limiting on admin GET endpoints ---


@pytest.mark.asyncio
async def test_admin_stats_has_rate_limit(client, db):
    """GET /admin/stats should have rate limit headers."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    resp = await client.get(
        "/api/v1/admin/stats", headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers


@pytest.mark.asyncio
async def test_admin_growth_has_rate_limit(client, db):
    """GET /admin/growth should have rate limit headers."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    resp = await client.get(
        "/api/v1/admin/growth", headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers


@pytest.mark.asyncio
async def test_admin_audit_logs_has_rate_limit(client, db):
    """GET /admin/audit-logs should have rate limit headers."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    resp = await client.get(
        "/api/v1/admin/audit-logs", headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers
