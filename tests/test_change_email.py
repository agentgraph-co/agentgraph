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
    "email": "change_email@example.com",
    "password": "Str0ngP@ss",
    "display_name": "ChangeEmail",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: AsyncClient) -> str:
    await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL, json={"email": USER["email"], "password": USER["password"]}
    )
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_change_email_success(client: AsyncClient, db):
    """Successfully change email with correct password."""
    token = await _setup(client)

    resp = await client.post(
        "/api/v1/auth/change-email",
        json={
            "new_email": "new_email@example.com",
            "current_password": USER["password"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "verification" in data["message"].lower() or "email" in data["message"].lower()


@pytest.mark.asyncio
async def test_change_email_wrong_password(client: AsyncClient, db):
    """Change email fails with wrong password."""
    token = await _setup(client)

    resp = await client.post(
        "/api/v1/auth/change-email",
        json={
            "new_email": "new@example.com",
            "current_password": "WrongPass1",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_change_email_duplicate(client: AsyncClient, db):
    """Change email fails if new email already taken."""
    token = await _setup(client)

    # Register another user with target email
    other = {
        "email": "taken@example.com",
        "password": "Str0ngP@ss",
        "display_name": "Taken",
    }
    await client.post(REGISTER_URL, json=other)

    resp = await client.post(
        "/api/v1/auth/change-email",
        json={
            "new_email": "taken@example.com",
            "current_password": USER["password"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_change_email_requires_auth(client: AsyncClient, db):
    """Change email requires authentication."""
    resp = await client.post(
        "/api/v1/auth/change-email",
        json={
            "new_email": "new@example.com",
            "current_password": "Str0ngP@ss",
        },
    )
    assert resp.status_code in (401, 403)
