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

OWNER = {
    "email": "ban_owner@example.com",
    "password": "Str0ngP@ss",
    "display_name": "BanOwner",
}
MEMBER = {
    "email": "ban_member@example.com",
    "password": "Str0ngP@ss",
    "display_name": "BanMember",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


async def _create_submolt(client: AsyncClient, token: str, name: str) -> str:
    resp = await client.post(
        "/api/v1/submolts",
        json={
            "name": name,
            "display_name": name.title(),
            "description": "Test submolt",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["name"]


@pytest.mark.asyncio
async def test_ban_member(client: AsyncClient, db):
    """Owner can ban a member from a submolt."""
    owner_token, _ = await _setup_user(client, OWNER)
    member_token, member_id = await _setup_user(client, MEMBER)
    submolt_name = await _create_submolt(client, owner_token, "bantest")

    # Member joins
    await client.post(
        f"/api/v1/submolts/{submolt_name}/join",
        headers=_auth(member_token),
    )

    # Owner bans member
    resp = await client.post(
        f"/api/v1/submolts/{submolt_name}/ban/{member_id}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    assert "banned" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_banned_member_cannot_rejoin(client: AsyncClient, db):
    """A banned member cannot rejoin the submolt."""
    owner_token, _ = await _setup_user(client, OWNER)
    member_token, member_id = await _setup_user(client, MEMBER)
    submolt_name = await _create_submolt(client, owner_token, "banretest")

    # Join then ban
    await client.post(
        f"/api/v1/submolts/{submolt_name}/join",
        headers=_auth(member_token),
    )
    await client.post(
        f"/api/v1/submolts/{submolt_name}/ban/{member_id}",
        headers=_auth(owner_token),
    )

    # Try to rejoin
    resp = await client.post(
        f"/api/v1/submolts/{submolt_name}/join",
        headers=_auth(member_token),
    )
    assert resp.status_code == 403
    assert "banned" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unban_member(client: AsyncClient, db):
    """Owner can unban a banned member."""
    owner_token, _ = await _setup_user(client, OWNER)
    member_token, member_id = await _setup_user(client, MEMBER)
    submolt_name = await _create_submolt(client, owner_token, "unbantest")

    await client.post(
        f"/api/v1/submolts/{submolt_name}/join",
        headers=_auth(member_token),
    )
    await client.post(
        f"/api/v1/submolts/{submolt_name}/ban/{member_id}",
        headers=_auth(owner_token),
    )

    # Unban
    resp = await client.delete(
        f"/api/v1/submolts/{submolt_name}/ban/{member_id}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 200

    # Can rejoin now
    resp = await client.post(
        f"/api/v1/submolts/{submolt_name}/join",
        headers=_auth(member_token),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cannot_ban_owner(client: AsyncClient, db):
    """Cannot ban the submolt owner."""
    owner_token, owner_id = await _setup_user(client, OWNER)
    member_token, member_id = await _setup_user(client, MEMBER)
    submolt_name = await _create_submolt(client, owner_token, "nobanowner")

    # Member joins and somehow gets promoted to mod (owner does it)
    await client.post(
        f"/api/v1/submolts/{submolt_name}/join",
        headers=_auth(member_token),
    )
    await client.post(
        f"/api/v1/submolts/{submolt_name}/moderators/{member_id}",
        headers=_auth(owner_token),
    )

    # Moderator tries to ban owner
    resp = await client.post(
        f"/api/v1/submolts/{submolt_name}/ban/{owner_id}",
        headers=_auth(member_token),
    )
    assert resp.status_code == 400
    assert "owner" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cannot_ban_self(client: AsyncClient, db):
    """Cannot ban yourself."""
    owner_token, owner_id = await _setup_user(client, OWNER)
    submolt_name = await _create_submolt(client, owner_token, "nobanself")

    resp = await client.post(
        f"/api/v1/submolts/{submolt_name}/ban/{owner_id}",
        headers=_auth(owner_token),
    )
    assert resp.status_code == 400
    assert "yourself" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_regular_member_cannot_ban(client: AsyncClient, db):
    """Regular members cannot ban others."""
    owner_token, _ = await _setup_user(client, OWNER)
    member_token, member_id = await _setup_user(client, MEMBER)
    submolt_name = await _create_submolt(client, owner_token, "membanfail")

    await client.post(
        f"/api/v1/submolts/{submolt_name}/join",
        headers=_auth(member_token),
    )

    # Regular member tries to ban owner
    resp = await client.post(
        f"/api/v1/submolts/{submolt_name}/ban/{member_id}",
        headers=_auth(member_token),
    )
    assert resp.status_code == 403
