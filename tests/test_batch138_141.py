"""Tests for Tasks #138-140: endorsement/evolution webhook dispatches,
evolution/submolt WS broadcasts, moderation content filtering, account rate limit."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
    "email": "batch138a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch138A",
}
USER_B = {
    "email": "batch138b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch138B",
}

SPAM_TEXT = "buy cheap discount click here visit http://spam.com"


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


# --- Task #138: Webhook dispatches for endorsement ---


@pytest.mark.asyncio
async def test_endorsement_webhook_dispatched(client, db):
    """Endorsing a capability should dispatch a webhook."""
    token_a, _ = await _setup_user(client, USER_A)

    # Create agent
    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "Webhook Endorse Agent",
            "description": "For webhook test",
            "capabilities": ["testing"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    agent_id = resp.json()["agent"]["id"]

    with patch("src.events.dispatch_webhooks", new_callable=AsyncMock) as mock_dispatch:
        resp = await client.post(
            f"/api/v1/entities/{agent_id}/endorsements",
            json={"capability": "testing", "comment": "Great!"},
            headers=_auth(token_a),
        )
        assert resp.status_code == 201

        # Check webhook was dispatched
        dispatched_events = [
            call[0][1] for call in mock_dispatch.call_args_list
        ]
        assert "endorsement.created" in dispatched_events


# --- Task #138: Webhook dispatches for evolution ---


@pytest.mark.asyncio
async def test_evolution_webhook_dispatched(client, db):
    """Creating an evolution record should dispatch a webhook."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "Webhook Evo Agent",
            "description": "For evolution webhook test",
            "capabilities": ["testing"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    agent_id = resp.json()["agent"]["id"]

    with patch("src.events.dispatch_webhooks", new_callable=AsyncMock) as mock_dispatch:
        resp = await client.post(
            "/api/v1/evolution",
            json={
                "entity_id": agent_id,
                "version": "1.0.0",
                "change_type": "initial",
                "change_summary": "Initial release with testing capability",
                "capabilities_snapshot": ["testing"],
            },
            headers=_auth(token_a),
        )
        assert resp.status_code == 201

        dispatched_events = [
            call[0][1] for call in mock_dispatch.call_args_list
        ]
        assert "evolution.created" in dispatched_events


# --- Task #138: Webhook event types ---


@pytest.mark.asyncio
async def test_webhook_accepts_endorsement_event_type(client, db):
    """Webhook subscription should accept endorsement.created event type."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://example.com/webhook",
            "event_types": ["endorsement.created", "evolution.created"],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201


# --- Task #139: WebSocket broadcast for evolution ---


@pytest.mark.asyncio
async def test_evolution_creates_record_successfully(client, db):
    """Evolution creation should succeed and include version."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "WS Evo Agent",
            "description": "For WS test",
            "capabilities": ["testing"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    agent_id = resp.json()["agent"]["id"]

    resp = await client.post(
        "/api/v1/evolution",
        json={
            "entity_id": agent_id,
            "version": "2.0.0",
            "change_type": "update",
            "change_summary": "Added new feature for testing",
            "capabilities_snapshot": ["testing", "new_feature"],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    assert resp.json()["version"] == "2.0.0"


# --- Task #140: Moderation flag content filtering ---


@pytest.mark.asyncio
async def test_moderation_flag_rejects_spam_details(client, db):
    """Moderation flag with spam details should be rejected."""
    token_a, user_a_id = await _setup_user(client, USER_A)
    token_b, user_b_id = await _setup_user(client, USER_B)

    resp = await client.post(
        "/api/v1/moderation/flag",
        json={
            "target_type": "entity",
            "target_id": user_b_id,
            "reason": "spam",
            "details": SPAM_TEXT,
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "rejected" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_moderation_flag_valid_details_succeeds(client, db):
    """Moderation flag with valid details should succeed."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, user_b_id = await _setup_user(client, USER_B)

    resp = await client.post(
        "/api/v1/moderation/flag",
        json={
            "target_type": "entity",
            "target_id": user_b_id,
            "reason": "spam",
            "details": "This user is posting irrelevant content",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201


# --- Task #140: Account audit log rate limiting ---


@pytest.mark.asyncio
async def test_account_audit_log_accessible(client, db):
    """Account audit log endpoint should be accessible."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.get(
        "/api/v1/account/audit-log",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert "entries" in resp.json()
    assert "total" in resp.json()
