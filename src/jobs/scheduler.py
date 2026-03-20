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

        # Job 3: External reputation sync (linked accounts)
        try:
            async with async_session() as session:
                async with session.begin():
                    from src.jobs.sync_linked_accounts import sync_stale_linked_accounts

                    summary = await sync_stale_linked_accounts(session)
                    if summary["synced"] > 0:
                        logger.info(
                            "Scheduled linked account sync completed: %s",
                            summary,
                        )
                    else:
                        logger.debug("Linked account sync: nothing to sync")
        except Exception:
            logger.exception("Scheduled linked account sync failed")

        # Job 4: Bot scheduled posts
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

        # Job 5: Token blacklist cleanup (expired entries)
        try:
            async with async_session() as session:
                async with session.begin():
                    from src.api.auth_service import cleanup_expired_blacklist

                    removed = await cleanup_expired_blacklist(session)
                    if removed > 0:
                        logger.info(
                            "Token blacklist cleanup: removed %d expired entries",
                            removed,
                        )
                    else:
                        logger.debug("Token blacklist cleanup: nothing to remove")
        except Exception:
            logger.exception("Token blacklist cleanup failed")

        # Job 6: Source import verification sync
        try:
            async with async_session() as session:
                async with session.begin():
                    from src.jobs.sync_source_imports import sync_stale_source_imports

                    summary = await sync_stale_source_imports(session)
                    if summary["synced"] > 0:
                        logger.info(
                            "Scheduled source import sync completed: %s",
                            summary,
                        )
                    else:
                        logger.debug("Source import sync: nothing to sync")
        except Exception:
            logger.exception("Scheduled source import sync failed")

        # Job 7: Marketing bot orchestrator
        # Gate: only fire after 18:00 UTC (10:00 AM PST) so the daily
        # news digest (arrives ~17:10 UTC / 9:10 AM PST) is available.
        try:
            from datetime import datetime, timezone

            _utc_hour = datetime.now(timezone.utc).hour
            if _utc_hour < 18:
                logger.debug(
                    "Marketing tick skipped: UTC hour %d < 18", _utc_hour,
                )
            else:
                from src.config import settings as _settings

                if _settings.marketing_enabled:
                    async with async_session() as session:
                        async with session.begin():
                            from src.marketing.orchestrator import run_marketing_tick

                            summary = await run_marketing_tick(session)
                            if summary.get("status") != "disabled":
                                logger.info(
                                    "Marketing tick completed: %s", summary,
                                )
        except Exception:
            logger.exception("Marketing tick failed")

        # Job 8: Weekly marketing digest email (Sunday midnight UTC)
        try:
            from datetime import datetime, timezone

            now_utc = datetime.now(timezone.utc)
            if now_utc.weekday() == 6:  # Sunday
                from src.config import settings as _digest_settings

                if _digest_settings.marketing_enabled:
                    # Only send once per Sunday (check Redis flag)
                    _digest_sent = False
                    try:
                        from src.redis_client import get_redis as _get_redis

                        _r = _get_redis()
                        _digest_key = f"ag:mktg:digest_sent:{now_utc.strftime('%Y-%m-%d')}"
                        _digest_sent = bool(await _r.get(_digest_key))
                        if not _digest_sent:
                            await _r.set(_digest_key, "1", ex=86400 * 2)
                    except Exception:
                        pass

                    if not _digest_sent:
                        async with async_session() as session:
                            from src.marketing.digest import send_weekly_digest_email

                            sent = await send_weekly_digest_email(session)
                            if sent:
                                logger.info("Weekly marketing digest email sent")
                            else:
                                logger.warning("Weekly marketing digest email failed")
        except Exception:
            logger.exception("Weekly digest email job failed")

        # Job 10: Marketing metrics refresh
        try:
            from src.config import settings as _metrics_settings

            if _metrics_settings.marketing_enabled:
                async with async_session() as session:
                    async with session.begin():
                        from src.marketing.metrics import (
                            refresh_metrics,
                        )

                        summary = await refresh_metrics(session)
                        if summary.get("updated", 0) > 0:
                            logger.info(
                                "Marketing metrics refresh: %s",
                                summary,
                            )
                        else:
                            logger.debug(
                                "Marketing metrics: nothing to update",
                            )
        except Exception:
            logger.exception("Marketing metrics refresh failed")

        # Job 11: Marketing watchdog checks (auth, zero-post, staleness)
        try:
            from src.config import settings as _watchdog_settings

            if _watchdog_settings.marketing_enabled:
                async with async_session() as session:
                    async with session.begin():
                        from src.marketing.alerts import (
                            run_watchdog_checks,
                        )

                        wd_results = await run_watchdog_checks(
                            session,
                        )
                        logger.debug(
                            "Marketing watchdog: %s", wd_results,
                        )
        except Exception:
            logger.exception("Marketing watchdog checks failed")

        # Job 12: Marketing recap to feed (Monday + Thursday)
        try:
            from src.config import settings as _recap_settings

            if _recap_settings.marketing_enabled:
                async with async_session() as session:
                    async with session.begin():
                        from src.marketing.recap import maybe_post_recap

                        recap_result = await maybe_post_recap(session)
                        if recap_result.get("status") == "posted":
                            logger.info(
                                "Marketing recap posted: %s",
                                recap_result,
                            )
                        else:
                            logger.debug(
                                "Marketing recap: %s",
                                recap_result.get("status", "skipped"),
                            )
        except Exception:
            logger.exception("Marketing recap job failed")

        # Job 13: Expired email verification token cleanup (daily)
        try:
            from datetime import datetime, timedelta, timezone

            _now = datetime.now(timezone.utc)
            # Run once per day — use Redis flag to avoid re-running each tick
            _cleanup_ran = False
            try:
                from src.redis_client import get_redis as _get_redis_cleanup

                _rc = _get_redis_cleanup()
                _cleanup_key = f"ag:jobs:token_cleanup:{_now.strftime('%Y-%m-%d')}"
                _cleanup_ran = bool(await _rc.get(_cleanup_key))
                if not _cleanup_ran:
                    await _rc.set(_cleanup_key, "1", ex=86400 * 2)
            except Exception:
                pass

            if not _cleanup_ran:
                from sqlalchemy import delete as sa_delete

                from src.models import EmailVerification

                async with async_session() as session:
                    async with session.begin():
                        # Remove used tokens older than 30 days
                        cutoff = _now - timedelta(days=30)
                        r1 = await session.execute(
                            sa_delete(EmailVerification).where(
                                EmailVerification.is_used.is_(True),
                                EmailVerification.created_at < cutoff,
                            )
                        )
                        # Remove expired tokens
                        r2 = await session.execute(
                            sa_delete(EmailVerification).where(
                                EmailVerification.expires_at < _now,
                            )
                        )
                        total = r1.rowcount + r2.rowcount
                        if total > 0:
                            logger.info(
                                "Token cleanup: removed %d expired/used email verifications",
                                total,
                            )
                        else:
                            logger.debug("Token cleanup: nothing to remove")
        except Exception:
            logger.exception("Email verification token cleanup failed")

        # Job 9: Moltbook auto-import flywheel
        try:
            from src.config import settings as _mkt_settings

            if _mkt_settings.moltbook_auto_import_enabled:
                async with async_session() as session:
                    async with session.begin():
                        from src.bridges.moltbook.batch_import import run_batch_import

                        summary = await run_batch_import(
                            session,
                            limit=_mkt_settings.moltbook_import_batch_size,
                        )
                        if summary.get("imported", 0) > 0:
                            logger.info(
                                "Moltbook auto-import: %s", summary,
                            )
                        else:
                            logger.debug(
                                "Moltbook auto-import: nothing new",
                            )
        except Exception:
            logger.exception("Moltbook auto-import failed")


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
