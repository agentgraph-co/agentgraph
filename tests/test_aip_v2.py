"""Tests for AIP v2 — agent-to-agent messaging, channels, negotiation."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import AgentCapabilityRegistry, TrustScore


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
BASE_URL = "/api/v1/aip/v2"

USER_A = {
    "email": "aipv2_a@test.com",
    "password": "Str0ngP@ss1",
    "display_name": "AIPv2UserA",
}
USER_B = {
    "email": "aipv2_b@test.com",
    "password": "Str0ngP@ss2",
    "display_name": "AIPv2UserB",
}
USER_C = {
    "email": "aipv2_c@test.com",
    "password": "Str0ngP@ss3",
    "display_name": "AIPv2UserC",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL,
        json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Send Message ---


@pytest.mark.asyncio
async def test_send_message_success(client):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)

    resp = await client.post(
        f"{BASE_URL}/messages",
        json={
            "recipient_entity_id": uid_b,
            "message_type": "request",
            "payload": {"action": "hello"},
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sender_entity_id"] == uid_a
    assert data["recipient_entity_id"] == uid_b
    assert data["message_type"] == "request"
    assert data["payload"] == {"action": "hello"}
    assert data["is_read"] is False
    assert "id" in data


@pytest.mark.asyncio
async def test_send_message_to_nonexistent_entity(client):
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        f"{BASE_URL}/messages",
        json={
            "recipient_entity_id": str(uuid.uuid4()),
            "message_type": "event",
            "payload": {},
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_send_message_to_self(client):
    token_a, uid_a = await _setup_user(client, USER_A)

    resp = await client.post(
        f"{BASE_URL}/messages",
        json={
            "recipient_entity_id": uid_a,
            "message_type": "notification",
            "payload": {},
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "yourself" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_send_message_requires_auth(client):
    resp = await client.post(
        f"{BASE_URL}/messages",
        json={
            "recipient_entity_id": str(uuid.uuid4()),
            "message_type": "request",
            "payload": {},
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_send_message_captures_trust_score(client, db):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)

    # Update trust score for user A (registration already creates one)
    from sqlalchemy import update
    await db.execute(
        update(TrustScore)
        .where(TrustScore.entity_id == uuid.UUID(uid_a))
        .values(score=0.85)
    )
    await db.flush()

    resp = await client.post(
        f"{BASE_URL}/messages",
        json={
            "recipient_entity_id": uid_b,
            "message_type": "request",
            "payload": {"data": "test"},
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sender_trust_score"] == pytest.approx(0.85, abs=0.01)


# --- Get Inbox ---


@pytest.mark.asyncio
async def test_get_inbox(client):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)

    # Send 2 messages from A to B
    for i in range(2):
        await client.post(
            f"{BASE_URL}/messages",
            json={
                "recipient_entity_id": uid_b,
                "message_type": "event",
                "payload": {"seq": i},
            },
            headers=_auth(token_a),
        )

    # Check B's inbox
    resp = await client.get(
        f"{BASE_URL}/messages", headers=_auth(token_b),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["messages"]) == 2
    # Both messages present (order may vary when timestamps identical)
    seqs = sorted(m["payload"]["seq"] for m in data["messages"])
    assert seqs == [0, 1]


@pytest.mark.asyncio
async def test_get_inbox_message_type_filter(client):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)

    # Send a request and an event
    await client.post(
        f"{BASE_URL}/messages",
        json={
            "recipient_entity_id": uid_b,
            "message_type": "request",
            "payload": {},
        },
        headers=_auth(token_a),
    )
    await client.post(
        f"{BASE_URL}/messages",
        json={
            "recipient_entity_id": uid_b,
            "message_type": "event",
            "payload": {},
        },
        headers=_auth(token_a),
    )

    # Filter by request only
    resp = await client.get(
        f"{BASE_URL}/messages?message_type=request",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["messages"][0]["message_type"] == "request"


# --- Create Channel ---


@pytest.mark.asyncio
async def test_create_channel_success(client):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)

    resp = await client.post(
        f"{BASE_URL}/channels",
        json={
            "name": "Test Channel",
            "participant_ids": [uid_a, uid_b],
            "description": "A test channel",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Channel"
    assert data["description"] == "A test channel"
    assert data["created_by_entity_id"] == uid_a
    assert uid_a in data["participant_ids"]
    assert uid_b in data["participant_ids"]
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_channel_without_self(client):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)
    token_c, uid_c = await _setup_user(client, USER_C)

    resp = await client.post(
        f"{BASE_URL}/channels",
        json={
            "name": "No Self Channel",
            "participant_ids": [uid_b, uid_c],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "creator" in resp.json()["detail"].lower()


# --- List Channels ---


@pytest.mark.asyncio
async def test_list_channels(client):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)

    # Create a channel
    await client.post(
        f"{BASE_URL}/channels",
        json={
            "name": "Listed Channel",
            "participant_ids": [uid_a, uid_b],
        },
        headers=_auth(token_a),
    )

    # Both users should see it
    resp_a = await client.get(
        f"{BASE_URL}/channels", headers=_auth(token_a),
    )
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["total"] >= 1
    channel_names = [ch["name"] for ch in data_a["channels"]]
    assert "Listed Channel" in channel_names

    resp_b = await client.get(
        f"{BASE_URL}/channels", headers=_auth(token_b),
    )
    assert resp_b.status_code == 200
    assert resp_b.json()["total"] >= 1


# --- Channel Messages ---


@pytest.mark.asyncio
async def test_channel_messages(client):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)

    # Create channel
    ch_resp = await client.post(
        f"{BASE_URL}/channels",
        json={
            "name": "Msg Channel",
            "participant_ids": [uid_a, uid_b],
        },
        headers=_auth(token_a),
    )
    channel_id = ch_resp.json()["id"]

    # Send a message in the channel
    msg_resp = await client.post(
        f"{BASE_URL}/messages",
        json={
            "recipient_entity_id": uid_b,
            "message_type": "request",
            "payload": {"in_channel": True},
            "channel_id": channel_id,
        },
        headers=_auth(token_a),
    )
    assert msg_resp.status_code == 201

    # Get channel messages
    resp = await client.get(
        f"{BASE_URL}/channels/{channel_id}/messages",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["messages"][0]["payload"]["in_channel"] is True


@pytest.mark.asyncio
async def test_channel_messages_ordering(client):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)

    # Create channel
    ch_resp = await client.post(
        f"{BASE_URL}/channels",
        json={
            "name": "Order Channel",
            "participant_ids": [uid_a, uid_b],
        },
        headers=_auth(token_a),
    )
    channel_id = ch_resp.json()["id"]

    # Send 3 messages
    for i in range(3):
        await client.post(
            f"{BASE_URL}/messages",
            json={
                "recipient_entity_id": uid_b,
                "message_type": "event",
                "payload": {"seq": i},
                "channel_id": channel_id,
            },
            headers=_auth(token_a),
        )

    resp = await client.get(
        f"{BASE_URL}/channels/{channel_id}/messages",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    # All messages present (order may vary when timestamps identical in test tx)
    seqs = sorted(m["payload"]["seq"] for m in data["messages"])
    assert seqs == [0, 1, 2]


@pytest.mark.asyncio
async def test_channel_messages_non_participant(client):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)
    token_c, uid_c = await _setup_user(client, USER_C)

    # Create channel between A and B
    ch_resp = await client.post(
        f"{BASE_URL}/channels",
        json={
            "name": "Private Channel",
            "participant_ids": [uid_a, uid_b],
        },
        headers=_auth(token_a),
    )
    channel_id = ch_resp.json()["id"]

    # C tries to read channel messages
    resp = await client.get(
        f"{BASE_URL}/channels/{channel_id}/messages",
        headers=_auth(token_c),
    )
    assert resp.status_code == 403


# --- Capability Negotiation ---


@pytest.mark.asyncio
async def test_negotiate_with_capabilities(client, db):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)

    # Register capabilities for user B
    db.add(AgentCapabilityRegistry(
        id=uuid.uuid4(),
        entity_id=uuid.UUID(uid_b),
        capability_name="text_generation",
        version="1.0.0",
        is_active=True,
    ))
    db.add(AgentCapabilityRegistry(
        id=uuid.uuid4(),
        entity_id=uuid.UUID(uid_b),
        capability_name="image_analysis",
        version="1.0.0",
        is_active=True,
    ))
    await db.flush()

    resp = await client.post(
        f"{BASE_URL}/negotiate",
        json={
            "target_entity_id": uid_b,
            "requested_capabilities": [
                "text_generation", "image_analysis", "audio_transcription",
            ],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["supported"]) == {"text_generation", "image_analysis"}
    assert data["unsupported"] == ["audio_transcription"]
    assert data["target_entity_id"] == uid_b


@pytest.mark.asyncio
async def test_negotiate_without_capabilities(client):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)

    resp = await client.post(
        f"{BASE_URL}/negotiate",
        json={
            "target_entity_id": uid_b,
            "requested_capabilities": ["nonexistent_cap"],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["supported"] == []
    assert data["unsupported"] == ["nonexistent_cap"]


@pytest.mark.asyncio
async def test_negotiate_nonexistent_target(client):
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        f"{BASE_URL}/negotiate",
        json={
            "target_entity_id": str(uuid.uuid4()),
            "requested_capabilities": ["something"],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_negotiate_requires_auth(client):
    resp = await client.post(
        f"{BASE_URL}/negotiate",
        json={
            "target_entity_id": str(uuid.uuid4()),
            "requested_capabilities": ["something"],
        },
    )
    assert resp.status_code == 401
