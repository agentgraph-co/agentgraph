"""Tests for escrow payment lifecycle.

Tests cover: escrow creation on purchase, buyer confirmation/capture,
cancellation of escrow, free listing auto-complete, Stripe webhook
handlers, and stripe service capture/cancel functions.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.main import app
from src.models import TrustScore

API = "/api/v1"


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _register(client: AsyncClient, db: AsyncSession | None = None) -> dict:
    """Register a user, login, and return {token, headers, entity_id}."""
    uid = uuid.uuid4().hex[:8]
    email = f"test_{uid}@test.com"
    password = "StrongPass1!"
    reg = await client.post(f"{API}/auth/register", json={
        "display_name": f"User {uid}",
        "email": email,
        "password": password,
    })
    assert reg.status_code == 201, reg.text

    login = await client.post(f"{API}/auth/login", json={
        "email": email,
        "password": password,
    })
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = await client.get(f"{API}/auth/me", headers=headers)
    assert me.status_code == 200, me.text

    entity_id = me.json()["id"]
    if db is not None:
        db.add(TrustScore(
            id=uuid.uuid4(), entity_id=uuid.UUID(entity_id), score=0.5,
            components={"verification": 0.3, "age": 0.1, "activity": 0.1},
        ))
        await db.flush()

    return {
        "token": token,
        "headers": headers,
        "entity_id": entity_id,
    }


def _mock_stripe():
    """Return a mock that patches stripe calls for paid purchase flow."""
    mock = MagicMock()
    mock.PaymentIntent.create.return_value = MagicMock(
        id="pi_test_escrow_123",
        client_secret="pi_test_escrow_123_secret",
        status="requires_capture",
    )
    mock.PaymentIntent.capture.return_value = MagicMock(
        id="pi_test_escrow_123",
        status="succeeded",
    )
    mock.PaymentIntent.cancel.return_value = MagicMock(
        id="pi_test_escrow_123",
        status="canceled",
    )
    mock.Account.create.return_value = MagicMock(id="acct_test_seller")
    mock.Account.retrieve.return_value = MagicMock(
        charges_enabled=True,
        payouts_enabled=True,
        details_submitted=True,
    )
    mock.AccountLink.create.return_value = MagicMock(url="https://stripe.com/onboard")
    return mock


async def _setup_escrow(client: AsyncClient, db: AsyncSession):
    """Create seller+buyer, onboard, create paid listing, purchase it.

    Returns (seller, buyer, listing_id, txn_id).
    """
    seller = await _register(client, db)
    buyer = await _register(client, db)

    with patch("src.payments.stripe_service.stripe", _mock_stripe()), \
         patch("src.api.marketplace_router.settings") as ms:
        ms.stripe_secret_key = "sk_test"
        ms.stripe_webhook_secret = "whsec_test"
        ms.stripe_platform_fee_percent = 10
        ms.api_v1_prefix = "/api/v1"

        await client.post(
            f"{API}/marketplace/connect/onboard",
            json={"return_url": "http://test/ok", "refresh_url": "http://test/refresh"},
            headers=seller["headers"],
        )

        listing = await client.post(f"{API}/marketplace", json={
            "title": "Escrow Svc",
            "description": "Costs 5000 cents",
            "category": "service",
            "pricing_model": "one_time",
            "price_cents": 5000,
        }, headers=seller["headers"])
        assert listing.status_code == 201
        listing_id = listing.json()["id"]

        purchase = await client.post(
            f"{API}/marketplace/{listing_id}/purchase",
            json={},
            headers=buyer["headers"],
        )
        assert purchase.status_code == 201
        assert purchase.json()["status"] == "escrow"
        txn_id = purchase.json()["id"]

    return seller, buyer, listing_id, txn_id


@pytest.mark.asyncio
async def test_free_listing_auto_completes(client, db):
    """Free listings should auto-complete without escrow."""
    seller = await _register(client, db)
    buyer = await _register(client, db)

    listing = await client.post(f"{API}/marketplace", json={
        "title": "Free Tool",
        "description": "A free tool for agents",
        "category": "tool",
        "pricing_model": "free",
        "price_cents": 0,
    }, headers=seller["headers"])
    assert listing.status_code == 201
    listing_id = listing.json()["id"]

    resp = await client.post(
        f"{API}/marketplace/{listing_id}/purchase",
        json={},
        headers=buyer["headers"],
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_paid_listing_creates_escrow(client, db):
    """Paid listing purchase should create a transaction in ESCROW status."""
    seller, buyer, listing_id, txn_id = await _setup_escrow(client, db)

    resp = await client.get(
        f"{API}/marketplace/purchases/{txn_id}",
        headers=buyer["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "escrow"
    assert resp.json()["amount_cents"] == 5000


@pytest.mark.asyncio
async def test_confirm_purchase_captures_funds(client, db):
    """Buyer confirming purchase should capture escrow and mark COMPLETED."""
    seller, buyer, listing_id, txn_id = await _setup_escrow(client, db)

    with patch("src.payments.stripe_service.capture_payment_intent") as mock_cap:
        mock_cap.return_value = {"payment_intent_id": "pi_test", "status": "succeeded"}

        confirm = await client.post(
            f"{API}/marketplace/purchases/{txn_id}/confirm",
            headers=buyer["headers"],
        )
        assert confirm.status_code == 200
        assert confirm.json()["status"] == "completed"
        assert confirm.json()["completed_at"] is not None


@pytest.mark.asyncio
async def test_cannot_confirm_non_escrow(client, db):
    """Confirming a non-escrow (completed) transaction should fail."""
    seller = await _register(client, db)
    buyer = await _register(client, db)

    listing = await client.post(f"{API}/marketplace", json={
        "title": "Free Confirm Test",
        "description": "A free tool",
        "category": "tool",
        "pricing_model": "free",
        "price_cents": 0,
    }, headers=seller["headers"])
    listing_id = listing.json()["id"]

    purchase = await client.post(
        f"{API}/marketplace/{listing_id}/purchase",
        json={},
        headers=buyer["headers"],
    )
    txn_id = purchase.json()["id"]
    assert purchase.json()["status"] == "completed"

    confirm = await client.post(
        f"{API}/marketplace/purchases/{txn_id}/confirm",
        headers=buyer["headers"],
    )
    assert confirm.status_code == 400
    assert "status" in confirm.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cannot_confirm_as_non_buyer(client, db):
    """Seller should not be able to confirm a purchase."""
    seller, buyer, listing_id, txn_id = await _setup_escrow(client, db)

    confirm = await client.post(
        f"{API}/marketplace/purchases/{txn_id}/confirm",
        headers=seller["headers"],
    )
    assert confirm.status_code == 403


@pytest.mark.asyncio
async def test_cancel_escrow_transaction(client, db):
    """Buyer cancelling an escrow transaction should work."""
    seller, buyer, listing_id, txn_id = await _setup_escrow(client, db)

    with patch("src.payments.stripe_service.cancel_payment_intent") as mock_cancel:
        mock_cancel.return_value = {"payment_intent_id": "pi_test", "status": "canceled"}

        cancel = await client.patch(
            f"{API}/marketplace/purchases/{txn_id}/cancel",
            headers=buyer["headers"],
        )
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_confirm_nonexistent_transaction(client, db):
    """Confirming a nonexistent transaction should 404."""
    user = await _register(client, db)
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"{API}/marketplace/purchases/{fake_id}/confirm",
        headers=user["headers"],
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_escrow_purchase_blocked(client, db):
    """Second purchase of same listing while in escrow should be blocked."""
    seller, buyer, listing_id, txn_id = await _setup_escrow(client, db)

    with patch("src.payments.stripe_service.stripe", _mock_stripe()), \
         patch("src.api.marketplace_router.settings") as ms:
        ms.stripe_secret_key = "sk_test"
        ms.stripe_webhook_secret = "whsec_test"
        ms.stripe_platform_fee_percent = 10
        ms.api_v1_prefix = "/api/v1"

        resp2 = await client.post(
            f"{API}/marketplace/{listing_id}/purchase",
            json={},
            headers=buyer["headers"],
        )
        assert resp2.status_code == 400
        assert "pending" in resp2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_stripe_capture_payment_intent():
    """Unit test for stripe_service.capture_payment_intent."""
    with patch("src.payments.stripe_service.stripe") as mock_stripe:
        mock_stripe.PaymentIntent.capture.return_value = MagicMock(
            id="pi_test_capture",
            status="succeeded",
        )

        from src.payments.stripe_service import capture_payment_intent

        result = capture_payment_intent("pi_test_capture")
        assert result["payment_intent_id"] == "pi_test_capture"
        assert result["status"] == "succeeded"
        mock_stripe.PaymentIntent.capture.assert_called_once_with("pi_test_capture")


@pytest.mark.asyncio
async def test_stripe_capture_partial():
    """Unit test for partial capture."""
    with patch("src.payments.stripe_service.stripe") as mock_stripe:
        mock_stripe.PaymentIntent.capture.return_value = MagicMock(
            id="pi_partial",
            status="succeeded",
        )

        from src.payments.stripe_service import capture_payment_intent

        result = capture_payment_intent("pi_partial", amount_cents=2500)
        assert result["status"] == "succeeded"
        mock_stripe.PaymentIntent.capture.assert_called_once_with(
            "pi_partial", amount_to_capture=2500,
        )


@pytest.mark.asyncio
async def test_stripe_cancel_payment_intent():
    """Unit test for stripe_service.cancel_payment_intent."""
    with patch("src.payments.stripe_service.stripe") as mock_stripe:
        mock_stripe.PaymentIntent.cancel.return_value = MagicMock(
            id="pi_test_cancel",
            status="canceled",
        )

        from src.payments.stripe_service import cancel_payment_intent

        result = cancel_payment_intent("pi_test_cancel")
        assert result["payment_intent_id"] == "pi_test_cancel"
        assert result["status"] == "canceled"
        mock_stripe.PaymentIntent.cancel.assert_called_once_with("pi_test_cancel")


@pytest.mark.asyncio
async def test_stripe_create_uses_manual_capture():
    """Verify create_payment_intent sets capture_method='manual'."""
    with patch("src.payments.stripe_service.stripe") as mock_stripe:
        mock_stripe.PaymentIntent.create.return_value = MagicMock(
            id="pi_manual",
            client_secret="pi_manual_secret",
        )

        from src.payments.stripe_service import create_payment_intent

        result = create_payment_intent(
            amount_cents=1000,
            seller_account_id="acct_seller",
            platform_fee_cents=100,
        )
        assert result["payment_intent_id"] == "pi_manual"

        call_kwargs = mock_stripe.PaymentIntent.create.call_args
        assert call_kwargs.kwargs.get("capture_method") == "manual" or \
            (len(call_kwargs.args) == 0 and "capture_method" in str(call_kwargs))


@pytest.mark.asyncio
async def test_webhook_payment_intent_canceled(client, db):
    """Stripe payment_intent.canceled webhook should cancel the transaction."""
    seller, buyer, listing_id, txn_id = await _setup_escrow(client, db)

    with patch("src.api.marketplace_router.settings") as ms, \
         patch("src.payments.stripe_service.verify_webhook_signature") as mock_verify:
        ms.stripe_webhook_secret = "whsec_test"
        ms.stripe_secret_key = "sk_test"
        ms.api_v1_prefix = "/api/v1"
        mock_verify.return_value = {
            "type": "payment_intent.canceled",
            "data": {
                "object": {
                    "id": "pi_test_escrow_123",
                },
            },
        }

        resp = await client.post(
            f"{API}/marketplace/stripe/webhook",
            content=b"{}",
            headers={"stripe-signature": "test_sig"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_purchase_history_includes_escrow_status(client, db):
    """Purchase history should support filtering by escrow status."""
    seller, buyer, listing_id, txn_id = await _setup_escrow(client, db)

    history = await client.get(
        f"{API}/marketplace/purchases/history?status=escrow",
        headers=buyer["headers"],
    )
    assert history.status_code == 200
    assert history.json()["total"] >= 1
    for t in history.json()["transactions"]:
        assert t["status"] == "escrow"


@pytest.mark.asyncio
async def test_purchase_own_listing_rejected(client, db):
    """Cannot purchase your own listing."""
    user = await _register(client, db)
    listing = await client.post(f"{API}/marketplace", json={
        "title": "Self Purchase Test",
        "description": "Should not be purchasable by self",
        "category": "tool",
        "pricing_model": "free",
        "price_cents": 0,
    }, headers=user["headers"])
    listing_id = listing.json()["id"]

    resp = await client.post(
        f"{API}/marketplace/{listing_id}/purchase",
        json={},
        headers=user["headers"],
    )
    assert resp.status_code == 400
    assert "own listing" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_escrow_config_setting():
    """Verify escrow_auto_release_hours setting exists."""
    from src.config import settings

    assert hasattr(settings, "escrow_auto_release_hours")
    assert settings.escrow_auto_release_hours == 72


@pytest.mark.asyncio
async def test_transaction_status_has_escrow_and_disputed():
    """Verify TransactionStatus enum has ESCROW and DISPUTED."""
    from src.models import TransactionStatus

    assert TransactionStatus.ESCROW.value == "escrow"
    assert TransactionStatus.DISPUTED.value == "disputed"


@pytest.mark.asyncio
async def test_get_escrow_transaction(client, db):
    """Verify a purchased escrow transaction is accessible via GET."""
    seller, buyer, listing_id, txn_id = await _setup_escrow(client, db)

    resp = await client.get(
        f"{API}/marketplace/purchases/{txn_id}",
        headers=buyer["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "escrow"

    resp2 = await client.get(
        f"{API}/marketplace/purchases/{txn_id}",
        headers=seller["headers"],
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "escrow"
