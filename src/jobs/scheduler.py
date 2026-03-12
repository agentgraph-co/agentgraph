"""Production-ready scheduler for periodic jobs.

Runs three jobs on the same interval (default 6 hours):
1. Trust recomputation — recalculate all trust scores with attestation decay
2. Provisional agent expiry — deactivate expired provisional agents and revoke keys
3. Bot scheduled posts — official platform bots post content on a cycle

Started via a startup hook in ``src/main.py`` when the ``ENABLE_SCHEDULER``
config flag is set.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# Default interval: 6 hours (in seconds)
SCHEDULER_INTERVAL = 6 * 60 * 60

_scheduler_task: asyncio.Task | None = None


async def _scheduler_loop(interval: int = SCHEDULER_INTERVAL) -> None:
    """Periodically run all scheduled jobs in the background."""
    from src.database import async_session

    logger.info(
        "Background scheduler started (interval=%ds)", interval,
    )

    while True:
        await asyncio.sleep(interval)

        # Job 1: Trust recomputation
        try:
            async with async_session() as session:
                async with session.begin():
                    from src.jobs.trust_recompute import run_trust_recompute

                    summary = await run_trust_recompute(session)
                    logger.info(
                        "Scheduled trust recompute completed: %s", summary,
                    )
        except Exception:
            logger.exception("Scheduled trust recompute failed")

        # Job 2: Provisional agent expiry
        try:
            async with async_session() as session:
                async with session.begin():
                    from src.jobs.expire_provisional import (
                        expire_provisional_agents,
                    )

                    summary = await expire_provisional_agents(session)
                    if summary["expired_count"] > 0:
                        logger.info(
                            "Scheduled provisional expiry completed: %s",
                            summary,
                        )
                    else:
                        logger.debug("Provisional expiry: nothing to expire")
        except Exception:
            logger.exception("Scheduled provisional expiry failed")

        # Job 3: Bot scheduled posts
        try:
            async with async_session() as session:
                async with session.begin():
                    from src.bots.engine import run_scheduled_posts

                    summary = await run_scheduled_posts(session)
                    if summary["posted"]:
                        logger.info(
                            "Scheduled bot posts completed: %s", summary,
                        )
        except Exception:
            logger.exception("Scheduled bot posts failed")


def start_scheduler(interval: int | None = None) -> asyncio.Task:
    """Start the background scheduler task.

    Returns the asyncio.Task so it can be cancelled on shutdown.
    Safe to call multiple times -- subsequent calls are no-ops.
    """
    global _scheduler_task

    if _scheduler_task is not None and not _scheduler_task.done():
        logger.debug("Scheduler already running, skipping start")
        return _scheduler_task

    effective_interval = interval or SCHEDULER_INTERVAL
    _scheduler_task = asyncio.create_task(
        _scheduler_loop(effective_interval),
        name="background-scheduler",
    )
    logger.info("Scheduler task created (interval=%ds)", effective_interval)
    return _scheduler_task


def stop_scheduler() -> None:
    """Cancel the running scheduler task (if any)."""
    global _scheduler_task

    if _scheduler_task is not None and not _scheduler_task.done():
        _scheduler_task.cancel()
        logger.info("Scheduler task cancelled")
    _scheduler_task = None
