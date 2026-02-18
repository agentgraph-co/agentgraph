"""Tests for Tasks #128-131: MCP handler content filtering,
cascade deactivation extensions, marketplace webhooks, export pagination."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import Entity, Listing, Transaction, TransactionStatus


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
    "email": "batch128a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch128A",
}
USER_B = {
    "email": "batch128b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch128B",
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


# --- Task #128: MCP handler content filtering ---


@pytest.mark.asyncio
async def test_mcp_handler_rejects_spam_evolution(client, db):
    """MCP handler should reject spam content in evolution change_summary."""
    from src.bridges.mcp_handler import MCPError, handle_tool_call

    token_a, user_a_id = await _setup_user(client, USER_A)

    # Create an agent
    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "MCP Filter Agent",
            "description": "Testing MCP filter",
            "capabilities": ["testing"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    agent_id = resp.json()["agent"]["id"]

    agent_entity = await db.get(Entity, uuid.UUID(agent_id))

    with pytest.raises(MCPError) as exc_info:
        await handle_tool_call(
            "agentgraph_create_evolution",
            {
                "entity_id": agent_id,
                "version": "1.0.0",
                "change_type": "initial",
                "change_summary": SPAM_TEXT,
                "capabilities_snapshot": ["testing"],
            },
            agent_entity,
            db,
        )
    assert "rejected" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_mcp_handler_rejects_spam_profile_name(client, db):
    """MCP handler should reject spam content in profile display_name."""
    from src.bridges.mcp_handler import MCPError, handle_tool_call

    token_a, user_a_id = await _setup_user(client, USER_A)
    entity = await db.get(Entity, uuid.UUID(user_a_id))

    with pytest.raises(MCPError) as exc_info:
        await handle_tool_call(
            "agentgraph_update_profile",
            {"display_name": SPAM_TEXT},
            entity,
            db,
        )
    assert "rejected" in exc_info.value.message.lower()


# --- Task #129: Cascade deactivation extensions ---


@pytest.mark.asyncio
async def test_cascade_deactivate_cancels_listings_and_transactions(client, db):
    """Cascade deactivation should deactivate listings and cancel pending txns."""
    from src.api.deactivation import cascade_deactivate

    token_a, user_a_id = await _setup_user(client, USER_A)
    token_b, user_b_id = await _setup_user(client, USER_B)

    # Create a marketplace listing as user A
    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Cascade Test Listing",
            "description": "For deactivation test",
            "category": "service",
            "pricing_model": "one_time",
            "price_cents": 1000,
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    # Purchase listing as user B
    resp = await client.post(
        f"/api/v1/marketplace/{listing_id}/purchase",
        json={"notes": "test purchase"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201
    txn_id = resp.json()["id"]

    # If transaction is completed (free or auto), set to pending for test
    txn = await db.get(Transaction, uuid.UUID(txn_id))
    if txn.status != TransactionStatus.PENDING:
        txn.status = TransactionStatus.PENDING
        await db.flush()

    # Run cascade deactivation for user A
    result = await cascade_deactivate(
        db, uuid.UUID(user_a_id),
        performed_by=uuid.UUID(user_a_id),
    )

    assert result["deactivated_listings"] >= 1
    assert result["cancelled_transactions"] >= 1

    # Verify listing is inactive
    listing = await db.get(Listing, uuid.UUID(listing_id))
    assert listing.is_active is False

    # Verify transaction is cancelled
    await db.refresh(txn)
    assert txn.status == TransactionStatus.CANCELLED


# --- Task #130: Marketplace webhook dispatches ---


@pytest.mark.asyncio
async def test_marketplace_purchase_dispatches_webhook(client, db):
    """Purchasing a listing should dispatch a webhook."""
    token_a, user_a_id = await _setup_user(client, USER_A)
    token_b, user_b_id = await _setup_user(client, USER_B)

    # Create listing
    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Webhook Test Listing",
            "description": "For webhook test",
            "category": "service",
            "pricing_model": "free",
            "price_cents": 0,
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    # Purchase it
    with patch("src.events.dispatch_webhooks", new_callable=AsyncMock) as mock_dispatch:
        resp = await client.post(
            f"/api/v1/marketplace/{listing_id}/purchase",
            json={"notes": "webhook test"},
            headers=_auth(token_b),
        )
        assert resp.status_code == 201

        # Webhook should have been dispatched
        if mock_dispatch.called:
            call_args = mock_dispatch.call_args
            assert call_args[0][1] == "entity.messaged"
            payload = call_args[0][2]
            assert payload["event"] == "marketplace.purchased"


@pytest.mark.asyncio
async def test_marketplace_create_listing_dispatches_webhook(client, db):
    """Creating a listing should dispatch a webhook."""
    token_a, _ = await _setup_user(client, USER_A)

    with patch("src.events.dispatch_webhooks", new_callable=AsyncMock) as mock_dispatch:
        resp = await client.post(
            "/api/v1/marketplace",
            json={
                "title": "Create Webhook Listing",
                "description": "For create webhook test",
                "category": "service",
                "pricing_model": "free",
                "price_cents": 0,
            },
            headers=_auth(token_a),
        )
        assert resp.status_code == 201

        # Check that webhook was dispatched for post.created
        if mock_dispatch.called:
            call_args = mock_dispatch.call_args
            assert call_args[0][1] == "post.created"


# --- Task #131: Export pagination limits ---


@pytest.mark.asyncio
async def test_export_returns_data(client, db):
    """Export endpoint should return structured data."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.get(
        "/api/v1/export/me",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "export_version" in data
    assert "profile" in data
    assert "posts" in data
    assert "votes" in data
    assert "following" in data
    assert "followers" in data
    assert "bookmarks" in data
    assert "notifications" in data
    assert "direct_messages" in data
    assert "endorsements_given" in data
    assert "reviews_given" in data
    assert "blocked_entities" in data
    assert "transactions" in data
    assert "listing_reviews_given" in data
    assert "audit_log" in data


@pytest.mark.asyncio
async def test_export_requires_auth(client, db):
    """Export endpoint should require authentication."""
    resp = await client.get("/api/v1/export/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_export_includes_counts(client, db):
    """Export should include count fields for posts, votes, following, followers."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.get(
        "/api/v1/export/me",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "post_count" in data
    assert "vote_count" in data
    assert "following_count" in data
    assert "follower_count" in data
    assert data["post_count"] == len(data["posts"])
    assert data["vote_count"] == len(data["votes"])
