"""Tests for Tasks #86-92: notification prefs, admin search, txn cancel/refund,
admin post hide, notification kind filter, profile browse privacy."""
from __future__ import annotations

from unittest.mock import patch

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
NOTIF_URL = "/api/v1/notifications"
ADMIN_URL = "/api/v1/admin"
MARKET_URL = "/api/v1/marketplace"
FEED_URL = "/api/v1/feed"
PROFILE_URL = "/api/v1/profiles"

USER_A = {
    "email": "batch86a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "BatchA",
}
USER_B = {
    "email": "batch86b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "BatchB",
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

    from src.models import TrustScore

    ts = TrustScore(
        id=_uuid.uuid4(),
        entity_id=entity_id,
        score=score,
        components={},
    )
    db.add(ts)
    await db.flush()


# --- Notification Preferences (Task #91) ---


@pytest.mark.asyncio
async def test_get_default_preferences(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)
    resp = await client.get(f"{NOTIF_URL}/preferences", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["follow_enabled"] is True
    assert data["reply_enabled"] is True
    assert data["message_enabled"] is True


@pytest.mark.asyncio
async def test_update_preferences(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    resp = await client.patch(
        f"{NOTIF_URL}/preferences",
        json={"follow_enabled": False, "vote_enabled": False},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["follow_enabled"] is False
    assert data["vote_enabled"] is False
    assert data["reply_enabled"] is True  # unchanged

    # Read back to verify persistence
    resp2 = await client.get(f"{NOTIF_URL}/preferences", headers=_auth(token))
    assert resp2.json()["follow_enabled"] is False


@pytest.mark.asyncio
async def test_preferences_unauthenticated(client: AsyncClient):
    resp = await client.get(f"{NOTIF_URL}/preferences")
    assert resp.status_code in (401, 403)


# --- Notification Kind Filter (Task #90) ---


@pytest.mark.asyncio
async def test_notification_kind_filter(client: AsyncClient):
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # Follow A to generate a "follow" notification
    await client.post(
        f"/api/v1/social/follow/{id_a}", headers=_auth(token_b),
    )

    # Get only "follow" notifications
    resp = await client.get(
        f"{NOTIF_URL}?kind=follow", headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    for n in data["notifications"]:
        assert n["kind"] == "follow"

    # Get non-existent kind
    resp2 = await client.get(
        f"{NOTIF_URL}?kind=nonexistent", headers=_auth(token_a),
    )
    assert resp2.status_code == 200
    assert len(resp2.json()["notifications"]) == 0


# --- Admin Entity Search (Task #87) ---


@pytest.mark.asyncio
async def test_admin_entity_search(client: AsyncClient, db):
    token, entity_id = await _setup_user(client, USER_A)

    # Make admin
    from src.models import Entity
    entity = await db.get(Entity, entity_id)
    entity.is_admin = True
    await db.flush()

    await _setup_user(client, USER_B)

    # Search by display_name
    resp = await client.get(
        f"{ADMIN_URL}/entities?q=BatchB", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    names = [e["display_name"] for e in data["entities"]]
    assert "BatchB" in names

    # Search by email
    resp2 = await client.get(
        f"{ADMIN_URL}/entities?q=batch86b", headers=_auth(token),
    )
    assert resp2.status_code == 200
    assert resp2.json()["total"] >= 1

    # Search with no results
    resp3 = await client.get(
        f"{ADMIN_URL}/entities?q=zzzznotfound", headers=_auth(token),
    )
    assert resp3.status_code == 200
    assert resp3.json()["total"] == 0


# --- Transaction Cancel/Refund (Task #88) ---


def _stripe_mocks():
    """Context manager to mock Stripe for paid purchases."""
    mock_status = {
        "charges_enabled": True,
        "payouts_enabled": True,
        "details_submitted": True,
    }
    mock_intent = {
        "client_secret": "pi_test_secret",
        "payment_intent_id": "pi_test_123",
    }
    return (
        patch("src.config.settings.stripe_secret_key", "sk_test_fake"),
        patch("src.payments.stripe_service.get_account_status", return_value=mock_status),
        patch("src.payments.stripe_service.create_payment_intent", return_value=mock_intent),
    )


@pytest.mark.asyncio
async def test_cancel_pending_transaction(client: AsyncClient, db):
    seller_token, seller_id = await _setup_user(client, USER_A)
    await _grant_trust(db, seller_id)
    buyer_token, _ = await _setup_user(client, USER_B)

    # Create paid listing
    listing_resp = await client.post(
        MARKET_URL,
        json={
            "title": "Paid Service",
            "description": "Costs money",
            "category": "service",
            "pricing_model": "one_time",
            "price_cents": 1000,
        },
        headers=_auth(seller_token),
    )
    listing_id = listing_resp.json()["id"]

    # Set up seller's Stripe account
    import uuid

    from src.models import Entity
    seller = await db.get(Entity, uuid.UUID(seller_id))
    seller.stripe_account_id = "acct_test_cancel"
    await db.flush()

    # Purchase (pending because non-free)
    p1, p2, p3 = _stripe_mocks()
    with p1, p2, p3:
        purchase_resp = await client.post(
            f"{MARKET_URL}/{listing_id}/purchase",
            json={},
            headers=_auth(buyer_token),
        )
    txn_id = purchase_resp.json()["id"]
    assert purchase_resp.json()["status"] == "escrow"

    # Cancel (must mock cancel_payment_intent since escrow cancel calls Stripe)
    with patch("src.payments.stripe_service.cancel_payment_intent",
               return_value={"payment_intent_id": "pi_test_123", "status": "canceled"}):
        cancel_resp = await client.patch(
            f"{MARKET_URL}/purchases/{txn_id}/cancel",
            headers=_auth(buyer_token),
        )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_not_buyer_fails(client: AsyncClient, db):
    seller_token, seller_id = await _setup_user(client, USER_A)
    await _grant_trust(db, seller_id)
    buyer_token, _ = await _setup_user(client, USER_B)

    listing_resp = await client.post(
        MARKET_URL,
        json={
            "title": "Paid Svc",
            "description": "Costs money",
            "category": "tool",
            "pricing_model": "one_time",
            "price_cents": 500,
        },
        headers=_auth(seller_token),
    )
    listing_id = listing_resp.json()["id"]

    # Set up seller's Stripe account
    import uuid

    from src.models import Entity
    seller = await db.get(Entity, uuid.UUID(seller_id))
    seller.stripe_account_id = "acct_test_cancel2"
    await db.flush()

    p1, p2, p3 = _stripe_mocks()
    with p1, p2, p3:
        purchase_resp = await client.post(
            f"{MARKET_URL}/{listing_id}/purchase",
            json={},
            headers=_auth(buyer_token),
        )
    txn_id = purchase_resp.json()["id"]

    # Seller tries to cancel — should fail
    resp = await client.patch(
        f"{MARKET_URL}/purchases/{txn_id}/cancel",
        headers=_auth(seller_token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_refund_completed_transaction(client: AsyncClient, db):
    seller_token, seller_id = await _setup_user(client, USER_A)
    await _grant_trust(db, seller_id)
    buyer_token, _ = await _setup_user(client, USER_B)

    # Free listing auto-completes
    listing_resp = await client.post(
        MARKET_URL,
        json={
            "title": "Free Bot",
            "description": "Free service",
            "category": "service",
            "pricing_model": "free",
        },
        headers=_auth(seller_token),
    )
    listing_id = listing_resp.json()["id"]

    purchase_resp = await client.post(
        f"{MARKET_URL}/{listing_id}/purchase",
        json={},
        headers=_auth(buyer_token),
    )
    txn_id = purchase_resp.json()["id"]
    assert purchase_resp.json()["status"] == "completed"

    # Seller refunds
    refund_resp = await client.patch(
        f"{MARKET_URL}/purchases/{txn_id}/refund",
        headers=_auth(seller_token),
    )
    assert refund_resp.status_code == 200
    assert refund_resp.json()["status"] == "refunded"


@pytest.mark.asyncio
async def test_refund_pending_fails(client: AsyncClient, db):
    seller_token, seller_id = await _setup_user(client, USER_A)
    await _grant_trust(db, seller_id)
    buyer_token, _ = await _setup_user(client, USER_B)

    listing_resp = await client.post(
        MARKET_URL,
        json={
            "title": "Paid Svc2",
            "description": "Costs money",
            "category": "data",
            "pricing_model": "one_time",
            "price_cents": 200,
        },
        headers=_auth(seller_token),
    )
    listing_id = listing_resp.json()["id"]

    # Set up seller's Stripe account
    import uuid

    from src.models import Entity
    seller = await db.get(Entity, uuid.UUID(seller_id))
    seller.stripe_account_id = "acct_test_refund"
    await db.flush()

    p1, p2, p3 = _stripe_mocks()
    with p1, p2, p3:
        purchase_resp = await client.post(
            f"{MARKET_URL}/{listing_id}/purchase",
            json={},
            headers=_auth(buyer_token),
        )
    txn_id = purchase_resp.json()["id"]

    # Try to refund a pending transaction
    resp = await client.patch(
        f"{MARKET_URL}/purchases/{txn_id}/refund",
        headers=_auth(seller_token),
    )
    assert resp.status_code == 400


# --- Admin Post Hide (Task #89) ---


@pytest.mark.asyncio
async def test_admin_hide_post(client: AsyncClient, db):
    token, entity_id = await _setup_user(client, USER_A)

    # Make admin
    from src.models import Entity
    entity = await db.get(Entity, entity_id)
    entity.is_admin = True
    await db.flush()

    # Create a post
    post_resp = await client.post(
        f"{FEED_URL}/posts",
        json={"content": "Should be hidden by admin"},
        headers=_auth(token),
    )
    post_id = post_resp.json()["id"]

    # Hide it
    resp = await client.patch(
        f"{ADMIN_URL}/posts/{post_id}/hide",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Post hidden"

    # Hide again — should be idempotent
    resp2 = await client.patch(
        f"{ADMIN_URL}/posts/{post_id}/hide",
        headers=_auth(token),
    )
    assert resp2.status_code == 200
    assert "already" in resp2.json()["message"].lower()


@pytest.mark.asyncio
async def test_admin_hide_post_non_admin(client: AsyncClient):
    token, _ = await _setup_user(client, USER_A)

    post_resp = await client.post(
        f"{FEED_URL}/posts",
        json={"content": "Non-admin cannot hide"},
        headers=_auth(token),
    )
    post_id = post_resp.json()["id"]

    resp = await client.patch(
        f"{ADMIN_URL}/posts/{post_id}/hide",
        headers=_auth(token),
    )
    assert resp.status_code == 403


# --- Profile Browse Privacy Filter (Task #92) ---


@pytest.mark.asyncio
async def test_profile_browse_excludes_private(client: AsyncClient, db):
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # Make user B's profile private
    from src.models import Entity, PrivacyTier
    entity_b = await db.get(Entity, id_b)
    entity_b.privacy_tier = PrivacyTier.PRIVATE
    await db.flush()

    # Browse should not include user B
    resp = await client.get(f"{PROFILE_URL}?q=BatchB")
    assert resp.status_code == 200
    names = [p["display_name"] for p in resp.json()["profiles"]]
    assert "BatchB" not in names

    # But user A should still appear
    resp2 = await client.get(f"{PROFILE_URL}?q=BatchA")
    assert resp2.status_code == 200
    names2 = [p["display_name"] for p in resp2.json()["profiles"]]
    assert "BatchA" in names2
