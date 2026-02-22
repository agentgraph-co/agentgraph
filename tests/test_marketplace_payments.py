"""Tests for Stripe Connect marketplace payment integration.

All Stripe API calls are mocked — no real Stripe interaction.
"""
from __future__ import annotations

import json
import uuid
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
MARKET_URL = "/api/v1/marketplace"


async def _setup_user(client: AsyncClient, email: str, name: str) -> tuple[str, str]:
    await client.post(
        REGISTER_URL,
        json={"email": email, "password": "Str0ngP@ss", "display_name": name},
    )
    resp = await client.post(
        LOGIN_URL, json={"email": email, "password": "Str0ngP@ss"},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


FREE_LISTING = {
    "title": "Free Helper Bot",
    "description": "A free helper bot for everyone",
    "category": "service",
    "tags": ["free"],
    "pricing_model": "free",
    "price_cents": 0,
}

PAID_LISTING = {
    "title": "Premium Analysis Service",
    "description": "Advanced AI analysis for your data",
    "category": "service",
    "tags": ["premium", "analysis"],
    "pricing_model": "one_time",
    "price_cents": 1000,
}


# --- Free listing tests (existing behavior preserved) ---


@pytest.mark.asyncio
async def test_purchase_free_listing_auto_completes(client: AsyncClient):
    """Free listings should auto-complete without Stripe."""
    seller_token, _ = await _setup_user(client, "freeseller@test.com", "FreeSeller")
    buyer_token, _ = await _setup_user(client, "freebuyer@test.com", "FreeBuyer")

    # Create free listing
    resp = await client.post(
        MARKET_URL, json=FREE_LISTING, headers=_auth(seller_token),
    )
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    # Purchase it
    resp = await client.post(
        f"{MARKET_URL}/{listing_id}/purchase",
        json={"notes": "Thanks!"},
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "completed"
    assert data["amount_cents"] == 0
    assert data["completed_at"] is not None
    assert data["client_secret"] is None
    assert data["platform_fee_cents"] is None


# --- Paid listing Stripe integration tests ---


@pytest.mark.asyncio
async def test_purchase_paid_listing_creates_payment_intent(client: AsyncClient, db):
    """Paid listings should create a Stripe PaymentIntent and return client_secret."""
    seller_token, seller_id = await _setup_user(
        client, "paidseller@test.com", "PaidSeller",
    )
    buyer_token, _ = await _setup_user(client, "paidbuyer@test.com", "PaidBuyer")

    # Create paid listing
    resp = await client.post(
        MARKET_URL, json=PAID_LISTING, headers=_auth(seller_token),
    )
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    # Set up seller's Stripe account in DB
    from src.models import Entity
    seller = await db.get(Entity, uuid.UUID(seller_id))
    seller.stripe_account_id = "acct_test_seller_123"
    await db.flush()

    # Mock Stripe calls
    mock_account_status = {
        "charges_enabled": True,
        "payouts_enabled": True,
        "details_submitted": True,
    }
    mock_intent = {
        "client_secret": "pi_test_secret_abc123",
        "payment_intent_id": "pi_test_123",
    }

    with patch("src.api.marketplace_router.get_account_status", return_value=mock_account_status), \
         patch("src.api.marketplace_router.create_payment_intent", return_value=mock_intent):
        resp = await client.post(
            f"{MARKET_URL}/{listing_id}/purchase",
            json={"notes": "Paid purchase"},
            headers=_auth(buyer_token),
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["client_secret"] == "pi_test_secret_abc123"
    assert data["amount_cents"] == 1000
    assert data["platform_fee_cents"] == 100  # 10% of 1000
    assert data["completed_at"] is None


@pytest.mark.asyncio
async def test_purchase_paid_listing_without_seller_stripe_account(client: AsyncClient):
    """Purchasing a paid listing from a seller without Stripe setup returns 400."""
    seller_token, _ = await _setup_user(
        client, "noseller@test.com", "NoStripeSeller",
    )
    buyer_token, _ = await _setup_user(client, "nobuyer@test.com", "NoBuyer")

    resp = await client.post(
        MARKET_URL, json=PAID_LISTING, headers=_auth(seller_token),
    )
    listing_id = resp.json()["id"]

    with patch("src.config.settings.stripe_secret_key", "sk_test_fake"):
        resp = await client.post(
            f"{MARKET_URL}/{listing_id}/purchase",
            json={},
            headers=_auth(buyer_token),
        )

    assert resp.status_code == 400
    assert "payment processing" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_purchase_paid_listing_seller_charges_not_enabled(
    client: AsyncClient, db,
):
    """Purchasing when seller charges are not enabled returns 400."""
    seller_token, seller_id = await _setup_user(
        client, "nochgseller@test.com", "NoChargeSeller",
    )
    buyer_token, _ = await _setup_user(client, "nochgbuyer@test.com", "NoChargeBuyer")

    resp = await client.post(
        MARKET_URL, json=PAID_LISTING, headers=_auth(seller_token),
    )
    listing_id = resp.json()["id"]

    from src.models import Entity
    seller = await db.get(Entity, uuid.UUID(seller_id))
    seller.stripe_account_id = "acct_not_ready"
    await db.flush()

    mock_status = {
        "charges_enabled": False,
        "payouts_enabled": False,
        "details_submitted": False,
    }

    with patch("src.config.settings.stripe_secret_key", "sk_test_fake"), \
         patch("src.api.marketplace_router.get_account_status", return_value=mock_status):
        resp = await client.post(
            f"{MARKET_URL}/{listing_id}/purchase",
            json={},
            headers=_auth(buyer_token),
        )

    assert resp.status_code == 400
    assert "not fully activated" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_double_purchase_prevention(client: AsyncClient, db):
    """Cannot purchase the same listing twice while a purchase is PENDING."""
    seller_token, seller_id = await _setup_user(
        client, "dupseller@test.com", "DupSeller",
    )
    buyer_token, _ = await _setup_user(client, "dupbuyer@test.com", "DupBuyer")

    resp = await client.post(
        MARKET_URL, json=PAID_LISTING, headers=_auth(seller_token),
    )
    listing_id = resp.json()["id"]

    from src.models import Entity
    seller = await db.get(Entity, uuid.UUID(seller_id))
    seller.stripe_account_id = "acct_dup_test"
    await db.flush()

    mock_status = {
        "charges_enabled": True,
        "payouts_enabled": True,
        "details_submitted": True,
    }
    mock_intent = {
        "client_secret": "pi_secret_dup",
        "payment_intent_id": "pi_dup_123",
    }

    with patch("src.config.settings.stripe_secret_key", "sk_test_fake"), \
         patch("src.api.marketplace_router.get_account_status", return_value=mock_status), \
         patch("src.api.marketplace_router.create_payment_intent", return_value=mock_intent):
        # First purchase
        resp1 = await client.post(
            f"{MARKET_URL}/{listing_id}/purchase",
            json={},
            headers=_auth(buyer_token),
        )
        assert resp1.status_code == 201

        # Second purchase should be blocked
        resp2 = await client.post(
            f"{MARKET_URL}/{listing_id}/purchase",
            json={},
            headers=_auth(buyer_token),
        )
        assert resp2.status_code == 400
        assert "pending" in resp2.json()["detail"].lower()


# --- Webhook tests ---


@pytest.mark.asyncio
async def test_webhook_payment_intent_succeeded(client: AsyncClient, db):
    """Webhook payment_intent.succeeded should mark transaction COMPLETED."""
    from src.models import Entity, Listing, Transaction, TransactionStatus

    # Create entities directly
    seller = Entity(
        id=uuid.uuid4(), type="human", display_name="WebhookSeller",
        did_web=f"did:web:test:{uuid.uuid4().hex[:8]}",
        email=f"wh_seller_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="fake",
    )
    buyer = Entity(
        id=uuid.uuid4(), type="human", display_name="WebhookBuyer",
        did_web=f"did:web:test:{uuid.uuid4().hex[:8]}",
        email=f"wh_buyer_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="fake",
    )
    db.add_all([seller, buyer])
    await db.flush()

    listing = Listing(
        id=uuid.uuid4(), entity_id=seller.id, title="WH Test",
        description="Test listing", category="service",
        pricing_model="one_time", price_cents=2000,
    )
    db.add(listing)
    await db.flush()

    txn = Transaction(
        id=uuid.uuid4(), listing_id=listing.id,
        buyer_entity_id=buyer.id, seller_entity_id=seller.id,
        amount_cents=2000, status=TransactionStatus.PENDING,
        listing_title="WH Test", listing_category="service",
        stripe_payment_intent_id="pi_webhook_test_123",
        platform_fee_cents=200,
    )
    db.add(txn)
    await db.flush()

    # Simulate Stripe webhook event
    event = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_webhook_test_123",
                "amount": 2000,
                "currency": "usd",
            },
        },
    }

    with patch("src.config.settings.stripe_webhook_secret", "whsec_test"), \
         patch(
             "src.api.marketplace_router.verify_webhook_signature",
             return_value=event,
         ):
        resp = await client.post(
            f"{MARKET_URL}/stripe/webhook",
            content=json.dumps(event),
            headers={
                "stripe-signature": "t=123,v1=fakesig",
                "content-type": "application/json",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify transaction was completed
    await db.refresh(txn)
    assert txn.status == TransactionStatus.COMPLETED
    assert txn.completed_at is not None


@pytest.mark.asyncio
async def test_webhook_charge_refunded(client: AsyncClient, db):
    """Webhook charge.refunded should mark transaction REFUNDED."""
    from datetime import datetime, timezone

    from src.models import Entity, Listing, Transaction, TransactionStatus

    seller = Entity(
        id=uuid.uuid4(), type="human", display_name="RefundSeller",
        did_web=f"did:web:test:{uuid.uuid4().hex[:8]}",
        email=f"rf_seller_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="fake",
    )
    buyer = Entity(
        id=uuid.uuid4(), type="human", display_name="RefundBuyer",
        did_web=f"did:web:test:{uuid.uuid4().hex[:8]}",
        email=f"rf_buyer_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="fake",
    )
    db.add_all([seller, buyer])
    await db.flush()

    listing = Listing(
        id=uuid.uuid4(), entity_id=seller.id, title="Refund Test",
        description="Test listing", category="service",
        pricing_model="one_time", price_cents=3000,
    )
    db.add(listing)
    await db.flush()

    txn = Transaction(
        id=uuid.uuid4(), listing_id=listing.id,
        buyer_entity_id=buyer.id, seller_entity_id=seller.id,
        amount_cents=3000, status=TransactionStatus.COMPLETED,
        listing_title="Refund Test", listing_category="service",
        stripe_payment_intent_id="pi_refund_test_456",
        platform_fee_cents=300,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(txn)
    await db.flush()

    event = {
        "type": "charge.refunded",
        "data": {
            "object": {
                "id": "ch_test_refund_123",
                "payment_intent": "pi_refund_test_456",
            },
        },
    }

    with patch("src.config.settings.stripe_webhook_secret", "whsec_test"), \
         patch(
             "src.api.marketplace_router.verify_webhook_signature",
             return_value=event,
         ):
        resp = await client.post(
            f"{MARKET_URL}/stripe/webhook",
            content=json.dumps(event),
            headers={
                "stripe-signature": "t=123,v1=fakesig",
                "content-type": "application/json",
            },
        )

    assert resp.status_code == 200
    await db.refresh(txn)
    assert txn.status == TransactionStatus.REFUNDED


@pytest.mark.asyncio
async def test_webhook_invalid_signature(client: AsyncClient):
    """Webhook with invalid signature returns 400."""
    import stripe as stripe_mod

    with patch("src.config.settings.stripe_webhook_secret", "whsec_test"), \
         patch(
             "src.api.marketplace_router.verify_webhook_signature",
             side_effect=stripe_mod.error.SignatureVerificationError(
                 "bad sig", "sig_header",
             ),
         ):
        resp = await client.post(
            f"{MARKET_URL}/stripe/webhook",
            content=b'{"type":"test"}',
            headers={
                "stripe-signature": "t=123,v1=badsig",
                "content-type": "application/json",
            },
        )

    assert resp.status_code == 400
    assert "signature" in resp.json()["detail"].lower()


# --- Connect onboarding tests ---


@pytest.mark.asyncio
async def test_connect_onboard_creates_account(client: AsyncClient):
    """Connect onboard creates Stripe account and returns onboarding URL."""
    token, entity_id = await _setup_user(
        client, "onboard@test.com", "OnboardSeller",
    )

    with patch("src.config.settings.stripe_secret_key", "sk_test_fake"), \
         patch(
             "src.api.marketplace_router.create_connect_account",
             return_value="acct_new_test",
         ), \
         patch(
             "src.api.marketplace_router.create_onboarding_link",
             return_value="https://connect.stripe.com/setup/test",
         ):
        resp = await client.post(
            f"{MARKET_URL}/connect/onboard",
            json={
                "return_url": "http://localhost:5173/settings",
                "refresh_url": "http://localhost:5173/settings?refresh=1",
            },
            headers=_auth(token),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["onboarding_url"] == "https://connect.stripe.com/setup/test"
    assert data["account_id"] == "acct_new_test"


@pytest.mark.asyncio
async def test_connect_onboard_existing_account(client: AsyncClient, db):
    """Connect onboard with existing account generates new onboarding link."""
    token, entity_id = await _setup_user(
        client, "existing_onboard@test.com", "ExistingSeller",
    )

    # Pre-set Stripe account
    from src.models import Entity
    entity = await db.get(Entity, uuid.UUID(entity_id))
    entity.stripe_account_id = "acct_existing_123"
    await db.flush()

    with patch("src.config.settings.stripe_secret_key", "sk_test_fake"), \
         patch(
             "src.api.marketplace_router.create_onboarding_link",
             return_value="https://connect.stripe.com/setup/resume",
         ):
        resp = await client.post(
            f"{MARKET_URL}/connect/onboard",
            json={
                "return_url": "http://localhost:5173/settings",
                "refresh_url": "http://localhost:5173/settings?refresh=1",
            },
            headers=_auth(token),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["account_id"] == "acct_existing_123"


# --- Connect status tests ---


@pytest.mark.asyncio
async def test_connect_status_returns_account_info(client: AsyncClient, db):
    """Connect status returns Stripe account details."""
    token, entity_id = await _setup_user(
        client, "status@test.com", "StatusSeller",
    )

    from src.models import Entity
    entity = await db.get(Entity, uuid.UUID(entity_id))
    entity.stripe_account_id = "acct_status_test"
    await db.flush()

    mock_status = {
        "charges_enabled": True,
        "payouts_enabled": True,
        "details_submitted": True,
    }

    with patch("src.config.settings.stripe_secret_key", "sk_test_fake"), \
         patch(
             "src.api.marketplace_router.get_account_status",
             return_value=mock_status,
         ):
        resp = await client.get(
            f"{MARKET_URL}/connect/status",
            headers=_auth(token),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["charges_enabled"] is True
    assert data["payouts_enabled"] is True
    assert data["details_submitted"] is True


@pytest.mark.asyncio
async def test_connect_status_no_account_returns_404(client: AsyncClient):
    """Connect status with no Stripe account returns 404."""
    token, _ = await _setup_user(
        client, "nostatus@test.com", "NoStatusSeller",
    )

    with patch("src.config.settings.stripe_secret_key", "sk_test_fake"):
        resp = await client.get(
            f"{MARKET_URL}/connect/status",
            headers=_auth(token),
        )

    assert resp.status_code == 404


# --- Platform fee calculation tests ---


@pytest.mark.asyncio
async def test_platform_fee_calculation(client: AsyncClient, db):
    """Verify platform fee = price * percent / 100."""
    seller_token, seller_id = await _setup_user(
        client, "feeseller@test.com", "FeeSeller",
    )
    buyer_token, _ = await _setup_user(client, "feebuyer@test.com", "FeeBuyer")

    # Create listing at $25.00 (2500 cents)
    listing_data = {**PAID_LISTING, "price_cents": 2500}
    resp = await client.post(
        MARKET_URL, json=listing_data, headers=_auth(seller_token),
    )
    listing_id = resp.json()["id"]

    from src.models import Entity
    seller = await db.get(Entity, uuid.UUID(seller_id))
    seller.stripe_account_id = "acct_fee_test"
    await db.flush()

    mock_status = {
        "charges_enabled": True,
        "payouts_enabled": True,
        "details_submitted": True,
    }
    mock_intent = {
        "client_secret": "pi_fee_secret",
        "payment_intent_id": "pi_fee_123",
    }

    pi_path = "src.api.marketplace_router.create_payment_intent"
    with patch("src.config.settings.stripe_secret_key", "sk_test_fake"), \
         patch("src.config.settings.stripe_platform_fee_percent", 10), \
         patch("src.api.marketplace_router.get_account_status", return_value=mock_status), \
         patch(pi_path, return_value=mock_intent) as mock_pi:
        resp = await client.post(
            f"{MARKET_URL}/{listing_id}/purchase",
            json={},
            headers=_auth(buyer_token),
        )

    assert resp.status_code == 201
    data = resp.json()
    # 10% of 2500 = 250
    assert data["platform_fee_cents"] == 250

    # Verify create_payment_intent was called with correct fee
    mock_pi.assert_called_once()
    call_kwargs = mock_pi.call_args
    assert call_kwargs[1]["platform_fee_cents"] == 250 or call_kwargs[0][2] == 250


@pytest.mark.asyncio
async def test_payment_not_configured_returns_503(client: AsyncClient):
    """When stripe_secret_key is None, paid purchases return 503."""
    seller_token, _ = await _setup_user(
        client, "no_stripe_seller@test.com", "NoStripeSeller2",
    )
    buyer_token, _ = await _setup_user(
        client, "no_stripe_buyer@test.com", "NoStripeBuyer2",
    )

    resp = await client.post(
        MARKET_URL, json=PAID_LISTING, headers=_auth(seller_token),
    )
    listing_id = resp.json()["id"]

    # stripe_secret_key defaults to None, so no need to patch
    resp = await client.post(
        f"{MARKET_URL}/{listing_id}/purchase",
        json={},
        headers=_auth(buyer_token),
    )
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"].lower()
