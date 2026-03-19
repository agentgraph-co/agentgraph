"""Marketing failure alerting — emails admin when things break.

Alert types:
1. Tick failures: called after each marketing tick if failures occurred
2. Auth health: daily sweep of platform adapter credentials
3. Silent zero-post: alert if 24h pass with no posts
4. News signal staleness: alert if digest_history.json is stale
5. Rate limit accumulation: alert if platforms keep rate-limiting
6. Digest: failure summary included in weekly digest email
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.marketing.models import MarketingPost

logger = logging.getLogger(__name__)

# Suppress duplicate alerts via Redis
_ALERT_COOLDOWN_KEY = "ag:mktg:failure_alert_sent"
_ALERT_COOLDOWN_SECONDS = 6 * 60 * 60  # 6 hours
_AUTH_HEALTH_KEY = "ag:mktg:auth_health_alert"
_ZERO_POST_KEY = "ag:mktg:zero_post_alert"
_NEWS_STALE_KEY = "ag:mktg:news_stale_alert"
_RATE_LIMIT_KEY = "ag:mktg:rate_limit_alert"
_DAILY_COOLDOWN = 24 * 60 * 60  # 1 day


async def check_and_alert_failures(
    db: AsyncSession,
    tick_results: dict,
) -> None:
    """Check marketing tick results for failures and alert admin.

    Called after every marketing tick. Only emails if there are
    actual failures AND we haven't alerted in the last 6 hours.
    """
    # Count failures from tick results
    failures: list[dict] = []

    proactive = tick_results.get("proactive", {})
    for err in proactive.get("errors", []):
        failures.append({
            "type": "proactive",
            "platform": err.get("platform", "unknown"),
            "error": err.get("error", "unknown"),
        })

    drafts = tick_results.get("drafts", {})
    for err in drafts.get("errors", []):
        failures.append({
            "type": "draft",
            "id": err.get("id", ""),
            "error": err.get("error", "unknown"),
        })

    monitoring = tick_results.get("monitoring", {})
    if monitoring.get("error"):
        failures.append({
            "type": "monitoring",
            "error": monitoring["error"],
        })
    if monitoring.get("errors", 0) > 0:
        failures.append({
            "type": "monitoring",
            "error": f"{monitoring['errors']} reply failures",
        })

    campaigns = tick_results.get("campaigns", {})
    for err in campaigns.get("errors", []):
        failures.append({
            "type": "campaign_post",
            "platform": err.get("platform", "unknown"),
            "error": err.get("error", "unknown"),
        })

    if not failures:
        return

    # Check cooldown — don't spam admin
    if await _is_on_cooldown():
        logger.info(
            "Marketing failures detected (%d) but alert on cooldown",
            len(failures),
        )
        return

    await _set_cooldown()
    await _send_failure_alert(db, failures)


async def get_failure_summary(
    db: AsyncSession,
    hours: int = 24,
) -> dict:
    """Get failure summary for dashboard or digest.

    Returns counts of failed/permanently_failed posts in the window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    failed_q = await db.execute(
        select(
            MarketingPost.platform,
            MarketingPost.status,
            func.count(MarketingPost.id).label("count"),
        ).where(
            MarketingPost.status.in_(["failed", "permanently_failed"]),
            MarketingPost.updated_at >= cutoff,
        ).group_by(MarketingPost.platform, MarketingPost.status),
    )

    by_platform: dict[str, dict] = {}
    total_failed = 0
    total_permanent = 0

    for row in failed_q.all():
        platform = row.platform
        if platform not in by_platform:
            by_platform[platform] = {
                "failed": 0, "permanently_failed": 0,
            }
        by_platform[platform][row.status] = row.count
        if row.status == "failed":
            total_failed += row.count
        else:
            total_permanent += row.count

    # Get recent error messages for context
    recent_errors_q = await db.execute(
        select(
            MarketingPost.platform,
            MarketingPost.error_message,
            MarketingPost.updated_at,
        ).where(
            MarketingPost.status.in_(
                ["failed", "permanently_failed"],
            ),
            MarketingPost.updated_at >= cutoff,
            MarketingPost.error_message.isnot(None),
        ).order_by(
            MarketingPost.updated_at.desc(),
        ).limit(10),
    )
    recent_errors = [
        {
            "platform": row.platform,
            "error": (row.error_message or "")[:200],
            "at": row.updated_at.isoformat()
            if row.updated_at
            else "",
        }
        for row in recent_errors_q.all()
    ]

    return {
        "total_failed": total_failed,
        "total_permanently_failed": total_permanent,
        "by_platform": by_platform,
        "recent_errors": recent_errors,
    }


