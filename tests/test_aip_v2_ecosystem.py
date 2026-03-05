"""Tests for AIP v2 Ecosystem — protocol info, validation, stats, connectivity."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

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
BASE_URL = "/api/v1/aip/v2/ecosystem"

USER_A = {
    "email": "eco_a@test.com",
    "password": "Str0ngP@ss1",
    "display_name": "EcoUserA",
}
USER_B = {
    "email": "eco_b@test.com",
    "password": "Str0ngP@ss2",
    "display_name": "EcoUserB",
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


# --- Protocol Info ---


@pytest.mark.asyncio
async def test_protocol_info(client):
    resp = await client.get(f"{BASE_URL}/protocol-info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "2.0"
    assert "request" in data["supported_message_types"]
    assert "response" in data["supported_message_types"]
    assert "event" in data["supported_message_types"]
    assert "notification" in data["supported_message_types"]
    assert data["channel_features"]["named_channels"] is True
    assert data["channel_features"]["multi_party"] is True
    assert len(data["authentication_methods"]) == 2
    assert data["rate_limits"]["reads"] is not None


# --- Supported Versions ---


@pytest.mark.asyncio
async def test_supported_versions(client):
    resp = await client.get(f"{BASE_URL}/supported-versions")
    assert resp.status_code == 200
    data = resp.json()
    versions = data["versions"]
    assert len(versions) == 2

    v1 = next(v for v in versions if v["version"] == "1.0")
    assert v1["status"] == "deprecated"
    assert v1["sunset_date"] == "2026-06-01"

    v2 = next(v for v in versions if v["version"] == "2.0")
    assert v2["status"] == "current"
    assert v2.get("sunset_date") is None


# --- Validate Message ---


@pytest.mark.asyncio
async def test_validate_message_valid(client):
    resp = await client.post(
        f"{BASE_URL}/validate-message",
        json={
            "message_type": "request",
            "payload": {"action": "hello"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_validate_message_invalid_type(client):
    resp = await client.post(
        f"{BASE_URL}/validate-message",
        json={
            "message_type": "invalid_type",
            "payload": {},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert len(data["errors"]) == 1
    assert data["errors"][0]["field"] == "message_type"
    assert "invalid_type" in data["errors"][0]["message"]


@pytest.mark.asyncio
async def test_validate_message_invalid_recipient(client):
    resp = await client.post(
        f"{BASE_URL}/validate-message",
        json={
            "message_type": "event",
            "payload": {"data": "test"},
            "recipient_entity_id": "not-a-uuid",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert any(e["field"] == "recipient_entity_id" for e in data["errors"])


@pytest.mark.asyncio
async def test_validate_message_nonexistent_recipient(client):
    resp = await client.post(
        f"{BASE_URL}/validate-message",
        json={
            "message_type": "request",
            "payload": {},
            "recipient_entity_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert any(
        e["field"] == "recipient_entity_id" and "not found" in e["message"]
        for e in data["errors"]
    )


@pytest.mark.asyncio
async def test_validate_message_valid_with_recipient(client):
    token_a, uid_a = await _setup_user(client, USER_A)

    resp = await client.post(
        f"{BASE_URL}/validate-message",
        json={
            "message_type": "notification",
            "payload": {"note": "hi"},
            "recipient_entity_id": uid_a,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["errors"] == []


# --- Stats ---


@pytest.mark.asyncio
async def test_stats_empty(client):
    token_a, uid_a = await _setup_user(client, USER_A)

    resp = await client.get(f"{BASE_URL}/stats", headers=_auth(token_a))
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == uid_a
    assert data["messages_sent"] == 0
    assert data["messages_received"] == 0
    assert data["channels_created"] == 0
    assert data["channels_participated"] == 0
    assert data["last_message_at"] is None


@pytest.mark.asyncio
async def test_stats_with_activity(client, db):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)

    # Send a message from A to B via the AIP v2 endpoint
    msg_resp = await client.post(
        "/api/v1/aip/v2/messages",
        json={
            "recipient_entity_id": uid_b,
            "message_type": "request",
            "payload": {"action": "ping"},
        },
        headers=_auth(token_a),
    )
    assert msg_resp.status_code == 201

    # Create a channel with both users
    ch_resp = await client.post(
        "/api/v1/aip/v2/channels",
        json={
            "name": "Stats Test Channel",
            "participant_ids": [uid_a, uid_b],
        },
        headers=_auth(token_a),
    )
    assert ch_resp.status_code == 201

    # Check stats for user A (sender, channel creator)
    resp_a = await client.get(f"{BASE_URL}/stats", headers=_auth(token_a))
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["messages_sent"] >= 1
    assert data_a["channels_created"] >= 1
    assert data_a["channels_participated"] >= 1
    assert data_a["last_message_at"] is not None

    # Check stats for user B (receiver, channel participant)
    resp_b = await client.get(f"{BASE_URL}/stats", headers=_auth(token_b))
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["messages_received"] >= 1
    assert data_b["channels_participated"] >= 1
    assert data_b["last_message_at"] is not None


@pytest.mark.asyncio
async def test_stats_requires_auth(client):
    resp = await client.get(f"{BASE_URL}/stats")
    assert resp.status_code == 401


# --- Test Connectivity ---


@pytest.mark.asyncio
async def test_connectivity_success(client):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)

    resp = await client.post(
        f"{BASE_URL}/test-connectivity",
        json={"target_entity_id": uid_b},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_entity_id"] == uid_b
    assert data["reachable"] is True
    assert data["is_active"] is True
    assert data["detail"] == "Entity is active and reachable"


@pytest.mark.asyncio
async def test_connectivity_with_trust_score(client, db):
    token_a, uid_a = await _setup_user(client, USER_A)
    token_b, uid_b = await _setup_user(client, USER_B)

    # Add a trust score for user B
    db.add(TrustScore(
        id=uuid.uuid4(), entity_id=uuid.UUID(uid_b), score=0.92,
    ))
    await db.flush()

    resp = await client.post(
        f"{BASE_URL}/test-connectivity",
        json={"target_entity_id": uid_b},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["reachable"] is True
    assert data["trust_score"] == pytest.approx(0.92, abs=0.01)


@pytest.mark.asyncio
async def test_connectivity_nonexistent_entity(client):
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        f"{BASE_URL}/test-connectivity",
        json={"target_entity_id": str(uuid.uuid4())},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["reachable"] is False
    assert data["is_active"] is False
    assert "not found" in data["detail"].lower()


@pytest.mark.asyncio
async def test_connectivity_self(client):
    token_a, uid_a = await _setup_user(client, USER_A)

    resp = await client.post(
        f"{BASE_URL}/test-connectivity",
        json={"target_entity_id": uid_a},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "yourself" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_connectivity_requires_auth(client):
    resp = await client.post(
        f"{BASE_URL}/test-connectivity",
        json={"target_entity_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 401
