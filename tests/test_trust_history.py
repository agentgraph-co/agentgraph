"""Tests for trust score history tracking and improvement guidance."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import TrustScore, TrustScoreHistory


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
    "email": "trust_hist_a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "TrustHistA",
}


async def _setup(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


# --- Trust History Endpoint Tests ---


@pytest.mark.asyncio
async def test_trust_history_empty(client: AsyncClient):
    """History endpoint returns empty for entity with no history."""
    _, user_id = await _setup(client, USER_A)
    resp = await client.get(f"/api/v1/trust/{user_id}/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == user_id
    assert data["count"] == 0
    assert data["history"] == []


@pytest.mark.asyncio
async def test_trust_history_with_data(client: AsyncClient, db):
    """History endpoint returns recorded score snapshots."""
    _, user_id = await _setup(client, USER_A)

    # Insert some history records
    for i in range(3):
        h = TrustScoreHistory(
            id=uuid.uuid4(),
            entity_id=user_id,
            score=0.1 * (i + 1),
            components={"verification": 0.1 * (i + 1)},
        )
        db.add(h)
    await db.flush()

    resp = await client.get(f"/api/v1/trust/{user_id}/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3
    assert len(data["history"]) == 3
    # Should be ordered by time ascending
    scores = [p["score"] for p in data["history"]]
    assert scores == sorted(scores)


@pytest.mark.asyncio
async def test_trust_history_days_filter(client: AsyncClient, db):
    """Days parameter filters history by age."""
    _, user_id = await _setup(client, USER_A)

    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    # Recent record
    h1 = TrustScoreHistory(
        id=uuid.uuid4(),
        entity_id=user_id,
        score=0.5,
        components={},
        recorded_at=now - timedelta(days=5),
    )
    # Old record
    h2 = TrustScoreHistory(
        id=uuid.uuid4(),
        entity_id=user_id,
        score=0.3,
        components={},
        recorded_at=now - timedelta(days=60),
    )
    db.add(h1)
    db.add(h2)
    await db.flush()

    # Default 30 days should only get h1
    resp = await client.get(f"/api/v1/trust/{user_id}/history?days=30")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1

    # 90 days should get both
    resp = await client.get(f"/api/v1/trust/{user_id}/history?days=90")
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


# --- Trust Improvements Endpoint Tests ---


@pytest.mark.asyncio
async def test_trust_improvements_no_score(client: AsyncClient):
    """Improvements endpoint returns 404 when no trust score exists."""
    random_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/trust/{random_id}/improvements")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trust_improvements_with_score(client: AsyncClient, db):
    """Improvements endpoint returns ranked tips based on weak components."""
    _, user_id = await _setup(client, USER_A)

    # Create a trust score with some weak components
    ts = TrustScore(
        id=uuid.uuid4(),
        entity_id=user_id,
        score=0.25,
        components={
            "verification": 0.3,
            "age": 0.1,
            "activity": 0.0,
            "reputation": 0.0,
            "community": 0.0,
        },
    )
    db.add(ts)
    await db.flush()

    resp = await client.get(f"/api/v1/trust/{user_id}/improvements")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == user_id
    assert data["current_score"] == 0.25
    assert len(data["improvements"]) >= 4  # At least 4 components need improvement
    # First improvement should be highest potential gain
    assert data["improvements"][0]["potential_gain"] >= data["improvements"][-1]["potential_gain"]
    # Each improvement should have tips
    for imp in data["improvements"]:
        assert len(imp["tips"]) > 0
        assert imp["weight"] > 0


@pytest.mark.asyncio
async def test_trust_improvements_perfect_score(client: AsyncClient, db):
    """Perfect score entity gets minimal improvement suggestions."""
    _, user_id = await _setup(client, USER_A)

    ts = TrustScore(
        id=uuid.uuid4(),
        entity_id=user_id,
        score=1.0,
        components={
            "verification": 1.0,
            "age": 1.0,
            "activity": 1.0,
            "reputation": 1.0,
            "community": 1.0,
        },
    )
    db.add(ts)
    await db.flush()

    resp = await client.get(f"/api/v1/trust/{user_id}/improvements")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_score"] == 1.0
    # No improvements needed when all components are maxed
    assert len(data["improvements"]) == 0


@pytest.mark.asyncio
async def test_trust_history_recorded_on_compute(client: AsyncClient, db):
    """Trust score computation creates history records."""
    _, user_id = await _setup(client, USER_A)

    # Trigger trust computation via refresh
    from src.trust.score import compute_trust_score
    await compute_trust_score(db, uuid.UUID(user_id))

    # Check that a history record was created
    from sqlalchemy import select
    result = await db.execute(
        select(TrustScoreHistory).where(
            TrustScoreHistory.entity_id == uuid.UUID(user_id),
        )
    )
    records = result.scalars().all()
    assert len(records) >= 1
    assert records[0].score >= 0
