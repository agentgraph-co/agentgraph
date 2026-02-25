"""Tests for dispute resolution system.

Tests cover: opening disputes, listing, getting details, adding messages,
resolving (release_funds, cancel_auth, partial_refund), escalating,
admin views, admin adjudication, and authorization checks.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from src.database import get_db
from src.main import app

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


async def _register(client: AsyncClient) -> dict:
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

    return {
        "token": token,
        "headers": headers,
        "entity_id": me.json()["id"],
    }


def _mock_stripe():
    """Return a mock that patches stripe calls for paid purchase flow."""
    mock = MagicMock()
    mock.PaymentIntent.create.return_value = MagicMock(
        id="pi_dispute_test_123",
        client_secret="pi_dispute_test_123_secret",
        status="requires_capture",
    )
    mock.PaymentIntent.capture.return_value = MagicMock(
        id="pi_dispute_test_123",
        status="succeeded",
    )
    mock.PaymentIntent.cancel.return_value = MagicMock(
        id="pi_dispute_test_123",
        status="canceled",
    )
    mock.Account.create.return_value = MagicMock(id="acct_dispute_seller")
    mock.Account.retrieve.return_value = MagicMock(
        charges_enabled=True,
        payouts_enabled=True,
        details_submitted=True,
    )
    mock.AccountLink.create.return_value = MagicMock(url="https://stripe.com/onboard")
    return mock


async def _setup_escrow_txn(client: AsyncClient):
    """Create seller+buyer, onboard, create paid listing, purchase (escrow).

    Returns (seller, buyer, listing_id, txn_id).
    """
    seller = await _register(client)
    buyer = await _register(client)

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
            "title": "Dispute Svc",
            "description": "Service for dispute testing",
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


async def _make_admin(db, entity_id: str):
    """Promote an entity to admin."""
    await db.execute(
        text("UPDATE entities SET is_admin = true WHERE id = :id"),
        {"id": entity_id},
    )
    await db.flush()


@pytest.mark.asyncio
async def test_open_dispute_on_escrow(client):
    """Buyer can open a dispute on an ESCROW transaction."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    resp = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "The service was not delivered as described in the listing.",
    }, headers=buyer["headers"])
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "open"
    assert data["transaction_id"] == txn_id
    assert "deadline" in data


@pytest.mark.asyncio
async def test_cannot_dispute_non_escrow(client):
    """Cannot open a dispute on a free (COMPLETED) transaction."""
    seller = await _register(client)
    buyer = await _register(client)

    listing = await client.post(f"{API}/marketplace", json={
        "title": "Free Dispute Test",
        "description": "A free service",
        "category": "service",
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

    resp = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "This should fail because the transaction is completed.",
    }, headers=buyer["headers"])
    assert resp.status_code == 400
    assert "status" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_seller_cannot_open_dispute(client):
    """Seller should not be able to open a dispute."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    resp = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Seller trying to dispute their own transaction sale.",
    }, headers=seller["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cannot_duplicate_dispute(client):
    """Cannot open two disputes for the same transaction."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    resp1 = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "First dispute - should succeed without issue.",
    }, headers=buyer["headers"])
    assert resp1.status_code == 201

    resp2 = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Second dispute - should be blocked as duplicate.",
    }, headers=buyer["headers"])
    assert resp2.status_code == 400
    # The first dispute moves the transaction to DISPUTED status,
    # so the second attempt is rejected for wrong status (not ESCROW).
    detail = resp2.json()["detail"].lower()
    assert "status" in detail or "already exists" in detail


@pytest.mark.asyncio
async def test_list_disputes(client):
    """Both buyer and seller should see their disputes."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Listing dispute for testing list endpoint display.",
    }, headers=buyer["headers"])

    resp_buyer = await client.get(f"{API}/disputes", headers=buyer["headers"])
    assert resp_buyer.status_code == 200
    assert resp_buyer.json()["total"] >= 1

    resp_seller = await client.get(f"{API}/disputes", headers=seller["headers"])
    assert resp_seller.status_code == 200
    assert resp_seller.json()["total"] >= 1


@pytest.mark.asyncio
async def test_get_dispute_details(client):
    """Buyer, seller, and admin can view dispute details."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing get dispute details for authorization check.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    resp = await client.get(f"{API}/disputes/{dispute_id}", headers=buyer["headers"])
    assert resp.status_code == 200
    assert resp.json()["id"] == dispute_id

    resp2 = await client.get(f"{API}/disputes/{dispute_id}", headers=seller["headers"])
    assert resp2.status_code == 200

    other = await _register(client)
    resp3 = await client.get(f"{API}/disputes/{dispute_id}", headers=other["headers"])
    assert resp3.status_code == 403


