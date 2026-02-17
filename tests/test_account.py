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
ACCOUNT_URL = "/api/v1/account"

USER = {
    "email": "acct@test.com",
    "password": "Str0ngP@ss",
    "display_name": "AccountUser",
}


async def _setup_user(
    client: AsyncClient, user: dict | None = None,
) -> str:
    """Register + login, return JWT token."""
    u = user or USER
    await client.post(REGISTER_URL, json=u)
    resp = await client.post(
        LOGIN_URL, json={"email": u["email"], "password": u["password"]},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_change_password(client: AsyncClient):
    token = await _setup_user(client)

    resp = await client.post(
        f"{ACCOUNT_URL}/change-password",
        json={
            "current_password": USER["password"],
            "new_password": "NewStr0ngP@ss!",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200

    # Login with new password
    resp = await client.post(
        LOGIN_URL,
        json={"email": USER["email"], "password": "NewStr0ngP@ss!"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_change_password_wrong_current(client: AsyncClient):
    token = await _setup_user(client)

    resp = await client.post(
        f"{ACCOUNT_URL}/change-password",
        json={
            "current_password": "WrongPassword1",
            "new_password": "NewStr0ngP@ss!",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_deactivate_account(client: AsyncClient):
    token = await _setup_user(client)

    resp = await client.post(
        f"{ACCOUNT_URL}/deactivate", headers=_auth(token),
    )
    assert resp.status_code == 200

    # Cannot login anymore
    resp = await client.post(
        LOGIN_URL,
        json={"email": USER["email"], "password": USER["password"]},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_audit_log_empty(client: AsyncClient):
    token = await _setup_user(client)

    resp = await client.get(
        f"{ACCOUNT_URL}/audit-log", headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_audit_log_after_password_change(client: AsyncClient):
    token = await _setup_user(client)

    await client.post(
        f"{ACCOUNT_URL}/change-password",
        json={
            "current_password": USER["password"],
            "new_password": "NewStr0ngP@ss!",
        },
        headers=_auth(token),
    )

    resp = await client.get(
        f"{ACCOUNT_URL}/audit-log", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    actions = [e["action"] for e in data["entries"]]
    assert "auth.password_change" in actions


@pytest.mark.asyncio
async def test_audit_log_pagination(client: AsyncClient):
    token = await _setup_user(client)

    # Create some audit entries via password changes
    for i in range(3):
        pwd = f"NewP@ss{i}x" if i > 0 else USER["password"]
        await client.post(
            f"{ACCOUNT_URL}/change-password",
            json={
                "current_password": pwd,
                "new_password": f"NewP@ss{i + 1}x",
            },
            headers=_auth(token),
        )

    resp = await client.get(
        f"{ACCOUNT_URL}/audit-log",
        params={"limit": 2},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["entries"]) == 2
