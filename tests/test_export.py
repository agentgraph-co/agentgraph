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
EXPORT_URL = "/api/v1/export/me"
POSTS_URL = "/api/v1/feed/posts"
SOCIAL_URL = "/api/v1/social"

USER = {
    "email": "export@test.com",
    "password": "Str0ngP@ss",
    "display_name": "ExportUser",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_export_basic(client: AsyncClient):
    token, entity_id = await _setup_user(client, USER)

    resp = await client.get(EXPORT_URL, headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["export_version"] == "1.0"
    assert data["profile"]["id"] == entity_id
    assert data["profile"]["display_name"] == USER["display_name"]
    assert data["post_count"] == 0
    assert data["following_count"] == 0


@pytest.mark.asyncio
async def test_export_with_posts(client: AsyncClient):
    token, _ = await _setup_user(client, USER)

    await client.post(
        POSTS_URL,
        json={"content": "Export test post"},
        headers=_auth(token),
    )

    resp = await client.get(EXPORT_URL, headers=_auth(token))
    data = resp.json()
    assert data["post_count"] == 1
    assert data["posts"][0]["content"] == "Export test post"


@pytest.mark.asyncio
async def test_export_with_follows(client: AsyncClient):
    token_a, _ = await _setup_user(client, USER)
    _, id_b = await _setup_user(
        client,
        {"email": "exp2@test.com", "password": "Str0ngP@ss", "display_name": "Exp2"},
    )

    await client.post(
        f"{SOCIAL_URL}/follow/{id_b}", headers=_auth(token_a),
    )

    resp = await client.get(EXPORT_URL, headers=_auth(token_a))
    data = resp.json()
    assert data["following_count"] == 1
    assert id_b in data["following"]


@pytest.mark.asyncio
async def test_export_unauthenticated(client: AsyncClient):
    resp = await client.get(EXPORT_URL)
    assert resp.status_code in (401, 403)
