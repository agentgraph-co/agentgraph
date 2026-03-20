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

SELLER = {
    "email": "txn_seller@example.com",
    "password": "Str0ngP@ss",
    "display_name": "TxnSeller",
}
BUYER = {
    "email": "txn_buyer@example.com",
    "password": "Str0ngP@ss",
    "display_name": "TxnBuyer",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _grant_trust(db, entity_id: str, score: float = 0.5):
    import uuid as _uuid

    from sqlalchemy import update as _sa_update

    from src.models import TrustScore
    await db.execute(
        _sa_update(TrustScore)
        .where(TrustScore.entity_id == _uuid.UUID(entity_id))
        .values(score=score, components={})
    )
    await db.flush()


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


async def _create_listing(
    client: AsyncClient, token: str,
    pricing_model: str = "free", price_cents: int = 0,
) -> str:
    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Test Service",
            "description": "A test service",
            "category": "service",
            "pricing_model": pricing_model,
            "price_cents": price_cents,
            "tags": ["test"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_purchase_free_listing(client: AsyncClient, db):
    """Purchasing a free listing auto-completes."""
    seller_token, seller_id = await _setup_user(client, SELLER)
    buyer_token, _ = await _setup_user(client, BUYER)
    await _grant_trust(db, seller_id)
    listing_id = await _create_listing(client, seller_token)

    resp = await client.post(
        f"/api/v1/marketplace/{listing_id}/purchase",
        json={"notes": "Looking forward to using this!"},
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "completed"
    assert data["amount_cents"] == 0
    assert data["listing_title"] == "Test Service"
    assert data["notes"] == "Looking forward to using this!"
    assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_purchase_paid_listing_pending(client: AsyncClient, db):
    """Purchasing a paid listing creates a pending transaction."""
    import uuid

    from src.models import Entity

    seller_token, seller_id = await _setup_user(client, SELLER)
    buyer_token, _ = await _setup_user(client, BUYER)
    await _grant_trust(db, seller_id)
    listing_id = await _create_listing(
        client, seller_token, pricing_model="one_time", price_cents=999,
    )

    # Set up seller's Stripe account
    seller = await db.get(Entity, uuid.UUID(seller_id))
    seller.stripe_account_id = "acct_test_paid"
    await db.flush()

    mock_status = {
        "charges_enabled": True,
        "payouts_enabled": True,
        "details_submitted": True,
    }
    mock_intent = {
        "client_secret": "pi_test_secret",
        "payment_intent_id": "pi_test_123",
    }

    with patch("src.config.settings.stripe_secret_key", "sk_test_fake"), \
         patch("src.payments.stripe_service.get_account_status", return_value=mock_status), \
         patch("src.payments.stripe_service.create_payment_intent", return_value=mock_intent):
        resp = await client.post(
            f"/api/v1/marketplace/{listing_id}/purchase",
            json={},
            headers=_auth(buyer_token),
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "escrow"
    assert data["amount_cents"] == 999
    assert data["completed_at"] is None


@pytest.mark.asyncio
async def test_cannot_purchase_own_listing(client: AsyncClient, db):
    """Seller cannot purchase their own listing."""
    seller_token, seller_id = await _setup_user(client, SELLER)
    await _grant_trust(db, seller_id)
    listing_id = await _create_listing(client, seller_token)

    resp = await client.post(
        f"/api/v1/marketplace/{listing_id}/purchase",
        json={},
        headers=_auth(seller_token),
    )
    assert resp.status_code == 400
    assert "own listing" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_purchase_history(client: AsyncClient, db):
    """Buyer can see their purchase history."""
    seller_token, seller_id = await _setup_user(client, SELLER)
    buyer_token, _ = await _setup_user(client, BUYER)
    await _grant_trust(db, seller_id)
    listing_id = await _create_listing(client, seller_token)

    # Purchase
    await client.post(
        f"/api/v1/marketplace/{listing_id}/purchase",
        json={},
        headers=_auth(buyer_token),
    )

    # Check buyer history
    resp = await client.get(
        "/api/v1/marketplace/purchases/history?role=buyer",
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["transactions"][0]["listing_title"] == "Test Service"

    # Check seller history
    resp = await client.get(
        "/api/v1/marketplace/purchases/history?role=seller",
        headers=_auth(seller_token),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_get_transaction_detail(client: AsyncClient, db):
    """Can get a specific transaction by ID."""
    seller_token, seller_id = await _setup_user(client, SELLER)
    buyer_token, _ = await _setup_user(client, BUYER)
    await _grant_trust(db, seller_id)
    listing_id = await _create_listing(client, seller_token)

    resp = await client.post(
        f"/api/v1/marketplace/{listing_id}/purchase",
        json={},
        headers=_auth(buyer_token),
    )
    txn_id = resp.json()["id"]

    # Buyer can see it
    resp = await client.get(
        f"/api/v1/marketplace/purchases/{txn_id}",
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == txn_id

    # Seller can see it
    resp = await client.get(
        f"/api/v1/marketplace/purchases/{txn_id}",
        headers=_auth(seller_token),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_purchase_notification_sent(client: AsyncClient, db):
    """Seller receives a notification when their listing is purchased."""
    seller_token, seller_id = await _setup_user(client, SELLER)
    buyer_token, _ = await _setup_user(client, BUYER)
    await _grant_trust(db, seller_id)
    listing_id = await _create_listing(client, seller_token)

    await client.post(
        f"/api/v1/marketplace/{listing_id}/purchase",
        json={},
        headers=_auth(buyer_token),
    )

    resp = await client.get(
        "/api/v1/notifications", headers=_auth(seller_token),
    )
    assert resp.status_code == 200
    notifs = resp.json()["notifications"]
    purchase_notifs = [n for n in notifs if "purchase" in n["title"].lower()]
    assert len(purchase_notifs) >= 1
