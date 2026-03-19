"""Weekly marketing digest — emailed to admin every Sunday midnight UTC."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.marketing.models import MarketingPost

logger = logging.getLogger(__name__)


async def get_digest_data(db: AsyncSession) -> dict:
    """Gather weekly digest data for dashboard and email."""
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)

    # Posts by platform
    platform_q = await db.execute(
        select(
            MarketingPost.platform,
            func.count(MarketingPost.id).label("count"),
        ).where(
            MarketingPost.status == "posted",
            MarketingPost.posted_at >= week_start,
        ).group_by(MarketingPost.platform),
    )
    platforms = [
        {"platform": row.platform, "posts": row.count}
        for row in platform_q.all()
    ]

    # Cost by model
    cost_q = await db.execute(
        select(
            MarketingPost.llm_model,
            func.count(MarketingPost.id).label("calls"),
            func.coalesce(
                func.sum(MarketingPost.llm_tokens_in + MarketingPost.llm_tokens_out),
                0,
            ).label("tokens"),
            func.coalesce(func.sum(MarketingPost.llm_cost_usd), 0.0).label("cost"),
        ).where(
            MarketingPost.llm_model.isnot(None),
            MarketingPost.created_at >= week_start,
        ).group_by(MarketingPost.llm_model),
    )
    cost_breakdown = [
        {
            "model": row.llm_model,
            "calls": row.calls,
            "tokens": row.tokens,
            "cost_usd": round(float(row.cost), 4),
        }
        for row in cost_q.all()
    ]

    total_cost = sum(c["cost_usd"] for c in cost_breakdown)

    # Top performing posts
    top_q = await db.execute(
        select(MarketingPost).where(
            MarketingPost.status == "posted",
            MarketingPost.posted_at >= week_start,
            MarketingPost.metrics_json.isnot(None),
        ).order_by(MarketingPost.posted_at.desc()).limit(5),
    )
    top_posts = []
    for post in top_q.scalars().all():
        m = post.metrics_json or {}
        engagement = m.get("likes", 0) + m.get("comments", 0) + m.get("shares", 0)
        top_posts.append({
            "platform": post.platform,
            "content": post.content[:120],
            "engagement": engagement,
            "likes": m.get("likes", 0),
            "comments": m.get("comments", 0),
            "shares": m.get("shares", 0),
        })

    total_posts = sum(p["posts"] for p in platforms)

    # Failure summary for the week
    from src.marketing.alerts import get_failure_summary

    failures = await get_failure_summary(db, hours=7 * 24)

    return {
        "week_start": week_start.strftime("%B %d, %Y"),
        "week_end": now.strftime("%B %d, %Y"),
        "platforms": platforms,
        "total_posts": total_posts,
        "cost_breakdown": cost_breakdown,
        "total_cost_usd": round(total_cost, 4),
        "top_posts": top_posts,
        "failures": failures,
    }


async def generate_weekly_digest(db: AsyncSession) -> dict:
    """Generate digest data (used by dashboard API)."""
    return await get_digest_data(db)


async def send_weekly_digest_email(db: AsyncSession) -> bool:
    """Generate and email the weekly digest to admin.

    Called by the scheduler every Sunday midnight UTC.
    Returns True if email was sent successfully.
    """
    from src.email import send_email
    from src.models import Entity

    data = await get_digest_data(db)

    # Find admin
    result = await db.execute(
        select(Entity).where(
            Entity.email == "***REMOVED***",
            Entity.is_active.is_(True),
        ).limit(1),
    )
    admin = result.scalar_one_or_none()
    if not admin:
        logger.warning("No admin entity found for weekly digest email")
        return False

    html = _render_digest_email(data)
    subject = (
        f"AgentGraph Marketing Digest — "
        f"Week of {data['week_start']}"
    )

    sent = await send_email(admin.email, subject, html)
    if sent:
        logger.info("Weekly digest email sent to %s", admin.email)
    else:
        logger.error("Failed to send weekly digest email")
    return sent


def _render_digest_email(data: dict) -> str:
    """Render the weekly digest as an HTML email."""
    from src.email import _load_template

    # Platform rows
    platform_rows = ""
    for p in data["platforms"]:
        platform_rows += (
            "<tr>"
            "<td style='padding:8px 12px;"
            "border-bottom:1px solid #334155;'>"
            f"{p['platform']}</td>"
            "<td style='padding:8px 12px;"
            "border-bottom:1px solid #334155;"
            f"text-align:center;'>{p['posts']}</td>"
            "</tr>"
        )
    if not platform_rows:
        platform_rows = (
            "<tr><td colspan='2' style='padding:8px 12px;"
            "color:#94a3b8;'>No posts this week</td></tr>"
        )

    # Cost rows
    cost_rows = ""
    for c in data["cost_breakdown"]:
        cost_rows += (
            "<tr>"
            "<td style='padding:8px 12px;"
            "border-bottom:1px solid #334155;'>"
            f"{c['model']}</td>"
            "<td style='padding:8px 12px;"
            "border-bottom:1px solid #334155;"
            f"text-align:center;'>{c['calls']}</td>"
            "<td style='padding:8px 12px;"
            "border-bottom:1px solid #334155;"
            f"text-align:right;'>${c['cost_usd']:.4f}</td>"
            "</tr>"
        )
    if not cost_rows:
        cost_rows = (
            "<tr><td colspan='3' style='padding:8px 12px;"
            "color:#94a3b8;'>No LLM usage this week</td></tr>"
        )

    # Top posts
    top_posts_html = ""
    for tp in data["top_posts"]:
        top_posts_html += (
            "<div style='padding:12px;background:#1e293b;"
            "border-radius:8px;margin-bottom:8px;'>"
            "<div style='color:#6366f1;font-size:12px;"
            f"margin-bottom:4px;'>{tp['platform']}</div>"
            "<div style='color:#e2e8f0;font-size:14px;'>"
            f"{tp['content']}</div>"
            "<div style='color:#94a3b8;font-size:12px;"
            f"margin-top:6px;'>{tp['engagement']} engagements "
            f"({tp['likes']} likes, {tp['comments']} comments, "
            f"{tp['shares']} shares)</div>"
            "</div>"
        )
    if not top_posts_html:
        top_posts_html = (
            "<p style='color:#94a3b8;'>"
            "No posts with metrics this week</p>"
        )

    # Failures section
    failures = data.get("failures", {})
    failures_section = ""
    total_failures = (
        failures.get("total_failed", 0)
        + failures.get("total_permanently_failed", 0)
    )
    if total_failures > 0:
        failure_rows = ""
        for platform, counts in failures.get(
            "by_platform", {},
        ).items():
            failed = counts.get("failed", 0)
            perm = counts.get("permanently_failed", 0)
            failure_rows += (
                "<tr>"
                "<td style='padding:8px 12px;"
                "border-bottom:1px solid #334155;"
                f"color:#e2e8f0;'>{platform}</td>"
                "<td style='padding:8px 12px;"
                "border-bottom:1px solid #334155;"
                f"text-align:center;color:#f87171;'>{failed}</td>"
                "<td style='padding:8px 12px;"
                "border-bottom:1px solid #334155;"
                f"text-align:center;color:#ef4444;'>{perm}</td>"
                "</tr>"
            )

        recent_error_html = ""
        for err in failures.get("recent_errors", [])[:5]:
            recent_error_html += (
                "<div style='padding:6px 10px;"
                "background:#1e293b;border-radius:4px;"
                "margin-bottom:4px;font-size:12px;'>"
                "<span style='color:#6366f1;'>"
                f"{err['platform']}</span>"
                "<span style='color:#94a3b8;'> — </span>"
                "<span style='color:#f87171;'>"
                f"{err['error']}</span>"
                "</div>"
            )

        failures_section = (
            "<tr><td style='padding-bottom:24px;'>"
            "<h2 style='color:#f87171;font-size:16px;"
            "margin:0 0 12px;'>"
            f"Failures ({total_failures})</h2>"
            "<table width='100%' cellpadding='0' "
            "cellspacing='0' "
            "style='background:#0f172a;"
            "border-radius:8px;'>"
            "<tr>"
            "<th style='padding:8px 12px;text-align:left;"
            "color:#94a3b8;font-size:12px;'>Platform</th>"
            "<th style='padding:8px 12px;text-align:center;"
            "color:#94a3b8;font-size:12px;'>Failed</th>"
            "<th style='padding:8px 12px;text-align:center;"
            "color:#94a3b8;font-size:12px;'>Permanent</th>"
            "</tr>"
            f"{failure_rows}"
            "</table>"
            f"{recent_error_html}"
            "</td></tr>"
        )

    return _load_template(
        "marketing_digest.html",
        week_start=data["week_start"],
        week_end=data["week_end"],
        total_posts=str(data["total_posts"]),
        total_cost=f"${data['total_cost_usd']:.2f}",
        platform_rows=platform_rows,
        cost_rows=cost_rows,
        top_posts=top_posts_html,
        failures_section=failures_section,
        fallback=(
            f"Marketing Digest: {data['total_posts']} posts, "
            f"${data['total_cost_usd']:.2f} spend"
        ),
    )
