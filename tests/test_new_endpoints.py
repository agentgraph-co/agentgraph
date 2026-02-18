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

USER_A = {
    "email": "new_ep_a@example.com",
    "password": "Str0ngP@ss",
    "display_name": "EndpointUserA",
}
USER_B = {
    "email": "new_ep_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "EndpointUserB",
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


# --- Browse Profiles ---


@pytest.mark.asyncio
async def test_browse_profiles(client: AsyncClient, db):
    """Browse profiles returns paginated results."""
    await _setup(client, USER_A)
    await _setup(client, USER_B)

    resp = await client.get("/api/v1/profiles")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    assert len(data["profiles"]) >= 2
    assert "has_more" in data


@pytest.mark.asyncio
async def test_browse_profiles_with_search(client: AsyncClient, db):
    """Browse profiles supports text search."""
    await _setup(client, USER_A)

    resp = await client.get("/api/v1/profiles", params={"q": "EndpointUserA"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(p["display_name"] == "EndpointUserA" for p in data["profiles"])


@pytest.mark.asyncio
async def test_browse_profiles_with_type_filter(client: AsyncClient, db):
    """Browse profiles supports entity type filter."""
    await _setup(client, USER_A)

    resp = await client.get("/api/v1/profiles", params={"entity_type": "human"})
    assert resp.status_code == 200
    for p in resp.json()["profiles"]:
        assert p["type"] == "human"


# --- Banned Members List ---


@pytest.mark.asyncio
async def test_list_banned_members(client: AsyncClient, db):
    """Owner can list banned members."""
    owner_token, _ = await _setup(client, USER_A)
    member_token, member_id = await _setup(client, USER_B)

    # Create submolt
    resp = await client.post(
        "/api/v1/submolts",
        json={"name": "banlist", "display_name": "Ban List", "description": "Test"},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 201

    # Member joins
    await client.post(
        "/api/v1/submolts/banlist/join", headers=_auth(member_token)
    )

    # Ban member
    await client.post(
        f"/api/v1/submolts/banlist/ban/{member_id}",
        headers=_auth(owner_token),
    )

    # List banned
    resp = await client.get(
        "/api/v1/submolts/banlist/banned", headers=_auth(owner_token)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["banned"][0]["entity_id"] == member_id


@pytest.mark.asyncio
async def test_non_mod_cannot_list_banned(client: AsyncClient, db):
    """Regular members cannot view ban list."""
    owner_token, _ = await _setup(client, USER_A)
    member_token, _ = await _setup(client, USER_B)

    await client.post(
        "/api/v1/submolts",
        json={"name": "banlist2", "display_name": "Ban List 2", "description": "Test"},
        headers=_auth(owner_token),
    )
    await client.post(
        "/api/v1/submolts/banlist2/join", headers=_auth(member_token)
    )

    resp = await client.get(
        "/api/v1/submolts/banlist2/banned", headers=_auth(member_token)
    )
    assert resp.status_code == 403


# --- Delete Conversation ---


@pytest.mark.asyncio
async def test_delete_conversation(client: AsyncClient, db):
    """Participant can delete a conversation."""
    token_a, id_a = await _setup(client, USER_A)
    token_b, id_b = await _setup(client, USER_B)

    # Send a DM to create conversation
    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "Hello!"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    conv_id = resp.json()["conversation_id"]

    # Delete conversation
    resp = await client.delete(
        f"/api/v1/messages/{conv_id}", headers=_auth(token_a)
    )
    assert resp.status_code == 204

    # Conversation should be gone
    resp = await client.get(
        f"/api/v1/messages/{conv_id}", headers=_auth(token_a)
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_non_participant_cannot_delete_conversation(client: AsyncClient, db):
    """Non-participant cannot delete a conversation."""
    token_a, id_a = await _setup(client, USER_A)
    token_b, id_b = await _setup(client, USER_B)

    # Create third user
    user_c = {
        "email": "new_ep_c@example.com",
        "password": "Str0ngP@ss",
        "display_name": "EndpointUserC",
    }
    token_c, _ = await _setup(client, user_c)

    # A sends DM to B
    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "Private chat"},
        headers=_auth(token_a),
    )
    conv_id = resp.json()["conversation_id"]

    # C tries to delete — should fail
    resp = await client.delete(
        f"/api/v1/messages/{conv_id}", headers=_auth(token_c)
    )
    assert resp.status_code == 403


# --- Trust Score Refresh ---


@pytest.mark.asyncio
async def test_refresh_trust_score(client: AsyncClient, db):
    """User can refresh their own trust score."""
    token, entity_id = await _setup(client, USER_A)

    resp = await client.post(
        f"/api/v1/entities/{entity_id}/trust/refresh",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "score" in data
    assert "component_details" in data
    assert 0.0 <= data["score"] <= 1.0


@pytest.mark.asyncio
async def test_cannot_refresh_other_trust_score(client: AsyncClient, db):
    """Cannot refresh another user's trust score."""
    token_a, _ = await _setup(client, USER_A)
    _, id_b = await _setup(client, USER_B)

    resp = await client.post(
        f"/api/v1/entities/{id_b}/trust/refresh",
        headers=_auth(token_a),
    )
    assert resp.status_code == 403
