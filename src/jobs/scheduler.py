"""Production-ready scheduler for periodic jobs.

Runs multiple jobs on the same interval (default 6 hours):
1. Trust recomputation — recalculate all trust scores with attestation decay
2. Provisional agent expiry — deactivate expired provisional agents and revoke keys
3. External reputation sync (linked accounts)
4. Bot scheduled posts — official platform bots post content on a cycle
5. Token blacklist cleanup (expired entries)
6. Source import verification sync
7. Marketing bot orchestrator (after 18:00 UTC)
8. Weekly marketing digest email (Sunday)
9. [REMOVED] Moltbook auto-import — synthetic data removed March 2026
10. Marketing metrics refresh
11. Marketing watchdog checks
12. Marketing recap to feed (Monday + Thursday)
13. Expired token cleanup — email verifications + password reset tokens (daily)
14. Reply Guy monitor — check reply targets for new posts
15. Reply Guy drafter — generate LLM reply drafts for new opportunities
16. Bluesky starter pack refresh — recreate starter pack every 30 days
17. Agent cleanup — hard-delete soft-deleted agents after grace period
18. Auto-follow — follow active Bluesky reply targets daily

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
_reply_monitor_task: asyncio.Task | None = None
_reply_drafter_task: asyncio.Task | None = None
_starter_pack_task: asyncio.Task | None = None
_auto_follow_task: asyncio.Task | None = None

# Reply Guy intervals (in seconds)
REPLY_MONITOR_INTERVAL = 15 * 60   # 15 minutes
REPLY_DRAFTER_INTERVAL = 30 * 60   # 30 minutes

# Bluesky starter pack refresh interval (30 days in seconds)
STARTER_PACK_INTERVAL = 30 * 24 * 60 * 60

# Auto-follow interval (24 hours)
AUTO_FOLLOW_INTERVAL = 24 * 60 * 60


async def _scheduler_loop(interval: int = SCHEDULER_INTERVAL) -> None:
    """Periodically run all scheduled jobs in the background."""
    from src.database import async_session

    logger.info(
        "Background scheduler started (interval=%ds)", interval,
    )

    while True:
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
                        logger.warning(
                            "Redis unavailable for digest tracking, skipping",
                            exc_info=True,
                        )

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

        # Job 13: Expired token cleanup — email verifications + password reset tokens (daily)
        try:
            from datetime import datetime, timedelta, timezone

            from sqlalchemy import text

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
                logger.warning(
                    "Redis unavailable for token cleanup tracking, skipping",
                    exc_info=True,
                )

            if not _cleanup_ran:
                _cutoff = _now - timedelta(days=30)

                async with async_session() as session:
                    async with session.begin():
                        # 1. Remove used email verifications older than 30 days
                        r1 = await session.execute(
                            text(
                                "DELETE FROM email_verifications "
                                "WHERE is_used = true AND created_at < :cutoff"
                            ),
                            {"cutoff": _cutoff},
                        )
                        # 2. Remove expired email verifications
                        r2 = await session.execute(
                            text(
                                "DELETE FROM email_verifications "
                                "WHERE expires_at < :now"
                            ),
                            {"now": _now},
                        )
                        # 3. Remove password reset tokens older than 30 days
                        r3 = await session.execute(
                            text(
                                "DELETE FROM password_reset_tokens "
                                "WHERE created_at < :cutoff"
                            ),
                            {"cutoff": _cutoff},
                        )
                        ev_total = r1.rowcount + r2.rowcount
                        prt_total = r3.rowcount
                        total = ev_total + prt_total
                        if total > 0:
                            logger.info(
                                "Token cleanup: removed %d email verifications, "
                                "%d password reset tokens",
                                ev_total,
                                prt_total,
                            )
                        else:
                            logger.debug("Token cleanup: nothing to remove")
        except Exception:
            logger.exception("Token cleanup failed")

        # Job 17: Hard-delete soft-deleted agents (daily)
        # Agents are soft-deleted (is_active=false) on user request;
        # this job does the actual CASCADE delete off the hot path.
        try:
            from datetime import datetime, timedelta, timezone

            from sqlalchemy import text

            _now_del = datetime.now(timezone.utc)
            _del_ran = False
            try:
                from src.redis_client import get_redis as _get_redis_del

                _rc_del = _get_redis_del()
                _del_key = f"ag:jobs:agent_cleanup:{_now_del.strftime('%Y-%m-%d')}"
                _del_ran = bool(await _rc_del.get(_del_key))
                if not _del_ran:
                    await _rc_del.set(_del_key, "1", ex=86400 * 2)
            except Exception:
                pass

            if not _del_ran:
                # Delete agents inactive for at least 5 minutes (grace period)
                _del_cutoff = _now_del - timedelta(minutes=5)
                async with async_session() as session:
                    async with session.begin():
                        r = await session.execute(
                            text(
                                "DELETE FROM entities "
                                "WHERE type = 'AGENT' "
                                "AND is_active = false "
                                "AND updated_at < :cutoff"
                            ),
                            {"cutoff": _del_cutoff},
                        )
                        if r.rowcount > 0:
                            logger.info(
                                "Agent cleanup: hard-deleted %d inactive agents",
                                r.rowcount,
                            )
                        else:
                            logger.debug("Agent cleanup: nothing to remove")
        except Exception:
            logger.exception("Agent cleanup failed")

        # Job 9: [REMOVED] Moltbook auto-import — synthetic data removed March 2026

        # Job 10: Operator recruitment (GitHub outreach)
        try:
            from src.config import settings as _recruit_settings

            if _recruit_settings.recruitment_enabled:
                async with async_session() as session:
                    async with session.begin():
                        from src.recruitment.github_discovery import (
                            run_discovery_cycle,
                        )

                        discovered = await run_discovery_cycle(session)
                        if discovered > 0:
                            logger.info(
                                "Recruitment discovery: %d new prospects", discovered,
                            )
                        else:
                            logger.debug("Recruitment discovery: nothing new")

                async with async_session() as session:
                    async with session.begin():
                        from src.recruitment.github_outreach import (
                            run_outreach_cycle,
                        )

                        sent = await run_outreach_cycle(session)
                        if sent > 0:
                            logger.info(
                                "Recruitment outreach: %d issues created", sent,
                            )
                        else:
                            logger.debug("Recruitment outreach: nothing to send")
        except Exception:
            logger.exception("Recruitment cycle failed")

        await asyncio.sleep(interval)


async def _reply_monitor_loop(interval: int = REPLY_MONITOR_INTERVAL) -> None:
    """Job 14: Check reply targets for new posts on a fast loop."""
    logger.info("Reply guy monitor started (interval=%ds)", interval)
    while True:
        try:
            from src.config import settings as _rg_settings

            if _rg_settings.reply_guy_enabled:
                from src.marketing.reply_guy.monitor import monitor_all_targets

                stats = await monitor_all_targets()
                if stats.get("new_opportunities", 0) > 0:
                    logger.info("Reply guy monitor: %s", stats)
                else:
                    logger.debug("Reply guy monitor: %s", stats)
        except Exception:
            logger.exception("Reply guy monitor failed")
        await asyncio.sleep(interval)


async def _reply_drafter_loop(interval: int = REPLY_DRAFTER_INTERVAL) -> None:
    """Job 15: Generate LLM reply drafts for new opportunities on a fast loop."""
    logger.info("Reply guy drafter started (interval=%ds)", interval)
    while True:
        try:
            from src.config import settings as _rg_settings

            if _rg_settings.reply_guy_enabled:
                from src.marketing.reply_guy.drafter import generate_drafts

                stats = await generate_drafts(limit=20)
                if stats.get("drafted", 0) > 0:
                    logger.info("Reply guy drafter: %s", stats)
                else:
                    logger.debug("Reply guy drafter: %s", stats)
        except Exception:
            logger.exception("Reply guy drafter failed")
        await asyncio.sleep(interval)


async def _starter_pack_loop(interval: int = STARTER_PACK_INTERVAL) -> None:
    """Job 16: Refresh the Bluesky starter pack every 30 days."""
    import os

    try:
        from scripts.create_bluesky_starter_pack import CURATED_ACCOUNTS
        from scripts.create_bluesky_starter_pack import main as _sp_main
    except ImportError:
        logger.warning(
            "Starter pack script not available (scripts/ not in path), "
            "disabling Job 16",
        )
        return

    logger.info("Bluesky starter pack refresh started (interval=%ds)", interval)
    while True:
        try:
            from src.config import settings as _sp_settings

            if not _sp_settings.starter_pack_refresh_enabled:
                logger.debug("Starter pack refresh disabled, sleeping")
                await asyncio.sleep(interval)
                continue

            # Get Bluesky credentials from marketing config
            from src.marketing.config import marketing_settings

            handle = marketing_settings.bluesky_handle
            password = marketing_settings.bluesky_app_password
            if not handle or not password:
                logger.warning(
                    "Starter pack refresh skipped: BLUESKY_HANDLE or "
                    "BLUESKY_APP_PASSWORD not set in marketing config"
                )
                await asyncio.sleep(interval)
                continue

            # Inject credentials into env for the script's main()
            _prev_handle = os.environ.get("BLUESKY_HANDLE")
            _prev_password = os.environ.get("BLUESKY_PASSWORD")
            os.environ["BLUESKY_HANDLE"] = handle
            os.environ["BLUESKY_PASSWORD"] = password
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, _sp_main)
                logger.info(
                    "Bluesky starter pack refreshed (%d curated accounts)",
                    len(CURATED_ACCOUNTS),
                )
            finally:
                # Restore previous env state
                if _prev_handle is not None:
                    os.environ["BLUESKY_HANDLE"] = _prev_handle
                else:
                    os.environ.pop("BLUESKY_HANDLE", None)
                if _prev_password is not None:
                    os.environ["BLUESKY_PASSWORD"] = _prev_password
                else:
                    os.environ.pop("BLUESKY_PASSWORD", None)
        except Exception:
            logger.exception("Bluesky starter pack refresh failed")
        await asyncio.sleep(interval)


async def _auto_follow_loop(interval: int = AUTO_FOLLOW_INTERVAL) -> None:
    """Job 18: Auto-follow active Bluesky reply targets daily."""
    logger.info("Auto-follow task started (interval=%ds)", interval)
    while True:
        try:
            from src.marketing.auto_follow import run_auto_follow

            stats = await run_auto_follow()
            if stats.get("followed", 0) > 0:
                logger.info("Auto-follow: %s", stats)
            else:
                logger.debug("Auto-follow: %s", stats)
        except Exception:
            logger.exception("Auto-follow failed")
        await asyncio.sleep(interval)


def start_scheduler(interval: int | None = None) -> asyncio.Task:
    """Start the background scheduler task.

    Returns the asyncio.Task so it can be cancelled on shutdown.
    Safe to call multiple times -- subsequent calls are no-ops.
    """
    global _scheduler_task, _reply_monitor_task, _reply_drafter_task
    global _starter_pack_task, _auto_follow_task

    if _scheduler_task is not None and not _scheduler_task.done():
        logger.debug("Scheduler already running, skipping start")
        return _scheduler_task

    effective_interval = interval or SCHEDULER_INTERVAL
    _scheduler_task = asyncio.create_task(
        _scheduler_loop(effective_interval),
        name="background-scheduler",
    )
    logger.info("Scheduler task created (interval=%ds)", effective_interval)

    # Reply Guy fast-loop tasks (gated by reply_guy_enabled inside each loop)
    from src.config import settings as _sched_settings

    # Job 16: Bluesky starter pack refresh (30-day loop)
    if _sched_settings.starter_pack_refresh_enabled:
        if _starter_pack_task is None or _starter_pack_task.done():
            _starter_pack_task = asyncio.create_task(
                _starter_pack_loop(),
                name="bluesky-starter-pack-refresh",
            )
            logger.info(
                "Bluesky starter pack task created (interval=%ds)",
                STARTER_PACK_INTERVAL,
            )

    # Job 18: Auto-follow Bluesky reply targets (daily)
    if _auto_follow_task is None or _auto_follow_task.done():
        _auto_follow_task = asyncio.create_task(
            _auto_follow_loop(),
            name="auto-follow-bluesky",
        )
        logger.info(
            "Auto-follow task created (interval=%ds)",
            AUTO_FOLLOW_INTERVAL,
        )

    if _sched_settings.reply_guy_enabled:
        if _reply_monitor_task is None or _reply_monitor_task.done():
            _reply_monitor_task = asyncio.create_task(
                _reply_monitor_loop(),
                name="reply-guy-monitor",
            )
            logger.info(
                "Reply guy monitor task created (interval=%ds)",
                REPLY_MONITOR_INTERVAL,
            )
        if _reply_drafter_task is None or _reply_drafter_task.done():
            _reply_drafter_task = asyncio.create_task(
                _reply_drafter_loop(),
                name="reply-guy-drafter",
            )
            logger.info(
                "Reply guy drafter task created (interval=%ds)",
                REPLY_DRAFTER_INTERVAL,
            )

    return _scheduler_task


def stop_scheduler() -> None:
    """Cancel the running scheduler task (if any)."""
    global _scheduler_task, _reply_monitor_task, _reply_drafter_task
    global _starter_pack_task, _auto_follow_task

    if _scheduler_task is not None and not _scheduler_task.done():
        _scheduler_task.cancel()
        logger.info("Scheduler task cancelled")
    _scheduler_task = None

    if _reply_monitor_task is not None and not _reply_monitor_task.done():
        _reply_monitor_task.cancel()
        logger.info("Reply guy monitor task cancelled")
    _reply_monitor_task = None

    if _reply_drafter_task is not None and not _reply_drafter_task.done():
        _reply_drafter_task.cancel()
        logger.info("Reply guy drafter task cancelled")
    _reply_drafter_task = None

    if _starter_pack_task is not None and not _starter_pack_task.done():
        _starter_pack_task.cancel()
        logger.info("Bluesky starter pack task cancelled")
    _starter_pack_task = None

    if _auto_follow_task is not None and not _auto_follow_task.done():
        _auto_follow_task.cancel()
        logger.info("Auto-follow task cancelled")
    _auto_follow_task = None
