"""Marketing failure alerting — emails admin when things break.

Three alerting modes:
1. Immediate: called after each marketing tick if failures occurred
2. Periodic: scheduled check for accumulated failures (every tick)
3. Digest: failure summary included in weekly digest email
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.marketing.models import MarketingPost

logger = logging.getLogger(__name__)

# Suppress duplicate alerts via Redis (one alert per 6 hours)
_ALERT_COOLDOWN_KEY = "ag:mktg:failure_alert_sent"
_ALERT_COOLDOWN_SECONDS = 6 * 60 * 60  # 6 hours


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