async def _is_on_cooldown() -> bool:
    """Check if we've sent a failure alert recently."""
    try:
        from src.redis_client import get_redis

        r = get_redis()
        return bool(await r.get(_ALERT_COOLDOWN_KEY))
    except Exception:
        return False  # If Redis is down, allow the alert


async def _set_cooldown() -> None:
    """Set the cooldown flag after sending an alert."""
    try:
        from src.redis_client import get_redis

        r = get_redis()
        await r.set(
            _ALERT_COOLDOWN_KEY, "1",
            ex=_ALERT_COOLDOWN_SECONDS,
        )
    except Exception:
        pass


async def _send_failure_alert(
    db: AsyncSession,
    failures: list[dict],
) -> None:
    """Send failure alert email + in-app notification."""
    from sqlalchemy import select as sa_select

    from src.email import send_email
    from src.models import Entity, Notification

    # Find admin
    result = await db.execute(
        sa_select(Entity).where(
            Entity.email == "***REMOVED***",
            Entity.is_active.is_(True),
        ).limit(1),
    )
    admin = result.scalar_one_or_none()
    if not admin:
        return

    count = len(failures)
    title = (
        f"MarketingBot: {count} failure"
        f"{'s' if count != 1 else ''} this tick"
    )

    # Build failure list for email
    failure_rows = ""
    for f in failures[:10]:
        platform = f.get("platform", f.get("type", "—"))
        error = f.get("error", "unknown")[:100]
        failure_rows += (
            "<tr>"
            "<td style='padding:6px 10px;"
            "border-bottom:1px solid #334155;"
            f"color:#e2e8f0;'>{f['type']}</td>"
            "<td style='padding:6px 10px;"
            "border-bottom:1px solid #334155;"
            f"color:#e2e8f0;'>{platform}</td>"
            "<td style='padding:6px 10px;"
            "border-bottom:1px solid #334155;"
            f"color:#f87171;'>{error}</td>"
            "</tr>"
        )

    body = (
        f"{count} failures detected in the latest marketing tick. "
        f"Check the dashboard for details."
    )

    html = (
        "<div style='font-family:sans-serif;padding:20px;"
        "background:#0f172a;color:#e2e8f0;'>"
        f"<h2 style='color:#f87171;'>{title}</h2>"
        f"<p>{body}</p>"
        "<table style='width:100%;border-collapse:collapse;"
        "margin:16px 0;'>"
        "<tr>"
        "<th style='text-align:left;padding:6px 10px;"
        "color:#94a3b8;font-size:12px;'>Type</th>"
        "<th style='text-align:left;padding:6px 10px;"
        "color:#94a3b8;font-size:12px;'>Platform</th>"
        "<th style='text-align:left;padding:6px 10px;"
        "color:#94a3b8;font-size:12px;'>Error</th>"
        "</tr>"
        f"{failure_rows}"
        "</table>"
        "<p><a href='https://agentgraph.co/admin' "
        "style='color:#6366f1;'>View Dashboard</a></p>"
        "</div>"
    )

    # In-app notification
    notif = Notification(
        entity_id=admin.id,
        kind="marketing_failure",
        title=title,
        body=body,
    )
    db.add(notif)

    # Email
    await send_email(admin.email, title, html)
    logger.warning(
        "Marketing failure alert sent: %d failures", count,
    )


# -------------------------------------------------------------------
# Watchdog alerts — run once per scheduler tick
# -------------------------------------------------------------------


async def _redis_cooldown_check(key: str, ttl: int) -> bool:
    """Return True if alert was already sent (on cooldown)."""
    try:
        from src.redis_client import get_redis

        r = get_redis()
        if await r.get(key):
            return True
        await r.set(key, "1", ex=ttl)
        return False
    except Exception:
        return False


