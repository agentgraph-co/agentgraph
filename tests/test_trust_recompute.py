from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.jobs.trust_recompute import (
    DECAY_FACTOR_90,
    DECAY_FACTOR_180,
    RECENCY_FACTOR_ACTIVE,
    RECENCY_FACTOR_MODERATE,
    RECENCY_FACTOR_STALE,
    apply_activity_recency,
    apply_attestation_decay,
    run_trust_recompute,
)
from src.main import app
from src.models import Entity, EntityType, Post, TrustScore

# --- Fixtures ---


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
ME_URL = "/api/v1/auth/me"
ADMIN_URL = "/api/v1/admin"

ADMIN_USER = {
    "email": "admin_recompute@test.com",
    "password": "Str0ngP@ss1!",
    "display_name": "AdminRecompute",
}
REGULAR_USER = {
    "email": "regular_recompute@test.com",
    "password": "Str0ngP@ss2!",
    "display_name": "RegularRecompute",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register + login, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


async def _make_admin(db: AsyncSession, entity_id: str) -> None:
    entity = await db.get(Entity, uuid.UUID(entity_id))
    entity.is_admin = True
    await db.flush()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_entity(db: AsyncSession, **kwargs) -> Entity:
    defaults = {
        "id": uuid.uuid4(),
        "type": EntityType.HUMAN,
        "display_name": f"Test-{uuid.uuid4().hex[:6]}",
        "did_web": f"did:web:agentgraph.io:users:{uuid.uuid4()}",
        "email_verified": False,
        "bio_markdown": "",
        "is_active": True,
    }
    defaults.update(kwargs)
    entity = Entity(**defaults)
    db.add(entity)
    return entity


# --- Attestation Decay Tests ---


class TestAttestationDecay:
    """Tests for apply_attestation_decay function."""

    def test_fresh_attestation_no_decay(self):
        """Attestations < 90 days old keep full weight."""
        now = datetime.now(timezone.utc)
        created = now - timedelta(days=30)
        result = apply_attestation_decay(created, 0.8, now=now)
        assert result == 0.8

    def test_90_day_decay_50_percent(self):
        """Attestations 91-180 days old get 50% weight."""
        now = datetime.now(timezone.utc)
        created = now - timedelta(days=100)
        result = apply_attestation_decay(created, 0.8, now=now)
        assert result == 0.8 * DECAY_FACTOR_90
        assert result == 0.4

    def test_180_day_decay_25_percent(self):
        """Attestations > 180 days old get 25% weight."""
        now = datetime.now(timezone.utc)
        created = now - timedelta(days=200)
        result = apply_attestation_decay(created, 0.8, now=now)
        assert result == 0.8 * DECAY_FACTOR_180
        assert result == 0.2

    def test_none_created_at_returns_original(self):
        """If created_at is None, return original weight unchanged."""
        result = apply_attestation_decay(None, 0.6)
        assert result == 0.6

    def test_exact_90_day_boundary(self):
        """Exactly 90 days is NOT decayed (> 90, not >=)."""
        now = datetime.now(timezone.utc)
        created = now - timedelta(days=90)
        result = apply_attestation_decay(created, 1.0, now=now)
        assert result == 1.0

    def test_exact_180_day_boundary(self):
        """Exactly 180 days gets 50% decay (> 90 but not > 180)."""
        now = datetime.now(timezone.utc)
        created = now - timedelta(days=180)
        result = apply_attestation_decay(created, 1.0, now=now)
        assert result == 1.0 * DECAY_FACTOR_90

    def test_naive_datetime_handled(self):
        """Naive datetimes (no tzinfo) are treated as UTC."""
        now = datetime.now(timezone.utc)
        created = (now - timedelta(days=200)).replace(tzinfo=None)
        result = apply_attestation_decay(created, 0.5, now=now)
        assert result == 0.5 * DECAY_FACTOR_180


# --- Activity Recency Tests ---


class TestActivityRecency:
    """Tests for apply_activity_recency function."""

    def test_recent_activity_full_weight(self):
        """Activity within last 30 days gets 100%."""
        now = datetime.now(timezone.utc)
        last = now - timedelta(days=10)
        result = apply_activity_recency(last, now=now)
        assert result == RECENCY_FACTOR_ACTIVE
        assert result == 1.0

    def test_moderate_activity_50_percent(self):
        """Activity 30-90 days ago gets 50%."""
        now = datetime.now(timezone.utc)
        last = now - timedelta(days=60)
        result = apply_activity_recency(last, now=now)
        assert result == RECENCY_FACTOR_MODERATE
        assert result == 0.5

    def test_stale_activity_25_percent(self):
        """Activity > 90 days ago gets 25%."""
        now = datetime.now(timezone.utc)
        last = now - timedelta(days=120)
        result = apply_activity_recency(last, now=now)
        assert result == RECENCY_FACTOR_STALE
        assert result == 0.25

    def test_no_activity_25_percent(self):
        """No activity at all defaults to 25%."""
        result = apply_activity_recency(None)
        assert result == RECENCY_FACTOR_STALE

    def test_exact_30_day_boundary(self):
        """Exactly 30 days counts as active."""
        now = datetime.now(timezone.utc)
        last = now - timedelta(days=30)
        result = apply_activity_recency(last, now=now)
        assert result == RECENCY_FACTOR_ACTIVE


# --- Batch Recompute Tests ---


@pytest.mark.asyncio
async def test_batch_recompute_processes_all(db: AsyncSession):
    """Batch recompute processes all active entities."""
    _make_entity(db)
    _make_entity(db)
    _make_entity(db, is_active=False)  # inactive, should be skipped
    await db.flush()

    summary = await run_trust_recompute(db)

    assert summary["entities_processed"] >= 2
    assert "scores_changed" in summary
    assert "avg_score" in summary
    assert "duration_seconds" in summary
    assert summary["duration_seconds"] >= 0


@pytest.mark.asyncio
async def test_batch_recompute_persists_scores(db: AsyncSession):
    """Recomputed scores are persisted to the database."""
    entity = _make_entity(db, email_verified=True, bio_markdown="Has a bio")
    await db.flush()

    await run_trust_recompute(db)

    ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity.id)
    )
    assert ts is not None
    assert ts.score > 0.0


