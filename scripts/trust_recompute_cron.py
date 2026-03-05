#!/usr/bin/env python3
"""Scheduled trust score recomputation — designed for cron or systemd timer.

Usage:
    # Daily lightweight recompute
    python3 scripts/trust_recompute_cron.py

    # Weekly deep recompute (with attestation decay + activity recency)
    python3 scripts/trust_recompute_cron.py --deep

    # Crontab examples:
    # Daily at 3 AM:   0 3 * * * cd /app && python3 scripts/trust_recompute_cron.py
    # Weekly deep:     0 4 * * 0 cd /app && python3 scripts/trust_recompute_cron.py --deep
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("trust_recompute")


async def run_simple() -> dict:
    """Run lightweight batch recompute for all active entities."""
    from src.database import async_session
    from src.trust.score import batch_recompute

    start = time.monotonic()
    async with async_session() as db:
        count = await batch_recompute(db)
        await db.commit()
    duration = time.monotonic() - start

    return {
        "mode": "simple",
        "entities_processed": count,
        "duration_seconds": round(duration, 2),
    }


async def run_deep() -> dict:
    """Run enhanced recompute with attestation decay + activity recency."""
    from src.database import async_session
    from src.jobs.trust_recompute import run_trust_recompute

    async with async_session() as db:
        summary = await run_trust_recompute(db)
        await db.commit()

    summary["mode"] = "deep"
    return summary


async def main() -> None:
    parser = argparse.ArgumentParser(description="Scheduled trust recomputation")
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Run enhanced recompute with attestation decay and activity recency",
    )
    args = parser.parse_args()

    logger.info("Starting trust recomputation (mode=%s)", "deep" if args.deep else "simple")

    try:
        if args.deep:
            result = await run_deep()
        else:
            result = await run_simple()

        logger.info("Trust recomputation complete: %s", result)
    except Exception:
        logger.exception("Trust recomputation failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