async def _notify_admin(
    db: AsyncSession,
    kind: str,
    title: str,
    body: str,
    html: str | None = None,
) -> None:
    """Send in-app notification + email to admin."""
    from src.email import send_email
    from src.models import Entity, Notification

    result = await db.execute(
        select(Entity).where(
            Entity.email == "***REMOVED***",
            Entity.is_active.is_(True),
        ).limit(1),
    )
    admin = result.scalar_one_or_none()
    if not admin:
        return

    notif = Notification(
        entity_id=admin.id,
        kind=kind,
        title=title,
        body=body,
    )
    db.add(notif)

    email_html = html or (
        "<div style='font-family:sans-serif;padding:20px;"
        "background:#0f172a;color:#e2e8f0;'>"
        f"<h2 style='color:#f59e0b;'>{title}</h2>"
        f"<p>{body}</p>"
        "<p><a href='https://agentgraph.co/admin' "
        "style='color:#6366f1;'>View Dashboard</a></p>"
        "</div>"
    )
    await send_email(admin.email, title, email_html)
    logger.warning("Watchdog alert sent: %s", title)


async def check_auth_health(db: AsyncSession) -> None:
    """Alert #1: Check all configured adapters for auth failures.

    Runs daily.  If any adapter that *should* be configured fails
    its health check, email admin immediately.
    """
    if await _redis_cooldown_check(
        _AUTH_HEALTH_KEY, _DAILY_COOLDOWN,
    ):
        return

    from src.marketing.orchestrator import _get_adapters

    adapters = _get_adapters()
    unhealthy: list[str] = []

    for name, adapter in adapters.items():
        try:
            if await adapter.is_configured():
                if not await adapter.health_check():
                    unhealthy.append(name)
        except Exception:
            unhealthy.append(name)

    if not unhealthy:
        # Reset cooldown so tomorrow checks again
        try:
            from src.redis_client import get_redis

            r = get_redis()
            await r.delete(_AUTH_HEALTH_KEY)
        except Exception:
            pass
        return

    platforms = ", ".join(unhealthy)
    await _notify_admin(
        db,
        kind="marketing_auth_failure",
        title=(
            f"MarketingBot: {len(unhealthy)} platform"
            f"{'s' if len(unhealthy) != 1 else ''}"
            " failing auth"
        ),
        body=(
            f"Platforms with auth/health failures: {platforms}. "
            f"Check API keys and credentials."
        ),
    )


async def check_zero_post_day(db: AsyncSession) -> None:
    """Alert #2: Alert if no posts were made in the last 24 hours.

    Catches silent failures where the scheduler isn't running or
    all platforms are stuck on cooldown.
    """
    if await _redis_cooldown_check(
        _ZERO_POST_KEY, _DAILY_COOLDOWN,
    ):
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        select(func.count(MarketingPost.id)).where(
            MarketingPost.status == "posted",
            MarketingPost.posted_at >= cutoff,
        ),
    )
    count = result.scalar() or 0

    if count > 0:
        # Posts exist — reset cooldown for tomorrow
        try:
            from src.redis_client import get_redis

            r = get_redis()
            await r.delete(_ZERO_POST_KEY)
        except Exception:
            pass
        return

    await _notify_admin(
        db,
        kind="marketing_zero_posts",
        title="MarketingBot: No posts in 24 hours",
        body=(
            "The marketing bot hasn't posted anything in the "
            "last 24 hours. This could mean the scheduler isn't "
            "running, all platforms are on cooldown, or adapters "
            "are misconfigured."
        ),
    )


async def check_campaign_proposal_delivery(
    db: AsyncSession,
) -> None:
    """Alert #3: Warn if a campaign proposal was generated but no
    email was sent (proposal stuck in 'proposed' for >48h).
    """
    from src.marketing.models import MarketingCampaign

    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    result = await db.execute(
        select(func.count(MarketingCampaign.id)).where(
            MarketingCampaign.status == "proposed",
            MarketingCampaign.created_at <= cutoff,
        ),
    )
    stale_count = result.scalar() or 0

    if stale_count == 0:
        return

    # No cooldown — this is rare enough not to spam
    await _notify_admin(
        db,
        kind="marketing_stale_campaign",
        title=(
            f"MarketingBot: {stale_count} campaign proposal"
            f"{'s' if stale_count != 1 else ''}"
            " awaiting review"
        ),
        body=(
            f"{stale_count} campaign proposal(s) have been "
            f"waiting for approval for over 48 hours. "
            f"Review them in the admin dashboard."
        ),
    )


