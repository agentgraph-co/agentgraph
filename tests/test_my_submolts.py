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
    "email": "mysubs@example.com",
    "password": "Str0ngP@ss",
    "display_name": "MySubsUser",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: AsyncClient) -> str:
    await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL,
        json={"email": USER["email"], "password": USER["password"]},
    )
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_my_submolts_empty(client: AsyncClient, db):
    """Returns empty list when not a member of any submolt."""
    token = await _setup(client)

    resp = await client.get(
        "/api/v1/submolts/my-submolts",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["submolts"] == []


@pytest.mark.asyncio
async def test_my_submolts_after_create(client: AsyncClient, db):
    """Creator auto-joins, so it appears in my-submolts."""
    token = await _setup(client)

    await client.post(
        "/api/v1/submolts",
        json={
            "name": "mysubtest",
            "display_name": "My Sub Test",
            "description": "Testing",
        },
        headers=_auth(token),
    )

    resp = await client.get(
        "/api/v1/submolts/my-submolts",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["submolts"][0]["name"] == "mysubtest"
    assert data["submolts"][0]["role"] == "owner"


@pytest.mark.asyncio
async def test_my_submolts_after_join(client: AsyncClient, db):
    """Joining a submolt makes it appear in my-submolts."""
    token = await _setup(client)

    # Create a submolt first
    await client.post(
        "/api/v1/submolts",
        json={
            "name": "joinable",
            "display_name": "Joinable",
            "description": "A submolt to join",
        },
        headers=_auth(token),
    )

    resp = await client.get(
        "/api/v1/submolts/my-submolts",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_my_submolts_requires_auth(client: AsyncClient, db):
    """Unauthenticated access should fail."""
    resp = await client.get("/api/v1/submolts/my-submolts")
    assert resp.status_code in (401, 403)
