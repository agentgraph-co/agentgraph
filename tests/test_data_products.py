from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import TrustScore


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
DATA_URL = "/api/v1/data"

USER = {
    "email": "dataprod@test.com",
    "password": "Str0ngP@ss",
    "display_name": "DataProdUser",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL,
        json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Network Health ---


@pytest.mark.asyncio
async def test_network_health_requires_auth(client):
    resp = await client.get(f"{DATA_URL}/network-health")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_network_health(client, db):
    token, uid = await _setup_user(client, USER)
    resp = await client.get(
        f"{DATA_URL}/network-health", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_entities"] >= 1
    assert data["total_entities"] >= 1
    assert "network_density" in data
    assert "computed_at" in data


# --- Trust Distribution ---


@pytest.mark.asyncio
async def test_trust_distribution_empty(client):
    token, _ = await _setup_user(client, USER)
    resp = await client.get(
        f"{DATA_URL}/trust-distribution", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "distribution" in data
    assert data["total_scored_entities"] >= 0


@pytest.mark.asyncio
async def test_trust_distribution_with_scores(client, db):
    token, uid = await _setup_user(client, USER)

    from sqlalchemy import update
    await db.execute(
        update(TrustScore)
        .where(TrustScore.entity_id == uuid.UUID(uid))
        .values(score=0.75)
    )
    await db.flush()

    resp = await client.get(
        f"{DATA_URL}/trust-distribution", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_scored_entities"] >= 1
    assert len(data["distribution"]) == 5
    # Our score of 0.75 should be in the "High" bucket (0.6-0.8)
    high_bucket = next(
        b for b in data["distribution"] if b["range_label"] == "High"
    )
    assert high_bucket["count"] >= 1


# --- Growth Trends ---


@pytest.mark.asyncio
async def test_growth_trends(client):
    token, _ = await _setup_user(client, USER)
    resp = await client.get(
        f"{DATA_URL}/growth-trends?days=7", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["period_days"] == 7
    assert "entity_growth" in data
    assert "post_growth" in data
    assert "relationship_growth" in data
    # We created an entity, so entity_growth should have data
    assert len(data["entity_growth"]) >= 1


# --- Activity Patterns ---


@pytest.mark.asyncio
async def test_activity_patterns(client):
    token, _ = await _setup_user(client, USER)

    # Create a post to have some activity
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Activity pattern test"},
        headers=_auth(token),
    )

    resp = await client.get(
        f"{DATA_URL}/activity-patterns?days=7", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["hourly_patterns"]) == 24
    assert "peak_hour_utc" in data
    assert "quietest_hour_utc" in data


# --- Entity Types ---


@pytest.mark.asyncio
async def test_entity_type_breakdown(client):
    token, _ = await _setup_user(client, USER)
    resp = await client.get(
        f"{DATA_URL}/entity-types", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "breakdown" in data
    type_names = [b["entity_type"] for b in data["breakdown"]]
    assert "human" in type_names


# --- Leaderboard ---


@pytest.mark.asyncio
async def test_leaderboard_trust_score(client, db):
    token, uid = await _setup_user(client, USER)

    from sqlalchemy import update
    await db.execute(
        update(TrustScore)
        .where(TrustScore.entity_id == uuid.UUID(uid))
        .values(score=0.9)
    )
    await db.flush()

    resp = await client.get(
        f"{DATA_URL}/leaderboard?metric=trust_score",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["metric"] == "trust_score"
    assert len(data["entities"]) >= 1
    assert data["entities"][0]["trust_score"] is not None


@pytest.mark.asyncio
async def test_leaderboard_posts(client):
    token, _ = await _setup_user(client, USER)

    # Create a post
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Leaderboard post"},
        headers=_auth(token),
    )

    resp = await client.get(
        f"{DATA_URL}/leaderboard?metric=posts",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["metric"] == "posts"
    assert len(data["entities"]) >= 1


@pytest.mark.asyncio
async def test_leaderboard_invalid_metric(client):
    token, _ = await _setup_user(client, USER)
    resp = await client.get(
        f"{DATA_URL}/leaderboard?metric=invalid",
        headers=_auth(token),
    )
    assert resp.status_code == 422


# --- Evolution Stats ---


@pytest.mark.asyncio
async def test_evolution_stats(client):
    token, _ = await _setup_user(client, USER)
    resp = await client.get(
        f"{DATA_URL}/evolution-stats", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_evolution_records" in data
    assert "unique_evolving_agents" in data
    assert "change_type_breakdown" in data


# --- Attestation Network ---


@pytest.mark.asyncio
async def test_attestation_network_stats(client):
    token, _ = await _setup_user(client, USER)
    resp = await client.get(
        f"{DATA_URL}/attestation-network", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_informal_attestations" in data
    assert "total_formal_attestations" in data
    assert "unique_attesters" in data
