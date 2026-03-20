"""Tests for anonymized network analytics (insights) endpoints."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.main import app
from src.models import TrustScore

PREFIX = "/api/v1"


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _create_user(
    client: AsyncClient, suffix: str = "", db: AsyncSession | None = None,
) -> tuple:
    """Helper to register + login a user and return (token, headers, login_data)."""
    email = f"insights_{uuid.uuid4().hex[:8]}@test.com"
    password = "StrongPass1!"
    await client.post(f"{PREFIX}/auth/register", json={
        "display_name": f"Insights User {suffix}",
        "email": email,
        "password": password,
    })
    login_resp = await client.post(f"{PREFIX}/auth/login", json={
        "email": email,
        "password": password,
    })
    data = login_resp.json()
    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    if db is not None:
        me = await client.get(f"{PREFIX}/auth/me", headers=headers)
        eid = uuid.UUID(me.json()["id"])
        from sqlalchemy import update
        await db.execute(
            update(TrustScore)
            .where(TrustScore.entity_id == eid)
            .values(score=0.5, components={"verification": 0.3, "age": 0.1, "activity": 0.1})
        )
        await db.flush()
    return token, headers, data


async def _create_listing(client: AsyncClient, headers: dict, category: str = "service") -> dict:
    """Create a marketplace listing."""
    resp = await client.post(f"{PREFIX}/marketplace", json={
        "title": f"Test Listing {uuid.uuid4().hex[:6]}",
        "description": "A test listing for insights",
        "category": category,
        "pricing_model": "free",
        "price_cents": 0,
        "tags": ["test"],
    }, headers=headers)
    assert resp.status_code == 201, f"Listing creation failed: {resp.status_code} {resp.text}"
    return resp.json()


# --- Network Growth ---


@pytest.mark.asyncio
async def test_network_growth_default(client, db):
    _, headers, _ = await _create_user(client, "growth1")
    resp = await client.get(f"{PREFIX}/insights/network/growth", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "period_days" in data
    assert data["period_days"] == 30
    assert "data" in data
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_network_growth_custom_days(client, db):
    _, headers, _ = await _create_user(client, "growth2")
    resp = await client.get(
        f"{PREFIX}/insights/network/growth?days=7", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["period_days"] == 7


@pytest.mark.asyncio
async def test_network_growth_large_days(client, db):
    _, headers, _ = await _create_user(client, "growth3")
    resp = await client.get(
        f"{PREFIX}/insights/network/growth?days=365", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["period_days"] == 365


@pytest.mark.asyncio
async def test_network_growth_invalid_days_zero(client, db):
    _, headers, _ = await _create_user(client, "growth4")
    resp = await client.get(
        f"{PREFIX}/insights/network/growth?days=0", headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_network_growth_invalid_days_too_large(client, db):
    _, headers, _ = await _create_user(client, "growth5")
    resp = await client.get(
        f"{PREFIX}/insights/network/growth?days=999", headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_network_growth_has_data(client, db):
    """After registering users, growth data should contain entries."""
    _, headers, _ = await _create_user(client, "growthA")
    await _create_user(client, "growthB")
    resp = await client.get(f"{PREFIX}/insights/network/growth", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) >= 1
    entry = data["data"][0]
    assert "date" in entry
    assert "entity_type" in entry
    assert "count" in entry
    assert entry["count"] >= 1


@pytest.mark.asyncio
async def test_network_growth_unauthenticated(client, db):
    resp = await client.get(f"{PREFIX}/insights/network/growth")
    assert resp.status_code == 401


# --- Trust Distribution ---


@pytest.mark.asyncio
async def test_trust_distribution(client, db):
    _, headers, _ = await _create_user(client, "trust1")
    resp = await client.get(
        f"{PREFIX}/insights/network/trust-distribution", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_scored_entities" in data
    assert "distribution" in data
    assert isinstance(data["distribution"], list)


@pytest.mark.asyncio
async def test_trust_distribution_structure(client, db):
    """Trust distribution buckets have the right shape."""
    _, headers, _ = await _create_user(client, "trust2")
    resp = await client.get(
        f"{PREFIX}/insights/network/trust-distribution", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    for bucket in data["distribution"]:
        assert "range_start" in bucket
        assert "range_end" in bucket
        assert "count" in bucket
        assert bucket["range_end"] > bucket["range_start"]


@pytest.mark.asyncio
async def test_trust_distribution_unauthenticated(client, db):
    resp = await client.get(f"{PREFIX}/insights/network/trust-distribution")
    assert resp.status_code == 401


# --- Network Health ---


@pytest.mark.asyncio
async def test_network_health(client, db):
    _, headers, _ = await _create_user(client, "health1")
    resp = await client.get(
        f"{PREFIX}/insights/network/health", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_entities" in data
    assert "total_humans" in data
    assert "total_agents" in data
    assert "average_trust_score" in data
    assert "total_posts" in data
    assert "total_relationships" in data
    assert "total_active_listings" in data


@pytest.mark.asyncio
async def test_network_health_has_entities(client, db):
    """After registering a user, entity counts should be positive."""
    _, headers, _ = await _create_user(client, "health2")
    resp = await client.get(
        f"{PREFIX}/insights/network/health", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_entities"] >= 1
    assert data["total_humans"] >= 1


@pytest.mark.asyncio
async def test_network_health_unauthenticated(client, db):
    resp = await client.get(f"{PREFIX}/insights/network/health")
    assert resp.status_code == 401


# --- Capability Demand ---


@pytest.mark.asyncio
async def test_capability_demand_default(client, db):
    _, headers, _ = await _create_user(client, "demand1")
    resp = await client.get(
        f"{PREFIX}/insights/capabilities/demand", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "capabilities" in data
    assert isinstance(data["capabilities"], list)


@pytest.mark.asyncio
async def test_capability_demand_with_limit(client, db):
    _, headers, _ = await _create_user(client, "demand2")
    resp = await client.get(
        f"{PREFIX}/insights/capabilities/demand?limit=5", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["capabilities"]) <= 5


@pytest.mark.asyncio
async def test_capability_demand_with_data(client, db):
    """Creating a listing should show up in capability demand."""
    _, headers, _ = await _create_user(client, "demand3", db)
    await _create_listing(client, headers, category="skill")
    resp = await client.get(
        f"{PREFIX}/insights/capabilities/demand", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    categories = [c["category"] for c in data["capabilities"]]
    assert "skill" in categories


@pytest.mark.asyncio
async def test_capability_demand_structure(client, db):
    _, headers, _ = await _create_user(client, "demand4", db)
    await _create_listing(client, headers)
    resp = await client.get(
        f"{PREFIX}/insights/capabilities/demand", headers=headers,
    )
    assert resp.status_code == 200
    for cap in resp.json()["capabilities"]:
        assert "category" in cap
        assert "listing_count" in cap
        assert "total_views" in cap


# --- Marketplace Volume ---


@pytest.mark.asyncio
async def test_marketplace_volume_default(client, db):
    _, headers, _ = await _create_user(client, "vol1")
    resp = await client.get(
        f"{PREFIX}/insights/marketplace/volume", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "period_days" in data
    assert data["period_days"] == 30
    assert "total_transactions" in data
    assert "total_volume_cents" in data
    assert "daily" in data


@pytest.mark.asyncio
async def test_marketplace_volume_custom_days(client, db):
    _, headers, _ = await _create_user(client, "vol2")
    resp = await client.get(
        f"{PREFIX}/insights/marketplace/volume?days=14", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["period_days"] == 14


@pytest.mark.asyncio
async def test_marketplace_volume_unauthenticated(client, db):
    resp = await client.get(f"{PREFIX}/insights/marketplace/volume")
    assert resp.status_code == 401


# --- Category Trends ---


@pytest.mark.asyncio
async def test_category_trends_default(client, db):
    _, headers, _ = await _create_user(client, "cat1")
    resp = await client.get(
        f"{PREFIX}/insights/marketplace/categories", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "period_days" in data
    assert data["period_days"] == 30
    assert "categories" in data
    assert isinstance(data["categories"], list)


@pytest.mark.asyncio
async def test_category_trends_with_data(client, db):
    """Creating a listing should appear in category trends."""
    _, headers, _ = await _create_user(client, "cat2", db)
    await _create_listing(client, headers, category="integration")
    resp = await client.get(
        f"{PREFIX}/insights/marketplace/categories?days=365", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    cats = [c["category"] for c in data["categories"]]
    assert "integration" in cats


@pytest.mark.asyncio
async def test_category_trends_structure(client, db):
    _, headers, _ = await _create_user(client, "cat3", db)
    await _create_listing(client, headers)
    resp = await client.get(
        f"{PREFIX}/insights/marketplace/categories", headers=headers,
    )
    assert resp.status_code == 200
    for cat in resp.json()["categories"]:
        assert "category" in cat
        assert "new_listings" in cat


# --- Framework Adoption ---


@pytest.mark.asyncio
async def test_framework_adoption(client, db):
    _, headers, _ = await _create_user(client, "fw1")
    resp = await client.get(
        f"{PREFIX}/insights/framework/adoption", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_framework_agents" in data
    assert "frameworks" in data
    assert isinstance(data["frameworks"], list)


@pytest.mark.asyncio
async def test_framework_adoption_structure(client, db):
    _, headers, _ = await _create_user(client, "fw2")
    resp = await client.get(
        f"{PREFIX}/insights/framework/adoption", headers=headers,
    )
    assert resp.status_code == 200
    for fw in resp.json()["frameworks"]:
        assert "framework" in fw
        assert "agent_count" in fw


@pytest.mark.asyncio
async def test_framework_adoption_unauthenticated(client, db):
    resp = await client.get(f"{PREFIX}/insights/framework/adoption")
    assert resp.status_code == 401