@pytest.mark.asyncio
async def test_get_nonexistent_dispute(client):
    """Getting a nonexistent dispute should 404."""
    user = await _register(client)
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"{API}/disputes/{fake_id}", headers=user["headers"])
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_dispute_message(client):
    """Adding a message to a dispute should succeed and create a DM."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Need to message about this transaction delivery.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    resp = await client.post(f"{API}/disputes/{dispute_id}/message", json={
        "message": "I have not received the service yet.",
    }, headers=buyer["headers"])
    assert resp.status_code == 200
    assert "message_id" in resp.json()
    assert "Dispute" in resp.json()["content"]


@pytest.mark.asyncio
async def test_message_moves_to_negotiating(client):
    """Adding a message to an OPEN dispute should move it to NEGOTIATING."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing status transition to negotiating state.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]
    assert create.json()["status"] == "open"

    await client.post(f"{API}/disputes/{dispute_id}/message", json={
        "message": "Let us try to work this out together.",
    }, headers=buyer["headers"])

    resp = await client.get(f"{API}/disputes/{dispute_id}", headers=buyer["headers"])
    assert resp.json()["status"] == "negotiating"


@pytest.mark.asyncio
async def test_cannot_message_resolved_dispute(client):
    """Cannot add messages to a resolved dispute."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing message block after resolution completes.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    with patch("src.payments.stripe_service.cancel_payment_intent") as mock_cancel:
        mock_cancel.return_value = {"payment_intent_id": "pi_test", "status": "canceled"}

        # Seller concedes by canceling (refunding buyer)
        await client.post(f"{API}/disputes/{dispute_id}/resolve", json={
            "resolution": "cancel_auth",
        }, headers=seller["headers"])

    resp = await client.post(f"{API}/disputes/{dispute_id}/message", json={
        "message": "This should be blocked after resolution.",
    }, headers=buyer["headers"])
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resolve_dispute_release_funds(client):
    """Resolving a dispute with release_funds should capture and complete."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing release funds resolution pathway for disputes.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    with patch("src.payments.stripe_service.capture_payment_intent") as mock_capture:
        mock_capture.return_value = {"payment_intent_id": "pi_test", "status": "succeeded"}

        resp = await client.post(f"{API}/disputes/{dispute_id}/resolve", json={
            "resolution": "release_funds",
        }, headers=buyer["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"
        assert resp.json()["resolution"] == "release_funds"


@pytest.mark.asyncio
async def test_resolve_dispute_cancel_auth(client):
    """Resolving with cancel_auth should cancel the payment (seller concedes)."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing cancel authorization resolution pathway.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    with patch("src.payments.stripe_service.cancel_payment_intent") as mock_cancel:
        mock_cancel.return_value = {"payment_intent_id": "pi_test", "status": "canceled"}

        # Seller concedes by canceling (refunding buyer)
        resp = await client.post(f"{API}/disputes/{dispute_id}/resolve", json={
            "resolution": "cancel_auth",
        }, headers=seller["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"
        assert resp.json()["resolution"] == "cancel_auth"


@pytest.mark.asyncio
async def test_resolve_partial_refund_requires_amount(client):
    """Partial refund without amount should fail."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing partial refund validation requirement for amount.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    resp = await client.post(f"{API}/disputes/{dispute_id}/resolve", json={
        "resolution": "partial_refund",
    }, headers=buyer["headers"])
    assert resp.status_code == 400
    assert "amount" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_resolve_partial_refund_with_amount(client):
    """Partial refund with valid amount should succeed."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing partial refund with valid amount parameter.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    with patch("src.payments.stripe_service.capture_payment_intent") as mock_capture:
        mock_capture.return_value = {"payment_intent_id": "pi_test", "status": "succeeded"}

        resp = await client.post(f"{API}/disputes/{dispute_id}/resolve", json={
            "resolution": "partial_refund",
            "amount_cents": 2500,
        }, headers=buyer["headers"])
        assert resp.status_code == 200
        assert resp.json()["resolution"] == "partial_refund"
        assert resp.json()["resolution_amount_cents"] == 2500


@pytest.mark.asyncio
async def test_cannot_resolve_already_resolved(client):
    """Cannot resolve an already resolved dispute."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing double resolution prevention on disputes.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    with patch("src.payments.stripe_service.cancel_payment_intent") as mock_cancel:
        mock_cancel.return_value = {"payment_intent_id": "pi_test", "status": "canceled"}

        # Seller concedes by canceling
        resp1 = await client.post(f"{API}/disputes/{dispute_id}/resolve", json={
            "resolution": "cancel_auth",
        }, headers=seller["headers"])
        assert resp1.status_code == 200

        resp2 = await client.post(f"{API}/disputes/{dispute_id}/resolve", json={
            "resolution": "release_funds",
        }, headers=buyer["headers"])
        assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_escalate_dispute(client):
    """Buyer or seller can escalate a dispute to admin."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Need admin help with this transaction dispute issue.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    resp = await client.post(
        f"{API}/disputes/{dispute_id}/escalate",
        headers=buyer["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "escalated"


@pytest.mark.asyncio
async def test_cannot_escalate_resolved(client):
    """Cannot escalate a resolved dispute."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing escalation block after resolution is complete.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    with patch("src.payments.stripe_service.cancel_payment_intent") as mock_cancel:
        mock_cancel.return_value = {"payment_intent_id": "pi_test", "status": "canceled"}
        # Seller concedes by canceling
        await client.post(f"{API}/disputes/{dispute_id}/resolve", json={
            "resolution": "cancel_auth",
        }, headers=seller["headers"])

    resp = await client.post(
        f"{API}/disputes/{dispute_id}/escalate",
        headers=buyer["headers"],
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cannot_double_escalate(client):
    """Cannot escalate an already escalated dispute."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing double escalation prevention on a dispute.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    resp1 = await client.post(
        f"{API}/disputes/{dispute_id}/escalate",
        headers=buyer["headers"],
    )
    assert resp1.status_code == 200

    resp2 = await client.post(
        f"{API}/disputes/{dispute_id}/escalate",
        headers=buyer["headers"],
    )
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_admin_list_disputes(client, db):
    """Admin can list all disputes."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing admin list endpoint for all disputes view.",
    }, headers=buyer["headers"])

    admin = await _register(client)
    await _make_admin(db, admin["entity_id"])

    resp = await client.get(
        f"{API}/disputes/admin/all",
        headers=admin["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_admin_list_requires_admin(client):
    """Non-admin cannot access admin dispute list."""
    user = await _register(client)
    resp = await client.get(f"{API}/disputes/admin/all", headers=user["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_adjudicate_release_funds(client, db):
    """Admin can adjudicate a dispute by releasing funds."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing admin adjudication with release funds action.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    admin = await _register(client)
    await _make_admin(db, admin["entity_id"])

    with patch("src.payments.stripe_service.capture_payment_intent") as mock_capture:
        mock_capture.return_value = {"payment_intent_id": "pi_test", "status": "succeeded"}

        resp = await client.post(
            f"{API}/disputes/admin/{dispute_id}/adjudicate",
            json={
                "resolution": "release_funds",
                "admin_note": "Seller delivered the service correctly.",
            },
            headers=admin["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"
        assert resp.json()["resolution"] == "release_funds"
        assert resp.json()["admin_note"] == "Seller delivered the service correctly."


@pytest.mark.asyncio
async def test_admin_adjudicate_cancel_auth(client, db):
    """Admin can adjudicate by cancelling auth."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing admin cancel auth adjudication pathway.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    admin = await _register(client)
    await _make_admin(db, admin["entity_id"])

    with patch("src.payments.stripe_service.cancel_payment_intent") as mock_cancel:
        mock_cancel.return_value = {"payment_intent_id": "pi_test", "status": "canceled"}

        resp = await client.post(
            f"{API}/disputes/admin/{dispute_id}/adjudicate",
            json={
                "resolution": "cancel_auth",
                "admin_note": "Seller did not deliver.",
            },
            headers=admin["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["resolution"] == "cancel_auth"


@pytest.mark.asyncio
async def test_admin_adjudicate_partial_refund(client, db):
    """Admin can adjudicate with partial refund."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing admin partial refund adjudication pathway.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    admin = await _register(client)
    await _make_admin(db, admin["entity_id"])

    with patch("src.payments.stripe_service.capture_payment_intent") as mock_capture:
        mock_capture.return_value = {"payment_intent_id": "pi_test", "status": "succeeded"}

        resp = await client.post(
            f"{API}/disputes/admin/{dispute_id}/adjudicate",
            json={
                "resolution": "partial_refund",
                "amount_cents": 2000,
                "admin_note": "Partial delivery acknowledged.",
            },
            headers=admin["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["resolution"] == "partial_refund"
        assert resp.json()["resolution_amount_cents"] == 2000


@pytest.mark.asyncio
async def test_admin_adjudicate_requires_admin(client):
    """Non-admin cannot adjudicate disputes."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing admin requirement for adjudication endpoint.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    resp = await client.post(
        f"{API}/disputes/admin/{dispute_id}/adjudicate",
        json={"resolution": "release_funds"},
        headers=buyer["headers"],
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_dispute_deadline_set(client):
    """Dispute deadline should be set to now + escrow_auto_release_hours."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    resp = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing that deadline is properly set on dispute creation.",
    }, headers=buyer["headers"])
    assert resp.status_code == 201
    data = resp.json()

    from datetime import datetime

    deadline = datetime.fromisoformat(data["deadline"])
    created = datetime.fromisoformat(data["created_at"])
    diff_hours = (deadline - created).total_seconds() / 3600
    assert 71 <= diff_hours <= 73


@pytest.mark.asyncio
async def test_dispute_reason_too_short(client):
    """Dispute reason must be at least 10 characters."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    resp = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "short",
    }, headers=buyer["headers"])
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_dispute_on_nonexistent_transaction(client):
    """Disputing a nonexistent transaction should 404."""
    user = await _register(client)
    fake_id = str(uuid.uuid4())
    resp = await client.post(f"{API}/disputes", json={
        "transaction_id": fake_id,
        "reason": "Transaction does not exist at all in the system.",
    }, headers=user["headers"])
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_disputes_with_status_filter(client):
    """Listing disputes with status filter should work."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing list disputes with status filter parameter.",
    }, headers=buyer["headers"])

    resp = await client.get(
        f"{API}/disputes?status=open",
        headers=buyer["headers"],
    )
    assert resp.status_code == 200
    for d in resp.json()["disputes"]:
        assert d["status"] == "open"


@pytest.mark.asyncio
async def test_seller_can_resolve(client):
    """Seller can resolve a dispute by conceding (cancel_auth)."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing that seller can also resolve a dispute case.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    with patch("src.payments.stripe_service.cancel_payment_intent") as mock_cancel:
        mock_cancel.return_value = {"payment_intent_id": "pi_test", "status": "canceled"}

        # Seller concedes by canceling (refunding buyer)
        resp = await client.post(f"{API}/disputes/{dispute_id}/resolve", json={
            "resolution": "cancel_auth",
        }, headers=seller["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_uninvolved_cannot_resolve(client):
    """Uninvolved user cannot resolve a dispute."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing unauthorized resolution attempt by outsider.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    other = await _register(client)
    resp = await client.post(f"{API}/disputes/{dispute_id}/resolve", json={
        "resolution": "release_funds",
    }, headers=other["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_buyer_cannot_self_refund(client):
    """Buyer cannot unilaterally cancel_auth (self-serving)."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing self-serving resolution block for buyer.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    resp = await client.post(f"{API}/disputes/{dispute_id}/resolve", json={
        "resolution": "cancel_auth",
    }, headers=buyer["headers"])
    assert resp.status_code == 403
    assert "Buyer cannot" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_seller_cannot_self_release(client):
    """Seller cannot unilaterally release_funds (self-serving)."""
    seller, buyer, listing_id, txn_id = await _setup_escrow_txn(client)

    create = await client.post(f"{API}/disputes", json={
        "transaction_id": txn_id,
        "reason": "Testing self-serving resolution block for seller.",
    }, headers=buyer["headers"])
    dispute_id = create.json()["id"]

    resp = await client.post(f"{API}/disputes/{dispute_id}/resolve", json={
        "resolution": "release_funds",
    }, headers=seller["headers"])
    assert resp.status_code == 403
    assert "Seller cannot" in resp.json()["detail"]
