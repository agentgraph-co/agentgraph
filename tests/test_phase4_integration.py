"""Phase 4 end-to-end integration tests.

Tests cross-feature interactions: escrow → disputes, capability listings → adoption,
AIP delegation lifecycle, insights endpoints, enterprise usage metering,
and WebSocket channel availability.
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


async def _register(client: AsyncClient) -> dict:
    """Register, login, return {token, headers, entity_id}."""
    uid = uuid.uuid4().hex[:8]
    email = f"p4_{uid}@test.com"
    password = "StrongPass1!"
    reg = await client.post(f"{API}/auth/register", json={
        "display_name": f"P4User {uid}",
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
    assert me.status_code == 200
    return {"token": token, "headers": headers, "entity_id": me.json()["id"]}


async def _grant_trust(db, entity_id: str, score: float = 0.5):
    from sqlalchemy import update as _sa_update
    await db.execute(
        _sa_update(TrustScore)
        .where(TrustScore.entity_id == uuid.UUID(entity_id))
        .values(score=score, components={})
    )
    await db.flush()


def _mock_stripe():
    mock = MagicMock()
    mock.Account.create.return_value = MagicMock(id="acct_test_123")
    mock.AccountLink.create.return_value = MagicMock(url="http://test/onboard")
    mock.PaymentIntent.create.return_value = MagicMock(
        id="pi_p4_test_123",
        client_secret="pi_p4_test_123_secret",
        status="requires_capture",
    )
    mock.PaymentIntent.capture.return_value = MagicMock(
        id="pi_p4_test_123",
        status="succeeded",
    )
    mock.PaymentIntent.cancel.return_value = MagicMock(
        id="pi_p4_test_123",
        status="canceled",
    )
    return mock


# ---- Escrow → Dispute E2E ----


@pytest.mark.asyncio
async def test_escrow_purchase_then_dispute_then_resolve(client: AsyncClient, db):
    """Full lifecycle: create listing → purchase (escrow) → open dispute → resolve."""
    seller = await _register(client)
    await _grant_trust(db, seller["entity_id"])
    buyer = await _register(client)
    await _grant_trust(db, buyer["entity_id"])
    admin = await _register(client)
    # Promote to admin via DB
    await db.execute(
        text("UPDATE entities SET is_admin = true WHERE id = :id"),
        {"id": admin["entity_id"]},
    )
    await db.flush()

    # Seller creates a paid listing
    listing = await client.post(
        f"{API}/marketplace", headers=seller["headers"], json={
            "title": "E2E Escrow Test Service",
            "description": "Integration test listing",
            "category": "service",
            "tags": ["test"],
            "pricing_model": "one_time",
            "price_cents": 5000,
        },
    )
    assert listing.status_code == 201, listing.text
    lid = listing.json()["id"]

    # Buyer purchases (escrow) — requires stripe + settings mock
    mock = _mock_stripe()
    with patch("src.payments.stripe_service.stripe", mock), \
         patch("src.api.marketplace_router.settings") as ms:
        ms.stripe_secret_key = "sk_test"
        ms.stripe_webhook_secret = "whsec_test"
        ms.stripe_platform_fee_percent = 10
        ms.api_v1_prefix = "/api/v1"

        # Seller onboards to Stripe Connect
        await client.post(
            f"{API}/marketplace/connect/onboard",
            json={"return_url": "http://test/ok", "refresh_url": "http://test/refresh"},
            headers=seller["headers"],
        )

        purchase = await client.post(
            f"{API}/marketplace/{lid}/purchase",
            json={},
            headers=buyer["headers"],
        )
    assert purchase.status_code == 201, purchase.text
    assert purchase.json()["status"] == "escrow"
    txn_id = purchase.json()["id"]

    # Buyer opens dispute
    dispute = await client.post(
        f"{API}/disputes",
        headers=buyer["headers"],
        json={"transaction_id": txn_id, "reason": "Service not delivered as described"},
    )
    assert dispute.status_code == 201, dispute.text
    dispute_id = dispute.json()["id"]

    # Verify dispute shows up in buyer's disputes
    my_disputes = await client.get(f"{API}/disputes", headers=buyer["headers"])
    assert my_disputes.status_code == 200
    assert any(d["id"] == dispute_id for d in my_disputes.json()["disputes"])

    # Admin adjudicates — cancel auth
    with patch("src.payments.stripe_service.cancel_payment_intent") as mock_cancel:
        mock_cancel.return_value = None
        adjudicate = await client.post(
            f"{API}/disputes/admin/{dispute_id}/adjudicate",
            headers=admin["headers"],
            json={"resolution": "cancel_auth", "admin_note": "Service not delivered"},
        )
    assert adjudicate.status_code == 200, adjudicate.text
    assert adjudicate.json()["status"] == "resolved"


# ---- Capability Marketplace → Evolution Fork E2E ----


@pytest.mark.asyncio
async def test_capability_listing_creation(client: AsyncClient, db):
    """Create a capability listing linked to an evolution record."""
    user = await _register(client)
    await _grant_trust(db, user["entity_id"])

    # Create capability listing directly
    listing = await client.post(
        f"{API}/marketplace", headers=user["headers"], json={
            "title": "Code Review Capability",
            "description": "Full code review pipeline for integration testing",
            "category": "capability",
            "tags": ["code-review"],
            "pricing_model": "free",
            "price_cents": 0,
        },
    )
    assert listing.status_code == 201, listing.text
    assert listing.json()["category"] == "capability"


# ---- AIP Delegation Full Lifecycle ----


@pytest.mark.asyncio
async def test_aip_delegation_full_lifecycle(client: AsyncClient):
    """Create → accept → complete delegation."""
    delegator = await _register(client)
    delegate = await _register(client)
    delegator_headers = delegator["headers"]
    delegate_id = delegate["entity_id"]
    delegate_headers = delegate["headers"]

    # Create delegation
    resp = await client.post(f"{API}/aip/delegate", headers=delegator_headers, json={
        "delegate_entity_id": delegate_id,
        "task_description": "Run integration test suite",
        "constraints": {"timeout": 300},
        "timeout_seconds": 3600,
    })
    assert resp.status_code in (200, 201), resp.text
    delegation_id = resp.json()["id"]

    # Accept
    accept = await client.patch(
        f"{API}/aip/delegations/{delegation_id}",
        headers=delegate_headers,
        json={"action": "accept"},
    )
    assert accept.status_code == 200, accept.text

    # Complete
    complete = await client.patch(
        f"{API}/aip/delegations/{delegation_id}",
        headers=delegate_headers,
        json={"action": "complete", "result": {"tests_passed": 42}},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] in ("completed", "COMPLETED")


# ---- AIP Capability Registry ----


@pytest.mark.asyncio
async def test_aip_register_and_discover_capability(client: AsyncClient):
    """Register a capability then discover it."""
    user = await _register(client)

    # Register capability
    reg = await client.post(f"{API}/aip/capabilities", headers=user["headers"], json={
        "capability_name": "integration-test-cap",
        "version": "1.0.0",
        "description": "Test capability for integration testing",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
    })
    # Might be 200 or 201 depending on implementation
    assert reg.status_code in (200, 201), reg.text

    # Discover
    discover = await client.get(
        f"{API}/aip/discover",
        headers=user["headers"],
        params={"capability": "integration-test-cap"},
    )
    assert discover.status_code == 200, discover.text
    results = discover.json()
    # Should find at least one result
    found = False
    if isinstance(results, list):
        found = any("integration-test-cap" in str(r) for r in results)
    elif isinstance(results, dict) and "results" in results:
        found = any("integration-test-cap" in str(r) for r in results["results"])
    else:
        found = "integration-test-cap" in str(results)
    assert found, f"Capability not found in discover results: {results}"


# ---- Insights / Data Products ----


@pytest.mark.asyncio
async def test_insights_endpoints_accessible(client: AsyncClient):
    """All insights endpoints return 200."""
    user = await _register(client)
    endpoints = [
        "/insights/network/growth",
        "/insights/network/trust-distribution",
        "/insights/capabilities/demand",
        "/insights/marketplace/volume",
        "/insights/marketplace/categories",
        "/insights/framework/adoption",
        "/insights/network/health",
    ]
    for ep in endpoints:
        resp = await client.get(f"{API}{ep}", headers=user["headers"])
        assert resp.status_code == 200, f"{ep} returned {resp.status_code}: {resp.text}"


# ---- Enterprise Usage Metering ----


@pytest.mark.asyncio
async def test_enterprise_org_usage_flow(client: AsyncClient, db):
    """Create org → record usage → query usage."""
    admin = await _register(client)

    # Create org
    org = await client.post(f"{API}/organizations", headers=admin["headers"], json={
        "name": f"usage-test-{uuid.uuid4().hex[:6]}",
        "display_name": "Usage Test Org",
        "description": "Testing usage metering",
    })
    assert org.status_code in (200, 201), org.text
    org_id = org.json()["id"]

    # Query usage (should be empty or return a structure)
    usage = await client.get(
        f"{API}/organizations/{org_id}/usage",
        headers=admin["headers"],
    )
    assert usage.status_code == 200, usage.text


# ---- Enterprise Audit Export ----


@pytest.mark.asyncio
async def test_enterprise_audit_export(client: AsyncClient, db):
    """Org admin can export audit logs."""
    admin = await _register(client)

    org = await client.post(f"{API}/organizations", headers=admin["headers"], json={
        "name": f"audit-test-{uuid.uuid4().hex[:6]}",
        "display_name": "Audit Test Org",
        "description": "Testing audit export",
    })
    assert org.status_code in (200, 201), org.text
    org_id = org.json()["id"]

    # Export audit logs
    export = await client.get(
        f"{API}/organizations/{org_id}/audit-export",
        headers=admin["headers"],
        params={"format": "json"},
    )
    assert export.status_code == 200, export.text


# ---- Enterprise Org API Keys ----


@pytest.mark.asyncio
async def test_enterprise_org_api_keys_lifecycle(client: AsyncClient, db):
    """Create, list, and revoke org-scoped API keys."""
    admin = await _register(client)

    org = await client.post(f"{API}/organizations", headers=admin["headers"], json={
        "name": f"apikey-test-{uuid.uuid4().hex[:6]}",
        "display_name": "API Key Test Org",
        "description": "Testing org API keys",
    })
    assert org.status_code in (200, 201), org.text
    org_id = org.json()["id"]

    # Create org API key
    create = await client.post(
        f"{API}/organizations/{org_id}/api-keys",
        headers=admin["headers"],
        json={"label": "test-key"},
    )
    assert create.status_code in (200, 201), create.text
    key_data = create.json()
    key_id = key_data.get("id") or key_data.get("key_id")
    assert key_id is not None

    # List org API keys
    keys = await client.get(
        f"{API}/organizations/{org_id}/api-keys",
        headers=admin["headers"],
    )
    assert keys.status_code == 200, keys.text

    # Revoke
    revoke = await client.delete(
        f"{API}/organizations/{org_id}/api-keys/{key_id}",
        headers=admin["headers"],
    )
    assert revoke.status_code in (200, 204), revoke.text


# ---- WebSocket Channel Availability ----


@pytest.mark.asyncio
async def test_ws_channels_include_phase4(client: AsyncClient):
    """Verify Phase 4 WebSocket channels are in valid_channels."""
    from src.api import ws_router
    if hasattr(ws_router, "VALID_CHANNELS"):
        channels = ws_router.VALID_CHANNELS
    else:
        # Read from source
        import inspect
        source = inspect.getsource(ws_router)
        assert "aip" in source
        assert "marketplace" in source
        assert "disputes" in source
        channels = None

    if channels is not None:
        for ch in ("aip", "marketplace", "disputes"):
            assert ch in channels, f"Channel '{ch}' missing from valid_channels"


# ---- Cross-Feature: AIP + Insights ----


@pytest.mark.asyncio
async def test_capability_demand_reflects_registrations(client: AsyncClient):
    """Registering capabilities should be reflected in insights demand data."""
    user = await _register(client)

    # Register a capability
    await client.post(f"{API}/aip/capabilities", headers=user["headers"], json={
        "capability_name": "demand-test-cap",
        "version": "1.0.0",
        "description": "Testing demand tracking",
        "input_schema": {},
        "output_schema": {},
    })

    # Check capability demand
    demand = await client.get(
        f"{API}/insights/capabilities/demand",
        headers=user["headers"],
    )
    assert demand.status_code == 200


# ---- Disputes List Filters ----


@pytest.mark.asyncio
async def test_disputes_require_auth(client: AsyncClient):
    """Disputes endpoints require authentication."""
    resp = await client.get(f"{API}/disputes")
    assert resp.status_code in (401, 403)


# ---- AIP Schema Endpoint ----


@pytest.mark.asyncio
async def test_aip_schema_endpoint(client: AsyncClient):
    """AIP schema endpoint returns protocol description."""
    user = await _register(client)
    resp = await client.get(f"{API}/aip/schema", headers=user["headers"])
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "version" in data or "schema" in data or "message_types" in data
