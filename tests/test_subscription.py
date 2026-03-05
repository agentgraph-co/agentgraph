"""Tests for the subscription & usage-based pricing endpoints."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app

PREFIX = "/api/v1/subscriptions"


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _create_user(client: AsyncClient, suffix: str | None = None):
    """Register a user via API and return (token, entity_id)."""
    sfx = suffix or uuid.uuid4().hex[:8]
    email = f"sub_{sfx}@example.com"
    body = {
        "email": email,
        "password": "Str0ngP@ss1",
        "display_name": f"SubUser {sfx}",
    }
    await client.post("/api/v1/auth/register", json=body)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Str0ngP@ss1"},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


# ---------------------------------------------------------------------------
# GET /subscriptions/pricing — Public pricing tiers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pricing_tiers(client: AsyncClient):
    resp = await client.get(f"{PREFIX}/pricing")
    assert resp.status_code == 200
    data = resp.json()
    assert "tiers" in data
    assert "metered" in data
    assert len(data["tiers"]) == 3
    tier_keys = [t["key"] for t in data["tiers"]]
    assert "free" in tier_keys
    assert "pro" in tier_keys
    assert "enterprise" in tier_keys


@pytest.mark.asyncio
async def test_pricing_tiers_have_limits(client: AsyncClient):
    resp = await client.get(f"{PREFIX}/pricing")
    data = resp.json()
    for tier in data["tiers"]:
        assert "limits" in tier
        assert "api_calls_per_day" in tier["limits"]
        assert "agents_max" in tier["limits"]
        assert "features" in tier
        assert len(tier["features"]) > 0


@pytest.mark.asyncio
async def test_pricing_metered_options(client: AsyncClient):
    resp = await client.get(f"{PREFIX}/pricing")
    data = resp.json()
    metered = data["metered"]
    assert "api_overage_per_1k" in metered
    assert "agent_extra_per_month" in metered
    assert metered["api_overage_per_1k"]["unit_cents"] > 0


# ---------------------------------------------------------------------------
# GET /subscriptions/me — Subscription status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_subscription_requires_auth(client: AsyncClient):
    resp = await client.get(f"{PREFIX}/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_subscription_default_free(client: AsyncClient):
    token, _ = await _create_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/me", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "free"
    assert data["is_organization"] is False
    assert "limits" in data
    assert "features" in data


# ---------------------------------------------------------------------------
# GET /subscriptions/usage — Usage summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_usage_requires_auth(client: AsyncClient):
    resp = await client.get(f"{PREFIX}/usage")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_usage_summary(client: AsyncClient):
    token, _ = await _create_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/usage", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "free"
    assert data["agents_active"] == 0
    assert data["listings_active"] == 0
    assert data["api_calls_limit"] == 100


# ---------------------------------------------------------------------------
# POST /subscriptions/upgrade — Tier changes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upgrade_requires_auth(client: AsyncClient):
    resp = await client.post(f"{PREFIX}/upgrade", json={"target_tier": "pro"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_upgrade_to_pro(client: AsyncClient):
    token, _ = await _create_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        f"{PREFIX}/upgrade",
        json={"target_tier": "pro", "billing_period": "monthly"},
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["previous_tier"] == "free"
    assert data["new_tier"] == "pro"
    assert data["price_cents"] == 2900
    assert data["billing_period"] == "monthly"


@pytest.mark.asyncio
async def test_upgrade_to_enterprise_yearly(client: AsyncClient):
    token, _ = await _create_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        f"{PREFIX}/upgrade",
        json={"target_tier": "enterprise", "billing_period": "yearly"},
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["new_tier"] == "enterprise"
    assert data["price_cents"] == 199000


@pytest.mark.asyncio
async def test_upgrade_invalid_tier(client: AsyncClient):
    token, _ = await _create_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        f"{PREFIX}/upgrade",
        json={"target_tier": "nonexistent"},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upgrade_invalid_billing_period(client: AsyncClient):
    token, _ = await _create_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        f"{PREFIX}/upgrade",
        json={"target_tier": "pro", "billing_period": "weekly"},
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upgrade_persists(client: AsyncClient):
    """After upgrading, /me should reflect the new tier."""
    token, _ = await _create_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Upgrade
    resp = await client.post(
        f"{PREFIX}/upgrade",
        json={"target_tier": "pro"},
        headers=headers,
    )
    assert resp.status_code == 200

    # Check status
    resp = await client.get(f"{PREFIX}/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["tier"] == "pro"


# ---------------------------------------------------------------------------
# POST /subscriptions/cancel — Cancel subscription
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_requires_auth(client: AsyncClient):
    resp = await client.post(f"{PREFIX}/cancel")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_cancel_subscription(client: AsyncClient):
    token, _ = await _create_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Upgrade first
    await client.post(
        f"{PREFIX}/upgrade",
        json={"target_tier": "pro"},
        headers=headers,
    )

    # Cancel
    resp = await client.post(f"{PREFIX}/cancel", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["previous_tier"] == "pro"
    assert data["new_tier"] == "free"

    # Verify status
    resp = await client.get(f"{PREFIX}/me", headers=headers)
    assert resp.json()["tier"] == "free"


# ---------------------------------------------------------------------------
# GET /subscriptions/check-limit/{resource} — Resource limit checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_limit_requires_auth(client: AsyncClient):
    resp = await client.get(f"{PREFIX}/check-limit/agents")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_check_limit_agents(client: AsyncClient):
    token, _ = await _create_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/check-limit/agents", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["resource"] == "agents"
    assert data["current"] == 0
    assert data["limit"] == 2  # free tier
    assert data["at_limit"] is False
    assert data["overage"] == 0


@pytest.mark.asyncio
async def test_check_limit_listings(client: AsyncClient):
    token, _ = await _create_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/check-limit/listings", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["resource"] == "listings"
    assert data["limit"] == 1  # free tier


@pytest.mark.asyncio
async def test_check_limit_invalid_resource(client: AsyncClient):
    token, _ = await _create_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/check-limit/bananas", headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_check_limit_after_upgrade(client: AsyncClient):
    """After upgrading to pro, limits should increase."""
    token, _ = await _create_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Upgrade to pro
    await client.post(
        f"{PREFIX}/upgrade",
        json={"target_tier": "pro"},
        headers=headers,
    )

    # Check agent limit — should be 20 now
    resp = await client.get(f"{PREFIX}/check-limit/agents", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["limit"] == 20


# ---------------------------------------------------------------------------
# GET /subscriptions/org-usage — Organization usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_usage_requires_auth(client: AsyncClient):
    resp = await client.get(f"{PREFIX}/org-usage")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_org_usage_requires_org_membership(client: AsyncClient):
    token, _ = await _create_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/org-usage", headers=headers)
    assert resp.status_code == 403
