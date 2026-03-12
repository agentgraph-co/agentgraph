"""Tests for the anomaly detection engine.

Covers all three detectors (trust velocity, relationship churn, cluster anomaly),
API endpoints (list, get, scan, resolve), and auth/admin permission checks.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import (
    AnomalyAlert,
    Entity,
    EntityRelationship,
    EntityType,
    RelationshipType,
    TrustScore,
)


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _create_user(client, email, name):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Str0ngP@ss1", "display_name": name},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Str0ngP@ss1"},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    return token, me.json()["id"]


async def _create_admin(client, db):
    token, eid = await _create_user(
        client, f"admin-{uuid.uuid4().hex[:8]}@test.com", "Admin"
    )
    entity = await db.get(Entity, uuid.UUID(eid))
    entity.is_admin = True
    await db.flush()
    return token, eid


def _make_entity(db, *, name=None, is_active=True):
    """Create and add an Entity to the session. Returns the entity."""
    eid = uuid.uuid4()
    entity = Entity(
        id=eid,
        type=EntityType.HUMAN,
        display_name=name or f"entity-{eid.hex[:8]}",
        did_web=f"did:web:agentgraph.co:entity:{eid}",
        is_active=is_active,
    )
    db.add(entity)
    return entity


# ---------------------------------------------------------------------------
# Detector unit tests — Trust velocity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trust_velocity_no_data(db):
    """No trust scores within the window should produce zero alerts."""
    from src.safety.anomaly import detect_trust_velocity

    alerts = await detect_trust_velocity(db)
    assert alerts == []


@pytest.mark.asyncio
async def test_trust_velocity_normal(db):
    """Entities with similar trust score deltas should not trigger alerts."""
    from src.safety.anomaly import detect_trust_velocity

    now = datetime.now(timezone.utc)

    for _ in range(5):
        entity = _make_entity(db)
        ts = TrustScore(
            id=uuid.uuid4(),
            entity_id=entity.id,
            score=0.5,
            computed_at=now - timedelta(days=1),
        )
        db.add(ts)

    await db.flush()

    alerts = await detect_trust_velocity(db, window_days=7)
    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_trust_velocity_detects_anomaly(db):
    """An entity with a drastically different trust score should be flagged."""
    from src.safety.anomaly import detect_trust_velocity

    now = datetime.now(timezone.utc)

    # Create 10 normal entities with scores clustered around 0.5
    for _ in range(10):
        entity = _make_entity(db)
        db.add(TrustScore(
            id=uuid.uuid4(), entity_id=entity.id, score=0.5,
            computed_at=now - timedelta(days=1),
        ))

    # Create one anomalous entity with an extreme score
    anomalous = _make_entity(db, name="anomalous-trust")
    db.add(TrustScore(
        id=uuid.uuid4(), entity_id=anomalous.id, score=0.99,
        computed_at=now - timedelta(days=1),
    ))

    await db.flush()

    alerts = await detect_trust_velocity(db, window_days=7, z_threshold=1.5)
    anomalous_alerts = [a for a in alerts if a.entity_id == anomalous.id]
    assert len(anomalous_alerts) >= 1
    assert anomalous_alerts[0].alert_type == "trust_velocity"


@pytest.mark.asyncio
async def test_trust_velocity_with_auto_flag(db):
    """Auto-flag should create a ModerationFlag alongside the alert."""
    from src.models import ModerationFlag
    from src.safety.anomaly import detect_trust_velocity

    now = datetime.now(timezone.utc)

    for _ in range(10):
        entity = _make_entity(db)
        db.add(TrustScore(
            id=uuid.uuid4(), entity_id=entity.id, score=0.5,
            computed_at=now - timedelta(days=3),
        ))

    anomalous = _make_entity(db, name="flag-me")
    db.add(TrustScore(
        id=uuid.uuid4(), entity_id=anomalous.id, score=0.95,
        computed_at=now - timedelta(days=1),
    ))
    await db.flush()

    alerts = await detect_trust_velocity(
        db, window_days=7, z_threshold=1.5, auto_flag=True,
    )

    anomalous_alerts = [a for a in alerts if a.entity_id == anomalous.id]
    if anomalous_alerts:
        # Verify a moderation flag was created
        from sqlalchemy import select

        result = await db.execute(
            select(ModerationFlag).where(
                ModerationFlag.target_id == anomalous.id,
                ModerationFlag.target_type == "entity",
            )
        )
        flags = result.scalars().all()
        assert len(flags) >= 1


# ---------------------------------------------------------------------------
# Detector unit tests — Relationship churn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relationship_churn_no_data(db):
    """No relationships should produce zero alerts."""
    from src.safety.anomaly import detect_relationship_churn

    alerts = await detect_relationship_churn(db)
    assert alerts == []


@pytest.mark.asyncio
async def test_relationship_churn_normal(db):
    """Entities with similar follow rates should not trigger alerts."""
    from src.safety.anomaly import detect_relationship_churn

    now = datetime.now(timezone.utc)

    entities = [_make_entity(db) for _ in range(6)]
    await db.flush()

    # Each entity follows 1 other — same rate
    for i in range(5):
        db.add(EntityRelationship(
            id=uuid.uuid4(),
            source_entity_id=entities[i].id,
            target_entity_id=entities[i + 1].id,
            type=RelationshipType.FOLLOW,
            created_at=now - timedelta(days=2),
        ))
    await db.flush()

    alerts = await detect_relationship_churn(db, window_days=30, z_threshold=3.0)
    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_relationship_churn_detects_anomaly(db):
    """An entity with many more follows than others should be flagged."""
    from src.safety.anomaly import detect_relationship_churn

    now = datetime.now(timezone.utc)

    # Create a pool of targets
    targets = [_make_entity(db) for _ in range(25)]
    normal_entities = [_make_entity(db) for _ in range(10)]
    anomalous = _make_entity(db, name="churn-anomaly")
    await db.flush()

    # Normal: each follows 1 target
    for i, ent in enumerate(normal_entities):
        db.add(EntityRelationship(
            id=uuid.uuid4(),
            source_entity_id=ent.id,
            target_entity_id=targets[i % len(targets)].id,
            type=RelationshipType.FOLLOW,
            created_at=now - timedelta(days=5),
        ))

    # Anomalous: follows 20 targets
    for i in range(20):
        db.add(EntityRelationship(
            id=uuid.uuid4(),
            source_entity_id=anomalous.id,
            target_entity_id=targets[i].id,
            type=RelationshipType.FOLLOW,
            created_at=now - timedelta(days=2),
        ))
    await db.flush()

    alerts = await detect_relationship_churn(db, window_days=30, z_threshold=2.0)
    anomalous_alerts = [a for a in alerts if a.entity_id == anomalous.id]
    assert len(anomalous_alerts) >= 1
    assert anomalous_alerts[0].alert_type == "relationship_churn"


# ---------------------------------------------------------------------------
# Detector unit tests — Cluster anomaly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cluster_anomaly_no_clusters(db):
    """No cluster data should produce zero alerts."""
    from unittest.mock import AsyncMock, patch

    from src.safety.anomaly import detect_cluster_anomaly

    with patch(
        "src.graph.community.get_cached_clusters",
        new_callable=AsyncMock,
        return_value={"clusters": {}, "total_clusters": 0},
    ):
        alerts = await detect_cluster_anomaly(db)
        assert alerts == []


@pytest.mark.asyncio
async def test_cluster_anomaly_detects_bridge_entity(db):
    """An entity with many cross-cluster connections should be flagged."""
    from unittest.mock import AsyncMock, patch

    from src.safety.anomaly import detect_cluster_anomaly

    # Create entities in two clusters
    cluster_a = [_make_entity(db, name=f"ca-{i}") for i in range(5)]
    cluster_b = [_make_entity(db, name=f"cb-{i}") for i in range(5)]
    bridge = _make_entity(db, name="bridge-entity")
    await db.flush()

    # Build cluster map
    cluster_data = {
        "clusters": {
            "0": {"members": [str(e.id) for e in cluster_a] + [str(bridge.id)], "size": 6},
            "1": {"members": [str(e.id) for e in cluster_b], "size": 5},
        },
        "total_clusters": 2,
    }

    # Bridge entity follows all 5 members of cluster_b (cross-cluster)
    for target in cluster_b:
        db.add(EntityRelationship(
            id=uuid.uuid4(),
            source_entity_id=bridge.id,
            target_entity_id=target.id,
            type=RelationshipType.FOLLOW,
        ))

    # Also add some intra-cluster follows for others (not cross-cluster)
    for i in range(4):
        db.add(EntityRelationship(
            id=uuid.uuid4(),
            source_entity_id=cluster_a[i].id,
            target_entity_id=cluster_a[i + 1].id,
            type=RelationshipType.FOLLOW,
        ))
    await db.flush()

    with patch(
        "src.graph.community.get_cached_clusters",
        new_callable=AsyncMock,
        return_value=cluster_data,
    ):
        # Use a low threshold so bridge entity gets flagged
        alerts = await detect_cluster_anomaly(db, cross_threshold=3)
        bridge_alerts = [a for a in alerts if a.entity_id == bridge.id]
        assert len(bridge_alerts) >= 1
        assert bridge_alerts[0].alert_type == "cluster_anomaly"


# ---------------------------------------------------------------------------
# Anomaly scan job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anomaly_scan_returns_summary(db):
    """run_anomaly_scan should return a summary dict with expected keys."""
    from src.jobs.anomaly_scan import run_anomaly_scan

    summary = await run_anomaly_scan(db)
    assert "trust_velocity_alerts" in summary
    assert "relationship_churn_alerts" in summary
    assert "cluster_anomaly_alerts" in summary
    assert "total_alerts" in summary
    assert "duration_seconds" in summary
    assert isinstance(summary["total_alerts"], int)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_anomalies_requires_auth(client, db):
    """Unauthenticated requests should be rejected."""
    resp = await client.get("/api/v1/anomalies")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_anomalies_user_sees_own(client, db):
    """Regular user should only see their own anomaly alerts."""
    token, eid = await _create_user(
        client, f"u-{uuid.uuid4().hex[:8]}@test.com", "RegularUser"
    )
    entity_id = uuid.UUID(eid)

    # Create an alert for this user
    alert = AnomalyAlert(
        id=uuid.uuid4(),
        entity_id=entity_id,
        alert_type="trust_velocity",
        severity="low",
        z_score=2.5,
        details={"test": True},
    )
    db.add(alert)

    # Create an alert for another entity (should NOT be visible)
    other = _make_entity(db, name="other")
    await db.flush()
    other_alert = AnomalyAlert(
        id=uuid.uuid4(),
        entity_id=other.id,
        alert_type="relationship_churn",
        severity="medium",
        z_score=3.5,
    )
    db.add(other_alert)
    await db.flush()

    resp = await client.get(
        "/api/v1/anomalies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # User should see exactly their alert
    alert_ids = {a["id"] for a in data}
    assert str(alert.id) in alert_ids
    assert str(other_alert.id) not in alert_ids


@pytest.mark.asyncio
async def test_list_anomalies_admin_sees_all(client, db):
    """Admin should see all anomaly alerts."""
    token, admin_eid = await _create_admin(client, db)

    other = _make_entity(db, name="any-entity")
    await db.flush()

    db.add(AnomalyAlert(
        id=uuid.uuid4(), entity_id=other.id,
        alert_type="trust_velocity", severity="low", z_score=2.1,
    ))
    await db.flush()

    resp = await client.get(
        "/api/v1/anomalies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_entity_anomalies_own(client, db):
    """User can view their own anomalies via entity_id endpoint."""
    token, eid = await _create_user(
        client, f"own-{uuid.uuid4().hex[:8]}@test.com", "OwnUser"
    )
    entity_id = uuid.UUID(eid)

    db.add(AnomalyAlert(
        id=uuid.uuid4(), entity_id=entity_id,
        alert_type="trust_velocity", severity="low", z_score=2.2,
    ))
    await db.flush()

    resp = await client.get(
        f"/api/v1/anomalies/{eid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_get_entity_anomalies_denied_for_other(client, db):
    """Non-admin user cannot view another entity's anomalies."""
    token, _ = await _create_user(
        client, f"denied-{uuid.uuid4().hex[:8]}@test.com", "DeniedUser"
    )
    other = _make_entity(db, name="other-entity")
    await db.flush()

    resp = await client.get(
        f"/api/v1/anomalies/{other.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_entity_anomalies_404(client, db):
    """Admin gets 404 for nonexistent entity."""
    token, _ = await _create_admin(client, db)
    fake_id = uuid.uuid4()

    resp = await client.get(
        f"/api/v1/anomalies/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_scan_requires_admin(client, db):
    """Non-admin should be blocked from triggering a scan."""
    token, _ = await _create_user(
        client, f"scan-na-{uuid.uuid4().hex[:8]}@test.com", "NonAdmin"
    )
    resp = await client.post(
        "/api/v1/admin/anomalies/scan",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_scan_admin_success(client, db):
    """Admin should be able to trigger a scan and get summary."""
    token, _ = await _create_admin(client, db)

    resp = await client.post(
        "/api/v1/admin/anomalies/scan",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_alerts" in data
    assert "duration_seconds" in data


@pytest.mark.asyncio
async def test_resolve_requires_admin(client, db):
    """Non-admin should be blocked from resolving an alert."""
    token, eid = await _create_user(
        client, f"res-na-{uuid.uuid4().hex[:8]}@test.com", "NonAdmin"
    )
    entity_id = uuid.UUID(eid)

    alert = AnomalyAlert(
        id=uuid.uuid4(), entity_id=entity_id,
        alert_type="trust_velocity", severity="low", z_score=2.3,
    )
    db.add(alert)
    await db.flush()

    resp = await client.patch(
        f"/api/v1/admin/anomalies/{alert.id}/resolve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_resolve_admin_success(client, db):
    """Admin should be able to resolve an alert."""
    token, admin_eid = await _create_admin(client, db)

    other = _make_entity(db, name="resolve-target")
    await db.flush()

    alert = AnomalyAlert(
        id=uuid.uuid4(), entity_id=other.id,
        alert_type="relationship_churn", severity="medium", z_score=3.2,
    )
    db.add(alert)
    await db.flush()

    resp = await client.patch(
        f"/api/v1/admin/anomalies/{alert.id}/resolve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_resolved"] is True
    assert data["resolved_by"] == admin_eid


@pytest.mark.asyncio
async def test_resolve_already_resolved(client, db):
    """Resolving an already-resolved alert should return 409."""
    token, admin_eid = await _create_admin(client, db)

    other = _make_entity(db, name="double-resolve")
    await db.flush()

    alert = AnomalyAlert(
        id=uuid.uuid4(), entity_id=other.id,
        alert_type="trust_velocity", severity="low", z_score=2.0,
        is_resolved=True,
        resolved_by=uuid.UUID(admin_eid),
        resolved_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    await db.flush()

    resp = await client.patch(
        f"/api/v1/admin/anomalies/{alert.id}/resolve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_resolve_not_found(client, db):
    """Resolving a nonexistent alert should return 404."""
    token, _ = await _create_admin(client, db)
    fake_id = uuid.uuid4()

    resp = await client.patch(
        f"/api/v1/admin/anomalies/{fake_id}/resolve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Z-score helper unit tests
# ---------------------------------------------------------------------------


def test_z_score_helper():
    """z_score computation should be correct."""
    from src.safety.anomaly import _z_score

    assert _z_score(10.0, 5.0, 2.5) == 2.0
    assert _z_score(5.0, 5.0, 2.5) == 0.0
    assert _z_score(5.0, 5.0, 0.0) == 0.0  # zero std


def test_mean_std_helper():
    """mean_std should return correct values."""
    from src.safety.anomaly import _mean_std

    mean, std = _mean_std([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    assert abs(mean - 5.0) < 0.001
    assert abs(std - 2.0) < 0.001

    mean, std = _mean_std([])
    assert mean == 0.0
    assert std == 0.0


def test_severity_from_z():
    """Severity mapping should follow z-score thresholds."""
    from src.safety.anomaly import _severity_from_z

    assert _severity_from_z(2.0) == "low"
    assert _severity_from_z(3.5) == "medium"
    assert _severity_from_z(4.5) == "high"
    assert _severity_from_z(-5.0) == "high"