async def check_news_signal_staleness(
    db: AsyncSession,
) -> None:
    """Alert #4: Warn if the news digest file is missing or stale.

    The news-digest project should sync daily via scp.  If the
    file is >48 hours old or missing entirely, the marketing bot
    is running on HN-only signals.
    """
    if await _redis_cooldown_check(
        _NEWS_STALE_KEY, _DAILY_COOLDOWN,
    ):
        return

    from src.marketing.news_signals import _find_digest_file

    digest_path = _find_digest_file()

    if digest_path is None:
        await _notify_admin(
            db,
            kind="marketing_news_stale",
            title="MarketingBot: News digest file not found",
            body=(
                "digest_history.json is missing from all "
                "expected paths. The marketing bot is running "
                "on HN Algolia signals only. Check that the "
                "news-digest project is syncing via scp."
            ),
        )
        return

    # Check file age
    try:
        mtime = datetime.fromtimestamp(
            digest_path.stat().st_mtime, tz=timezone.utc,
        )
        age_hours = (
            datetime.now(timezone.utc) - mtime
        ).total_seconds() / 3600

        if age_hours > 48:
            await _notify_admin(
                db,
                kind="marketing_news_stale",
                title="MarketingBot: News digest is stale",
                body=(
                    f"digest_history.json is {age_hours:.0f} "
                    f"hours old (last modified: "
                    f"{mtime.strftime('%Y-%m-%d %H:%M UTC')}). "
                    f"The news-digest scp sync may have stopped."
                ),
            )
        else:
            # Fresh — reset cooldown
            try:
                from src.redis_client import get_redis

                r = get_redis()
                await r.delete(_NEWS_STALE_KEY)
            except Exception:
                pass
    except OSError:
        pass  # Can't stat the file — will catch next time


async def check_rate_limit_accumulation(
    db: AsyncSession,
) -> None:
    """Alert #5: Warn if rate-limiting is frequent.

    Rate-limited posts show as 'skipped' in tick results and never
    trigger failure alerts. If multiple platforms are consistently
    rate-limited, something is wrong with cadence config.
    """
    if await _redis_cooldown_check(
        _RATE_LIMIT_KEY, _DAILY_COOLDOWN,
    ):
        return

    # Check Redis for recent rate-limit skip counts
    try:
        from src.redis_client import get_redis

        r = get_redis()
        # The orchestrator logs skips — we track via a counter
        count_raw = await r.get("ag:mktg:rate_limit_count")
        rl_count = int(count_raw) if count_raw else 0

        if rl_count < 5:
            # Reset cooldown if low
            await r.delete(_RATE_LIMIT_KEY)
            return

        # Reset the counter after alerting
        await r.set("ag:mktg:rate_limit_count", "0", ex=86400)
    except Exception:
        return

    await _notify_admin(
        db,
        kind="marketing_rate_limited",
        title=(
            f"MarketingBot: {rl_count} rate-limit"
            f" skips in 24h"
        ),
        body=(
            f"The marketing bot was rate-limited {rl_count} "
            f"times in the last 24 hours. Consider increasing "
            f"platform post intervals in the config."
        ),
    )


async def run_watchdog_checks(db: AsyncSession) -> dict:
    """Run all watchdog checks.  Called once per scheduler tick.

    Returns a summary of which checks ran and any alerts sent.
    """
    results: dict = {}
    checks = [
        ("auth_health", check_auth_health),
        ("zero_post_day", check_zero_post_day),
        ("campaign_proposal", check_campaign_proposal_delivery),
        ("news_staleness", check_news_signal_staleness),
        ("rate_limit", check_rate_limit_accumulation),
    ]

    for name, check_fn in checks:
        try:
            await check_fn(db)
            results[name] = "ok"
        except Exception:
            logger.exception("Watchdog check %s failed", name)
            results[name] = "error"

    return results
