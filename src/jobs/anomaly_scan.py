"""Background job for periodic anomaly scanning.

Runs all three anomaly detectors and persists the results.
Can be triggered manually via the admin API or scheduled via APScheduler.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from src.safety.anomaly import (
    detect_cluster_anomaly,
    detect_relationship_churn,
    detect_trust_velocity,
)

logger = logging.getLogger(__name__)


async def run_anomaly_scan(
    db: AsyncSession,
    *,
    auto_flag: bool = False,
) -> dict:
    """Execute all anomaly detectors and return a summary.

    Args:
        db: Async database session.
        auto_flag: When True, automatically create ModerationFlags for detected
            anomalies.

    Returns:
        Summary dict::

            {
                "trust_velocity_alerts": int,
                "relationship_churn_alerts": int,
                "cluster_anomaly_alerts": int,
                "total_alerts": int,
                "duration_seconds": float,
            }
    """
    start = time.monotonic()

    trust_alerts = await detect_trust_velocity(db, auto_flag=auto_flag)
    churn_alerts = await detect_relationship_churn(db, auto_flag=auto_flag)

    try:
        cluster_alerts = await detect_cluster_anomaly(db, auto_flag=auto_flag)
    except Exception:
        logger.warning("Cluster anomaly detection failed", exc_info=True)
        cluster_alerts = []

    duration = time.monotonic() - start
    total = len(trust_alerts) + len(churn_alerts) + len(cluster_alerts)

    summary = {
        "trust_velocity_alerts": len(trust_alerts),
        "relationship_churn_alerts": len(churn_alerts),
        "cluster_anomaly_alerts": len(cluster_alerts),
        "total_alerts": total,
        "duration_seconds": round(duration, 3),
    }

    logger.info(
        "Anomaly scan complete: %d trust_velocity, %d churn, %d cluster, "
        "total=%d, took %.3fs",
        len(trust_alerts),
        len(churn_alerts),
        len(cluster_alerts),
        total,
        duration,
    )

    return summary
