"""Anomaly detection engine for AgentGraph.

Provides three statistical detectors that use z-score analysis to identify
suspicious entity behaviour:

- **Trust velocity**: rapid trust score changes (7-day window, threshold |z| > 2)
- **Relationship churn**: abnormal follow/unfollow rate (30-day window, |z| > 3)
- **Cluster anomaly**: entities with unusually high cross-cluster connections

All detectors are async, accept an AsyncSession, and return newly-created
AnomalyAlert records.
"""
from __future__ import annotations

import logging
import math
import uuid as _uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    AnomalyAlert,
    EntityRelationship,
    ModerationFlag,
    ModerationReason,
    ModerationStatus,
    RelationshipType,
    TrustScore,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_SEVERITIES = {"low", "medium", "high"}


def _z_score(value: float, mean: float, std: float) -> float:
    """Compute z-score.  Returns 0 when std is 0 (no variance)."""
    if std == 0:
        return 0.0
    return (value - mean) / std


def _mean_std(values: list[float]) -> tuple[float, float]:
    """Return (mean, population std) for a list of floats."""
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return mean, math.sqrt(variance)


def _severity_from_z(z: float) -> str:
    """Map absolute z-score to a severity label."""
    az = abs(z)
    if az >= 4:
        return "high"
    if az >= 3:
        return "medium"
    return "low"


async def _create_anomaly_alert(
    db: AsyncSession,
    *,
    entity_id: _uuid.UUID,
    alert_type: str,
    z_score: float,
    severity: str | None = None,
    details: dict[str, Any] | None = None,
) -> AnomalyAlert:
    """Persist a new AnomalyAlert row and return it."""
    sev = severity or _severity_from_z(z_score)
    alert = AnomalyAlert(
        id=_uuid.uuid4(),
        entity_id=entity_id,
        alert_type=alert_type,
        severity=sev,
        z_score=round(z_score, 4),
        details=details or {},
    )
    db.add(alert)
    await db.flush()
    return alert


async def _auto_flag_entity(
    db: AsyncSession,
    entity_id: _uuid.UUID,
    reason_text: str,
) -> None:
    """Optionally create a ModerationFlag for the anomalous entity."""
    flag = ModerationFlag(
        id=_uuid.uuid4(),
        reporter_entity_id=None,  # system-generated
        target_type="entity",
        target_id=entity_id,
        reason=ModerationReason.OTHER,
        details=reason_text,
        status=ModerationStatus.PENDING,
    )
    db.add(flag)
    await db.flush()


# ---------------------------------------------------------------------------
# Detector 1 — Trust velocity
# ---------------------------------------------------------------------------

TRUST_VELOCITY_WINDOW_DAYS = 7
TRUST_VELOCITY_Z_THRESHOLD = 2.0