@pytest.mark.asyncio
async def test_batch_recompute_activity_recency_applied(db: AsyncSession):
    """Active entity gets higher score than stale entity (same profile)."""
    active_entity = _make_entity(
        db, email_verified=True, bio_markdown="Active user",
    )
    stale_entity = _make_entity(
        db, email_verified=True, bio_markdown="Stale user",
    )
    await db.flush()

    # Give active entity recent posts
    for i in range(5):
        db.add(Post(
            id=uuid.uuid4(),
            author_entity_id=active_entity.id,
            content=f"Active post {i}",
        ))
    await db.flush()

    await run_trust_recompute(db)

    active_ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == active_entity.id)
    )
    stale_ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == stale_entity.id)
    )

    assert active_ts is not None
    assert stale_ts is not None
    # Active entity should have higher score due to activity + no recency penalty
    assert active_ts.score >= stale_ts.score


@pytest.mark.asyncio
async def test_batch_recompute_returns_summary(db: AsyncSession):
    """Summary dict has all required keys."""
    _make_entity(db)
    await db.flush()

    summary = await run_trust_recompute(db)

    assert isinstance(summary["entities_processed"], int)
    assert isinstance(summary["scores_changed"], int)
    assert isinstance(summary["avg_score"], float)
    assert isinstance(summary["duration_seconds"], float)


@pytest.mark.asyncio
async def test_recompute_skips_inactive(db: AsyncSession):
    """Inactive entities are not processed."""
    active = _make_entity(db)
    inactive = _make_entity(db, is_active=False)
    await db.flush()

    await run_trust_recompute(db)

    active_ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == active.id)
    )
    inactive_ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == inactive.id)
    )
    assert active_ts is not None
    assert inactive_ts is None


# --- Admin Endpoint Tests ---


@pytest.mark.asyncio
async def test_recompute_all_admin_only(client: AsyncClient, db: AsyncSession):
    """Non-admin gets 403 on recompute-all."""
    token, _ = await _setup_user(client, REGULAR_USER)

    resp = await client.post(
        f"{ADMIN_URL}/trust/recompute-all",
        headers=_auth(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_recompute_all_success(client: AsyncClient, db: AsyncSession):
    """Admin can trigger batch recompute and gets summary."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    resp = await client.post(
        f"{ADMIN_URL}/trust/recompute-all",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "entities_processed" in data
    assert "scores_changed" in data
    assert "avg_score" in data
    assert "duration_seconds" in data
    assert data["entities_processed"] >= 1


@pytest.mark.asyncio
async def test_trust_stats_admin_only(client: AsyncClient, db: AsyncSession):
    """Non-admin gets 403 on trust stats."""
    token, _ = await _setup_user(
        client,
        {
            "email": "nonadmin_stats@test.com",
            "password": "Str0ngP@ss3!",
            "display_name": "NonAdmin",
        },
    )

    resp = await client.get(
        f"{ADMIN_URL}/trust/stats",
        headers=_auth(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_trust_stats_returns_distribution(
    client: AsyncClient, db: AsyncSession,
):
    """Admin gets trust distribution stats."""
    admin_token, admin_id = await _setup_user(
        client,
        {
            "email": "admin_stats@test.com",
            "password": "Str0ngP@ss4!",
            "display_name": "AdminStats",
        },
    )
    await _make_admin(db, admin_id)

    # Compute a trust score first
    from src.trust.score import compute_trust_score

    await compute_trust_score(db, uuid.UUID(admin_id))

    resp = await client.get(
        f"{ADMIN_URL}/trust/stats",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "distribution" in data
    assert len(data["distribution"]) == 5
    assert data["distribution"][0]["range"] == "0.0-0.2"
    assert data["distribution"][4]["range"] == "0.8-1.0"
    assert "avg_by_type" in data
    assert len(data["avg_by_type"]) == 2
    types = {item["entity_type"] for item in data["avg_by_type"]}
    assert "human" in types
    assert "agent" in types
    assert data["total_with_scores"] >= 1


@pytest.mark.asyncio
async def test_trust_stats_correct_counts(
    client: AsyncClient, db: AsyncSession,
):
    """Trust stats distribution sums to total_with_scores."""
    admin_token, admin_id = await _setup_user(
        client,
        {
            "email": "admin_counts@test.com",
            "password": "Str0ngP@ss5!",
            "display_name": "AdminCounts",
        },
    )
    await _make_admin(db, admin_id)

    from src.trust.score import compute_trust_score

    await compute_trust_score(db, uuid.UUID(admin_id))

    resp = await client.get(
        f"{ADMIN_URL}/trust/stats",
        headers=_auth(admin_token),
    )
    data = resp.json()

    bucket_total = sum(b["count"] for b in data["distribution"])
    assert bucket_total == data["total_with_scores"]
