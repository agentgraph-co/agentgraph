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
    "email": "audit_admin@example.com",
    "password": "Str0ngP@ss",
    "display_name": "AuditAdmin",
}
USER = {
    "email": "audit_user@example.com",
    "password": "Str0ngP@ss",
    "display_name": "AuditUser",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_admin(client: AsyncClient, db) -> str:
    """Register user and promote to admin. Returns token."""
    await client.post(REGISTER_URL, json=ADMIN)
    resp = await client.post(
        LOGIN_URL,
        json={"email": ADMIN["email"], "password": ADMIN["password"]},
    )
    token = resp.json()["access_token"]

    # Promote to admin directly in DB
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    entity_id = me.json()["id"]

    from src.models import Entity
    entity = await db.get(Entity, entity_id)
    entity.is_admin = True
    await db.flush()

    return token


@pytest.mark.asyncio
async def test_audit_logs_admin_access(client: AsyncClient, db):
    """Admin can query audit logs."""
    token = await _setup_admin(client, db)

    resp = await client.get(
        "/api/v1/admin/audit-logs",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data
    assert "total" in data
    assert isinstance(data["logs"], list)


@pytest.mark.asyncio
async def test_audit_logs_non_admin_denied(client: AsyncClient, db):
    """Non-admin cannot query audit logs."""
    await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL,
        json={"email": USER["email"], "password": USER["password"]},
    )
    token = resp.json()["access_token"]

    resp = await client.get(
        "/api/v1/admin/audit-logs",
        headers=_auth(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audit_logs_filter_by_action(client: AsyncClient, db):
    """Audit logs can be filtered by action prefix."""
    token = await _setup_admin(client, db)

    # Create an agent to generate audit log entries
    await client.post(
        "/api/v1/agents",
        json={"display_name": "AuditBot", "capabilities": []},
        headers=_auth(token),
    )

    resp = await client.get(
        "/api/v1/admin/audit-logs?action=agent",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    # All returned logs should have action starting with "agent"
    for log in data["logs"]:
        assert log["action"].startswith("agent")


@pytest.mark.asyncio
async def test_audit_logs_pagination(client: AsyncClient, db):
    """Audit logs respect limit and offset."""
    token = await _setup_admin(client, db)

    resp = await client.get(
        "/api/v1/admin/audit-logs?limit=2&offset=0",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["logs"]) <= 2