async def detect_trust_velocity(
    db: AsyncSession,
    *,
    window_days: int = TRUST_VELOCITY_WINDOW_DAYS,
    z_threshold: float = TRUST_VELOCITY_Z_THRESHOLD,
    auto_flag: bool = False,
) -> list[AnomalyAlert]:
    """Detect entities whose trust score is anomalous relative to peers.

    Since TrustScore is one-per-entity (updated in place), this detector
    performs z-score analysis on score values of entities whose scores were
    recently computed (within *window_days*).  Any entity whose score deviates
    from the population mean by more than *z_threshold* standard deviations
    is flagged.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)

    # Fetch trust scores computed within the window
    result = await db.execute(
        select(TrustScore.entity_id, TrustScore.score).where(
            TrustScore.computed_at >= cutoff,
        )
    )
    rows = result.all()

    if not rows:
        return []

    scores: dict[_uuid.UUID, float] = {eid: score for eid, score in rows}

    score_values = list(scores.values())
    mean, std = _mean_std(score_values)

    alerts: list[AnomalyAlert] = []
    for eid, score in scores.items():
        z = _z_score(score, mean, std)
        if abs(z) > z_threshold:
            alert = await _create_anomaly_alert(
                db,
                entity_id=eid,
                alert_type="trust_velocity",
                z_score=z,
                details={
                    "score": round(score, 4),
                    "mean_score": round(mean, 4),
                    "std_score": round(std, 4),
                    "window_days": window_days,
                },
            )
            alerts.append(alert)
            if auto_flag:
                await _auto_flag_entity(
                    db, eid,
                    f"Anomaly: trust velocity z={z:.2f} (score={score:.4f})",
                )

    return alerts


# ---------------------------------------------------------------------------
# Detector 2 — Relationship churn
# ---------------------------------------------------------------------------

CHURN_WINDOW_DAYS = 30
CHURN_Z_THRESHOLD = 3.0


async def detect_relationship_churn(
    db: AsyncSession,
    *,
    window_days: int = CHURN_WINDOW_DAYS,
    z_threshold: float = CHURN_Z_THRESHOLD,
    auto_flag: bool = False,
) -> list[AnomalyAlert]:
    """Detect entities with abnormal follow/unfollow activity.

    Counts relationships created per entity per day over *window_days*,
    then flags entities whose daily rate z-score exceeds *z_threshold*.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)

    result = await db.execute(
        select(
            EntityRelationship.source_entity_id,
            func.count(EntityRelationship.id),
        )
        .where(
            EntityRelationship.type == RelationshipType.FOLLOW,
            EntityRelationship.created_at >= cutoff,
        )
        .group_by(EntityRelationship.source_entity_id)
    )
    rows = result.all()

    if not rows:
        return []

    # daily rate = count / window_days
    rates: dict[_uuid.UUID, float] = {}
    for eid, count in rows:
        rates[eid] = count / max(window_days, 1)

    rate_values = list(rates.values())
    mean, std = _mean_std(rate_values)

    alerts: list[AnomalyAlert] = []
    for eid, rate in rates.items():
        z = _z_score(rate, mean, std)
        if abs(z) > z_threshold:
            alert = await _create_anomaly_alert(
                db,
                entity_id=eid,
                alert_type="relationship_churn",
                z_score=z,
                details={
                    "daily_rate": round(rate, 4),
                    "mean_rate": round(mean, 4),
                    "std_rate": round(std, 4),
                    "window_days": window_days,
                    "total_relationships": int(rate * window_days),
                },
            )
            alerts.append(alert)
            if auto_flag:
                await _auto_flag_entity(
                    db, eid,
                    f"Anomaly: relationship churn z={z:.2f} (rate={rate:.4f}/day)",
                )

    return alerts


# ---------------------------------------------------------------------------
# Detector 3 — Cluster anomaly
# ---------------------------------------------------------------------------

CLUSTER_CROSS_THRESHOLD = 10


async def detect_cluster_anomaly(
    db: AsyncSession,
    *,
    cross_threshold: int = CLUSTER_CROSS_THRESHOLD,
    auto_flag: bool = False,
) -> list[AnomalyAlert]:
    """Detect entities with suspiciously many cross-cluster connections.

    Uses community detection from ``src.graph.community`` to obtain cluster
    assignments, then flags entities whose cross-cluster connection count
    exceeds *cross_threshold*.
    """
    try:
        from src.graph.community import get_cached_clusters
    except ImportError:
        logger.warning("Community detection module not available; skipping cluster anomaly check")
        return []

    cluster_data = await get_cached_clusters(db)
    clusters = cluster_data.get("clusters", {})

    if not clusters:
        return []

    # Build entity -> cluster_id map
    entity_cluster: dict[str, str] = {}
    for cid, cdata in clusters.items():
        for member_id in cdata.get("members", []):
            entity_cluster[member_id] = cid

    # Load all follow relationships
    result = await db.execute(
        select(
            EntityRelationship.source_entity_id,
            EntityRelationship.target_entity_id,
        ).where(
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    relationships = result.all()

    # Count cross-cluster connections per entity
    cross_counts: dict[str, int] = defaultdict(int)
    for src_id, tgt_id in relationships:
        src_str = str(src_id)
        tgt_str = str(tgt_id)
        src_cluster = entity_cluster.get(src_str)
        tgt_cluster = entity_cluster.get(tgt_str)
        if src_cluster is not None and tgt_cluster is not None and src_cluster != tgt_cluster:
            cross_counts[src_str] += 1

    if not cross_counts:
        return []

    count_values = list(cross_counts.values())
    mean, std = _mean_std(count_values)

    alerts: list[AnomalyAlert] = []
    for eid_str, count in cross_counts.items():
        if count > cross_threshold:
            z = _z_score(float(count), mean, std)
            try:
                eid = _uuid.UUID(eid_str)
            except ValueError:
                continue

            alert = await _create_anomaly_alert(
                db,
                entity_id=eid,
                alert_type="cluster_anomaly",
                z_score=z,
                details={
                    "cross_cluster_connections": count,
                    "threshold": cross_threshold,
                    "mean_cross": round(mean, 4),
                    "std_cross": round(std, 4),
                },
            )
            alerts.append(alert)
            if auto_flag:
                await _auto_flag_entity(
                    db, eid,
                    f"Anomaly: cross-cluster connections={count} (threshold={cross_threshold})",
                )

    return alerts
