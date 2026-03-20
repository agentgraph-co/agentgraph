from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.main import app
from src.models import TrustScore


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

ALICE = {
    "email": "dm_alice@example.com",
    "password": "Str0ngP@ss",
    "display_name": "DmAlice",
}
BOB = {
    "email": "dm_bob@example.com",
    "password": "Str0ngP@ss",
    "display_name": "DmBob",
}
CAROL = {
    "email": "dm_carol@example.com",
    "password": "Str0ngP@ss",
    "display_name": "DmCarol",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _grant_trust(db: AsyncSession, entity_id: str, score: float = 0.5) -> None:
    """Give entity a trust score sufficient for trust-gated actions."""
    from sqlalchemy import update as _sa_update
    eid = uuid.UUID(entity_id)
    await db.execute(
        _sa_update(TrustScore)
        .where(TrustScore.entity_id == eid)
        .values(score=score, components={"verification": 0.3, "age": 0.1, "activity": 0.1})
    )
    await db.flush()


async def _setup_user(
    client: AsyncClient, user: dict, db: AsyncSession | None = None,
) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    eid = me.json()["id"]
    if db is not None:
        await _grant_trust(db, eid)
    return token, eid


@pytest.mark.asyncio
async def test_send_message(client: AsyncClient, db):
    """Can send a direct message to another entity."""
    token_a, _ = await _setup_user(client, ALICE, db)
    _, id_b = await _setup_user(client, BOB, db)

    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "Hello Bob!"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "Hello Bob!"
    assert data["sender_name"] == "DmAlice"
    assert data["is_read"] is False
    assert "conversation_id" in data


@pytest.mark.asyncio
async def test_cannot_message_self(client: AsyncClient, db):
    """Cannot send a message to yourself."""
    token_a, id_a = await _setup_user(client, ALICE, db)

    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_a, "content": "Self-talk"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cannot_message_blocked(client: AsyncClient, db):
    """Blocked entities cannot exchange messages."""
    token_a, id_a = await _setup_user(client, ALICE, db)
    token_b, id_b = await _setup_user(client, BOB, db)

    # B blocks A
    await client.post(
        f"/api/v1/social/block/{id_a}", headers=_auth(token_b),
    )

    # A tries to message B — should fail
    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "Hey"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_conversations(client: AsyncClient, db):
    """List conversations shows recent activity."""
    token_a, _ = await _setup_user(client, ALICE, db)
    token_b, id_b = await _setup_user(client, BOB, db)

    # Send a message to create conversation
    await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "Hi Bob"},
        headers=_auth(token_a),
    )

    # Alice's conversations
    resp = await client.get(
        "/api/v1/messages", headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["conversations"]) == 1
    conv = data["conversations"][0]
    assert conv["other_entity_name"] == "DmBob"
    assert conv["last_message_preview"] == "Hi Bob"

    # Bob sees the same conversation
    resp = await client.get(
        "/api/v1/messages", headers=_auth(token_b),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["conversations"][0]["other_entity_name"] == "DmAlice"
    assert data["conversations"][0]["unread_count"] == 1


@pytest.mark.asyncio
async def test_get_conversation_messages(client: AsyncClient, db):
    """Get messages in a conversation, with read receipt marking."""
    token_a, _ = await _setup_user(client, ALICE, db)
    token_b, id_b = await _setup_user(client, BOB, db)

    # Send messages
    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "Message 1"},
        headers=_auth(token_a),
    )
    conv_id = resp.json()["conversation_id"]

    await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "Message 2"},
        headers=_auth(token_a),
    )

    # Bob reads the conversation
    resp = await client.get(
        f"/api/v1/messages/{conv_id}", headers=_auth(token_b),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["messages"]) == 2
    assert data["conversation_id"] == conv_id

    # After reading, unread count should be 0
    resp = await client.get(
        "/api/v1/messages", headers=_auth(token_b),
    )
    assert resp.json()["conversations"][0]["unread_count"] == 0


@pytest.mark.asyncio
async def test_conversation_not_accessible_to_others(client: AsyncClient, db):
    """Third party cannot access a conversation."""
    token_a, _ = await _setup_user(client, ALICE, db)
    _, id_b = await _setup_user(client, BOB, db)
    token_c, _ = await _setup_user(client, CAROL, db)

    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "Private msg"},
        headers=_auth(token_a),
    )
    conv_id = resp.json()["conversation_id"]

    # Carol tries to read Alice-Bob conversation
    resp = await client.get(
        f"/api/v1/messages/{conv_id}", headers=_auth(token_c),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unread_message_count(client: AsyncClient, db):
    """Unread count endpoint returns total across conversations."""
    token_a, _ = await _setup_user(client, ALICE, db)
    token_b, id_b = await _setup_user(client, BOB, db)
    _, id_c = await _setup_user(client, CAROL, db)

    # Alice sends to Bob
    await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "Hey Bob"},
        headers=_auth(token_a),
    )

    # Bob's unread count
    resp = await client.get(
        "/api/v1/messages/unread-count", headers=_auth(token_b),
    )
    assert resp.status_code == 200
    assert resp.json()["unread_count"] == 1


@pytest.mark.asyncio
async def test_same_conversation_reused(client: AsyncClient, db):
    """Multiple messages between same pair use the same conversation."""
    token_a, id_a = await _setup_user(client, ALICE, db)
    token_b, id_b = await _setup_user(client, BOB, db)

    # A messages B
    resp1 = await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "First"},
        headers=_auth(token_a),
    )
    conv1 = resp1.json()["conversation_id"]

    # B messages A
    resp2 = await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_a, "content": "Reply"},
        headers=_auth(token_b),
    )
    conv2 = resp2.json()["conversation_id"]

    # Same conversation
    assert conv1 == conv2


@pytest.mark.asyncio
async def test_message_to_nonexistent_user(client: AsyncClient, db):
    """Message to nonexistent user returns 404."""
    import uuid

    token_a, _ = await _setup_user(client, ALICE, db)

    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": str(uuid.uuid4()), "content": "Hello?"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 404
