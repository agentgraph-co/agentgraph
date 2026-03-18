"""Weekly performance digest — auto-generated Sunday midnight UTC."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.marketing.content.templates import WEEKLY_DIGEST
from src.marketing.models import MarketingPost

logger = logging.getLogger(__name__)


async def generate_weekly_digest(db: AsyncSession) -> str:
    """Generate a markdown-formatted weekly digest of marketing performance."""
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
    platform_rows_list = []
    for row in platform_q.all():
        platform_rows_list.append(
            f"| {row.platform} | {row.count} | — | — |"
        )
    platform_rows = "\n".join(platform_rows_list) or "| (none) | 0 | — | — |"

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
    cost_rows_list = []
    for row in cost_q.all():
        cost_rows_list.append(
            f"| {row.llm_model} | {row.calls} | {row.tokens} | ${float(row.cost):.4f} |"
        )
    cost_rows = "\n".join(cost_rows_list) or "| (none) | 0 | 0 | $0.00 |"

    # Top performing posts
    top_q = await db.execute(
        select(MarketingPost).where(
            MarketingPost.status == "posted",
            MarketingPost.posted_at >= week_start,
            MarketingPost.metrics_json.isnot(None),
        ).order_by(MarketingPost.posted_at.desc()).limit(5),
    )
    top_list = []
    for post in top_q.scalars().all():
        m = post.metrics_json or {}
        engagement = m.get("likes", 0) + m.get("comments", 0) + m.get("shares", 0)
        top_list.append(
            f"- [{post.platform}] {post.content[:80]}... "
            f"({engagement} engagements)"
        )
    top_posts = "\n".join(top_list) or "- No posts with metrics this week"

    digest = WEEKLY_DIGEST.format(
        week_start=week_start.strftime("%B %d, %Y"),
        platform_rows=platform_rows,
        cost_rows=cost_rows,
        top_posts=top_posts,
        total_clicks=0,  # TODO: wire to analytics_events UTM tracking
        attributed_signups=0,
        cost_per_signup=0.0,
    )

    return digest
