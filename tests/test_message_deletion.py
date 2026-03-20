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
    "email": "mdel_alice@example.com",
    "password": "Str0ngP@ss",
    "display_name": "MDelAlice",
}
BOB = {
    "email": "mdel_bob@example.com",
    "password": "Str0ngP@ss",
    "display_name": "MDelBob",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _grant_trust(db: AsyncSession, entity_id: str, score: float = 0.5) -> None:
    from sqlalchemy import update
    eid = uuid.UUID(entity_id)
    await db.execute(
        update(TrustScore)
        .where(TrustScore.entity_id == eid)
        .values(score=score, components={"verification": 0.3, "age": 0.1, "activity": 0.1})
    )
    await db.flush()


async def _setup_user(
    client: AsyncClient, user: dict, db: AsyncSession | None = None,
) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    eid = me.json()["id"]
    if db is not None:
        await _grant_trust(db, eid)
    return token, eid


@pytest.mark.asyncio
async def test_delete_own_message(client: AsyncClient, db):
    """Sender can delete their own message."""
    token_a, _ = await _setup_user(client, ALICE, db)
    _, id_b = await _setup_user(client, BOB, db)

    # Send a message
    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "Delete me"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    msg_id = resp.json()["id"]
    conv_id = resp.json()["conversation_id"]

    # Delete the message
    resp = await client.delete(
        f"/api/v1/messages/{conv_id}/messages/{msg_id}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 204

    # Verify message is gone
    resp = await client.get(
        f"/api/v1/messages/{conv_id}", headers=_auth(token_a),
    )
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert all(m["id"] != msg_id for m in messages)


@pytest.mark.asyncio
async def test_cannot_delete_others_message(client: AsyncClient, db):
    """Cannot delete a message sent by someone else."""
    token_a, _ = await _setup_user(client, ALICE, db)
    token_b, id_b = await _setup_user(client, BOB, db)

    # Alice sends to Bob
    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "Alice's message"},
        headers=_auth(token_a),
    )
    msg_id = resp.json()["id"]
    conv_id = resp.json()["conversation_id"]

    # Bob tries to delete Alice's message
    resp = await client.delete(
        f"/api/v1/messages/{conv_id}/messages/{msg_id}",
        headers=_auth(token_b),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_nonexistent_message(client: AsyncClient, db):
    """Deleting a nonexistent message returns 404."""
    token_a, _ = await _setup_user(client, ALICE, db)
    _, id_b = await _setup_user(client, BOB, db)

    # Create conversation
    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "Setup msg"},
        headers=_auth(token_a),
    )
    conv_id = resp.json()["conversation_id"]

    resp = await client.delete(
        f"/api/v1/messages/{conv_id}/messages/{uuid.uuid4()}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation(client: AsyncClient, db):
    """Participant can delete entire conversation and all messages."""
    token_a, _ = await _setup_user(client, ALICE, db)
    _, id_b = await _setup_user(client, BOB, db)

    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": id_b, "content": "To be deleted"},
        headers=_auth(token_a),
    )
    conv_id = resp.json()["conversation_id"]

    # Delete conversation
    resp = await client.delete(
        f"/api/v1/messages/{conv_id}", headers=_auth(token_a),
    )
    assert resp.status_code == 204

    # Conversation no longer listed
    resp = await client.get(
        "/api/v1/messages", headers=_auth(token_a),
    )
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_dm_content_sanitized(client: AsyncClient, db):
    """Message content is sanitized for XSS."""
    token_a, _ = await _setup_user(client, ALICE, db)
    _, id_b = await _setup_user(client, BOB, db)

    resp = await client.post(
        "/api/v1/messages",
        json={
            "recipient_id": id_b,
            "content": 'Hello <script>alert("xss")</script> there',
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    assert "<script>" not in resp.json()["content"]
    assert "Hello" in resp.json()["content"]
    assert "there" in resp.json()["content"]
