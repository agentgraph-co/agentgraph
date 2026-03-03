"""Population composition monitoring scan job."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.safety.population import run_all_population_detectors

logger = logging.getLogger(__name__)


async def run_population_scan(
    db: AsyncSession,
) -> dict:
    """Run all population detectors. Returns summary stats."""
    alerts = await run_all_population_detectors(db)

    summary = {
        "total_alerts": len(alerts),
        "framework_monoculture": sum(
            1 for a in alerts if a.alert_type == "framework_monoculture"
        ),
        "operator_flood": sum(
            1 for a in alerts if a.alert_type == "operator_flood"
        ),
        "registration_spike": sum(
            1 for a in alerts if a.alert_type == "registration_spike"
        ),
        "sybil_cluster": sum(
            1 for a in alerts if a.alert_type == "sybil_cluster"
        ),
    }
    logger.info("Population scan complete: %s", summary)
    return summary
