"""Production-ready scheduler for periodic jobs.

Uses a simple asyncio-based loop to run trust recomputation every 6 hours.
Started via a startup hook in ``src/main.py`` when the ``ENABLE_SCHEDULER``
config flag is set.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# Default interval: 6 hours (in seconds)
TRUST_RECOMPUTE_INTERVAL = 6 * 60 * 60

_scheduler_task: asyncio.Task | None = None


async def _trust_recompute_loop(interval: int = TRUST_RECOMPUTE_INTERVAL) -> None:
    """Periodically run trust recomputation in the background."""
    from src.database import async_session

    logger.info(
        "Trust recompute scheduler started (interval=%ds)", interval,
    )

    while True:
        await asyncio.sleep(interval)
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


def start_scheduler(interval: int | None = None) -> asyncio.Task:
    """Start the background scheduler task.

    Returns the asyncio.Task so it can be cancelled on shutdown.
    Safe to call multiple times -- subsequent calls are no-ops.
    """
    global _scheduler_task

    if _scheduler_task is not None and not _scheduler_task.done():
        logger.debug("Scheduler already running, skipping start")
        return _scheduler_task

    effective_interval = interval or TRUST_RECOMPUTE_INTERVAL
    _scheduler_task = asyncio.create_task(
        _trust_recompute_loop(effective_interval),
        name="trust-recompute-scheduler",
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
