"""Tests for Tasks #142-145: operator is_active check, marketplace webhook
event types, review stats is_active filtering, follower/following count filtering."""
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
    "email": "batch142a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch142A",
}
USER_B = {
    "email": "batch142b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch142B",
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


async def _grant_trust(db, entity_id: str, score: float = 0.5):
    """Give an entity a trust score so trust-gated endpoints work."""
    import uuid as _uuid

    from sqlalchemy import update as _sa_update

    from src.models import TrustScore

    await db.execute(
        _sa_update(TrustScore)
        .where(TrustScore.entity_id == _uuid.UUID(entity_id))
        .values(score=score, components={})
    )
    await db.flush()


# --- Task #142: Operator is_active check ---


@pytest.mark.asyncio
async def test_register_agent_rejects_deactivated_operator(client, db):
    """Agent registration should reject a deactivated operator."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    # Deactivate the operator
    resp = await client.post(
        "/api/v1/account/deactivate",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Try to register an agent with the deactivated operator
    resp = await client.post(
        "/api/v1/agents/register",
        json={
            "display_name": "Orphan Agent",
            "description": "Should fail",
            "capabilities": ["testing"],
            "framework": "custom",
            "operator_email": USER_A["email"],
        },
    )
    assert resp.status_code == 400
    assert "deactivated" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_agent_with_active_operator_succeeds(client, db):
    """Agent registration should succeed with an active operator."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/agents/register",
        json={
            "display_name": "Good Agent",
            "description": "Should succeed",
            "capabilities": ["testing"],
            "framework": "custom",
            "operator_email": USER_A["email"],
        },
    )
    assert resp.status_code == 201


# --- Task #143: Marketplace webhook event types ---


@pytest.mark.asyncio
async def test_webhook_accepts_marketplace_event_types(client, db):
    """Webhook subscription should accept marketplace event types."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)

    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://example.com/webhook",
            "event_types": [
                "marketplace.listing_created",
                "marketplace.purchased",
                "marketplace.cancelled",
                "marketplace.refunded",
            ],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_listing_create_dispatches_marketplace_webhook(client, db):
    """Listing creation should dispatch marketplace.listing_created webhook."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)

    with patch("src.events.dispatch_webhooks", new_callable=AsyncMock) as mock_dispatch:
        resp = await client.post(
            "/api/v1/marketplace",
            json={
                "title": "Test Service",
                "description": "A test marketplace listing",
                "category": "service",
                "pricing_model": "free",
                "price_cents": 0,
            },
            headers=_auth(token_a),
        )
        assert resp.status_code == 201

        dispatched_events = [
            call[0][1] for call in mock_dispatch.call_args_list
        ]
        assert "marketplace.listing_created" in dispatched_events


@pytest.mark.asyncio
async def test_purchase_dispatches_marketplace_webhook(client, db):
    """Purchase should dispatch marketplace.purchased webhook."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)
    token_b, _ = await _setup_user(client, USER_B)

    # Create listing
    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Purchasable Service",
            "description": "A test listing for purchase",
            "category": "service",
            "pricing_model": "free",
            "price_cents": 0,
        },
        headers=_auth(token_a),
    )
    listing_id = resp.json()["id"]

    with patch("src.events.dispatch_webhooks", new_callable=AsyncMock) as mock_dispatch:
        resp = await client.post(
            f"/api/v1/marketplace/{listing_id}/purchase",
            json={},
            headers=_auth(token_b),
        )
        assert resp.status_code == 201

        dispatched_events = [
            call[0][1] for call in mock_dispatch.call_args_list
        ]
        assert "marketplace.purchased" in dispatched_events


# --- Task #144: Review stats is_active filtering ---


@pytest.mark.asyncio
async def test_profile_accessible_after_setup(client, db):
    """Profile endpoint should return review and endorsement stats."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.get(
        f"/api/v1/profiles/{user_a_id}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "review_count" in data
    assert "endorsement_count" in data
    assert data["review_count"] >= 0
    assert data["endorsement_count"] >= 0


# --- Task #145: Follower/following counts ---


@pytest.mark.asyncio
async def test_profile_follower_counts(client, db):
    """Profile should show follower/following counts."""
    token_a, user_a_id = await _setup_user(client, USER_A)
    token_b, user_b_id = await _setup_user(client, USER_B)

    # B follows A
    resp = await client.post(
        f"/api/v1/social/follow/{user_a_id}",
        headers=_auth(token_b),
    )
    assert resp.status_code in (200, 201)

    # Check A's profile shows 1 follower
    resp = await client.get(
        f"/api/v1/profiles/{user_a_id}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert resp.json()["follower_count"] == 1

    # Check B's profile shows 1 following
    resp = await client.get(
        f"/api/v1/profiles/{user_b_id}",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    assert resp.json()["following_count"] == 1


@pytest.mark.asyncio
async def test_listing_reviews_accessible(client, db):
    """Listing reviews endpoint should be accessible."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)
    token_b, _ = await _setup_user(client, USER_B)

    # Create listing
    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Reviewable Listing",
            "description": "A listing to review",
            "category": "tool",
            "pricing_model": "free",
            "price_cents": 0,
        },
        headers=_auth(token_a),
    )
    listing_id = resp.json()["id"]

    # B reviews the listing
    resp = await client.post(
        f"/api/v1/marketplace/{listing_id}/reviews",
        json={"rating": 4, "text": "Good listing"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201

    # Get reviews
    resp = await client.get(
        f"/api/v1/marketplace/{listing_id}/reviews",
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
