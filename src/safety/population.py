"""Population composition monitoring for AgentGraph.

Provides four detectors that identify platform-level manipulation patterns:

- **Framework monoculture**: single framework dominating active agent population
- **Operator flood**: single operator registering too many agents in a time window
- **Registration spike**: abnormal daily registration volume vs. 30-day average
- **Sybil cluster**: multiple entities sharing the same registration IP (requires field)

All detectors are async, accept an AsyncSession, and return newly-created
PopulationAlert records.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, EntityType, PopulationAlert

logger = logging.getLogger(__name__)

# Population alert types
POPULATION_ALERT_TYPES = frozenset({
    "framework_monoculture",
    "operator_flood",
    "registration_spike",
    "sybil_cluster",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _has_unresolved_alert(
    db: AsyncSession,
    alert_type: str,
) -> bool:
    """Check if an unresolved alert of this type already exists."""
    count = await db.scalar(
        select(func.count()).select_from(PopulationAlert).where(
            PopulationAlert.alert_type == alert_type,
            PopulationAlert.is_resolved.is_(False),
        )
    )
    return (count or 0) > 0


async def _create_population_alert(
    db: AsyncSession,
    *,
    alert_type: str,
    severity: str,
    details: dict | None = None,
) -> PopulationAlert:
    """Persist a new PopulationAlert row and return it."""
    alert = PopulationAlert(
        id=_uuid.uuid4(),
        alert_type=alert_type,
        severity=severity,
        details=details or {},
    )
    db.add(alert)
    await db.flush()
    return alert


# ---------------------------------------------------------------------------
# Detector 1 -- Framework monoculture
# ---------------------------------------------------------------------------


async def detect_framework_monoculture(
    db: AsyncSession,
    threshold: float = 0.70,
) -> list[PopulationAlert]:
    """Alert if any single framework_source exceeds threshold of active agents.

    Only considers active agents (not humans). A threshold of 0.70 means
    any framework representing >70% of active agents triggers an alert.

    Severity:
    - "medium" if share is between threshold and 0.85
    - "high" if share >= 0.85
    """
    # Skip if there's already an unresolved alert of this type
    if await _has_unresolved_alert(db, "framework_monoculture"):
        return []

    # Count total active agents
    total_agents = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.type == EntityType.AGENT,
            Entity.is_active.is_(True),
        )
    ) or 0

    if total_agents == 0:
        return []

    # Count per framework
    fw_label = func.coalesce(Entity.framework_source, "unknown").label("fw")
    result = await db.execute(
        select(fw_label, func.count().label("cnt"))
        .where(
            Entity.type == EntityType.AGENT,
            Entity.is_active.is_(True),
        )
        .group_by(fw_label)
        .order_by(func.count().desc())
    )
    rows = result.all()

    alerts: list[PopulationAlert] = []
    for framework, count in rows:
        share = count / total_agents
        if share > threshold:
            severity = "high" if share >= 0.85 else "medium"
            alert = await _create_population_alert(
                db,
                alert_type="framework_monoculture",
                severity=severity,
                details={
                    "framework": framework,
                    "agent_count": count,
                    "total_agents": total_agents,
                    "share": round(share, 4),
                    "threshold": threshold,
                },
            )
            alerts.append(alert)
            logger.warning(
                "Framework monoculture detected: %s has %.1f%% share (%d/%d agents)",
                framework, share * 100, count, total_agents,
            )

    return alerts


# ---------------------------------------------------------------------------
# Detector 2 -- Operator flood
# ---------------------------------------------------------------------------


async def detect_operator_flood(
    db: AsyncSession,
    max_agents: int = 10,
    window_hours: int = 24,
) -> list[PopulationAlert]:
    """Alert if any single operator registers >max_agents in window.

    Looks at agents created in the last `window_hours` hours, grouped by
    operator_id. Any operator exceeding the threshold is flagged.

    Severity:
    - "medium" if count is between max_agents and 2*max_agents
    - "high" if count >= 2*max_agents
    """
    if await _has_unresolved_alert(db, "operator_flood"):
        return []

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)

    result = await db.execute(
        select(
            Entity.operator_id,
            func.count().label("cnt"),
        )
        .where(
            Entity.type == EntityType.AGENT,
            Entity.operator_id.isnot(None),
            Entity.created_at >= cutoff,
        )
        .group_by(Entity.operator_id)
        .having(func.count() > max_agents)
    )
    rows = result.all()

    if not rows:
        return []

    # Fetch operator display names for context
    operator_ids = [row[0] for row in rows]
    name_result = await db.execute(
        select(Entity.id, Entity.display_name).where(Entity.id.in_(operator_ids))
    )
    name_map = {eid: name for eid, name in name_result.all()}

    alerts: list[PopulationAlert] = []
    for operator_id, count in rows:
        severity = "high" if count >= 2 * max_agents else "medium"
        alert = await _create_population_alert(
            db,
            alert_type="operator_flood",
            severity=severity,
            details={
                "operator_id": str(operator_id),
                "operator_name": name_map.get(operator_id, "unknown"),
                "agents_registered": count,
                "max_agents": max_agents,
                "window_hours": window_hours,
            },
        )
        alerts.append(alert)
        logger.warning(
            "Operator flood detected: operator %s registered %d agents in %dh",
            operator_id, count, window_hours,
        )

    return alerts


# ---------------------------------------------------------------------------
# Detector 3 -- Registration spike
# ---------------------------------------------------------------------------


async def detect_registration_spike(
    db: AsyncSession,
    multiplier: float = 3.0,
) -> list[PopulationAlert]:
    """Alert if new registrations today exceed multiplier x 30-day daily average.

    Compares the number of entities created in the last 24 hours against
    the average daily registration rate over the prior 30 days.

    Severity:
    - "medium" if rate is between multiplier and 2*multiplier of average
    - "high" if rate >= 2*multiplier of average
    """
    if await _has_unresolved_alert(db, "registration_spike"):
        return []

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_30d = now - timedelta(days=30)

    # Registrations in last 24h
    recent_count = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.created_at >= cutoff_24h,
        )
    ) or 0

    # Registrations in prior 30 days (excluding last 24h for clean average)
    prior_count = await db.scalar(
        select(func.count()).select_from(Entity).where(
            and_(
                Entity.created_at >= cutoff_30d,
                Entity.created_at < cutoff_24h,
            )
        )
    ) or 0

    # Calculate daily average over the 30-day window
    daily_avg = prior_count / 30.0 if prior_count > 0 else 0.0

    # Need at least some historical data to compare against
    if daily_avg == 0:
        return []

    ratio = recent_count / daily_avg

    alerts: list[PopulationAlert] = []
    if ratio > multiplier:
        severity = "high" if ratio >= 2 * multiplier else "medium"
        alert = await _create_population_alert(
            db,
            alert_type="registration_spike",
            severity=severity,
            details={
                "registrations_24h": recent_count,
                "daily_avg_30d": round(daily_avg, 2),
                "ratio": round(ratio, 2),
                "multiplier_threshold": multiplier,
            },
        )
        alerts.append(alert)
        logger.warning(
            "Registration spike detected: %d registrations in 24h "
            "(%.1fx the 30-day daily avg of %.1f)",
            recent_count, ratio, daily_avg,
        )

    return alerts


# ---------------------------------------------------------------------------
# Detector 4 -- Sybil cluster (IP-based)
# ---------------------------------------------------------------------------


async def detect_sybil_cluster(
    db: AsyncSession,
    max_same_ip: int = 5,
    window_hours: int = 24,
) -> list[PopulationAlert]:
    """Alert if >max_same_ip new entities share same registration IP in window.

    NOTE: The Entity model does not currently have a `registration_ip` field.
    This detector is a placeholder and will return an empty list until the
    `registration_ip` column is added to the entities table. When that field
    is added, uncomment the query logic below and remove this early return.
    """
    # TODO: Enable when Entity.registration_ip column is added.
    # The implementation would group recent registrations by IP and flag
    # any IP with more than max_same_ip registrations in the window.
    logger.debug(
        "Sybil cluster detector skipped: Entity.registration_ip field not yet available"
    )
    return []


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------


async def run_all_population_detectors(
    db: AsyncSession,
) -> list[PopulationAlert]:
    """Run all population detectors and return combined alerts."""
    alerts: list[PopulationAlert] = []
    alerts.extend(await detect_framework_monoculture(db))
    alerts.extend(await detect_operator_flood(db))
    alerts.extend(await detect_registration_spike(db))
    alerts.extend(await detect_sybil_cluster(db))
    return alerts
