"""Collusion detection scan job."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.safety.collusion import run_all_collusion_detectors

logger = logging.getLogger(__name__)


async def run_collusion_scan(
    db: AsyncSession,
    *,
    auto_flag: bool = True,
) -> dict:
    """Run all collusion detectors. Returns summary stats."""
    alerts = await run_all_collusion_detectors(db, auto_flag=auto_flag)

    summary = {
        "total_alerts": len(alerts),
        "mutual_attestation": sum(
            1 for a in alerts if a.alert_type == "mutual_attestation"
        ),
        "attestation_cluster": sum(
            1 for a in alerts if a.alert_type == "attestation_cluster"
        ),
        "voting_ring": sum(
            1 for a in alerts if a.alert_type == "voting_ring"
        ),
    }
    logger.info("Collusion scan complete: %s", summary)
    return summary
