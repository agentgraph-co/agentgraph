"""Send email notification when marketing drafts need approval.

Fires after the proactive cycle generates human-review drafts for
platforms like Dev.to, LinkedIn, Hashnode, and Reddit.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def notify_pending_drafts(drafts: list[dict]) -> bool:
    """Send an email listing new drafts that need human review.

    Args:
        drafts: List of dicts with keys: platform, topic

    Returns True if the email was sent.
    """
    if not drafts:
        return False

    # Guard: don't send more than once per 6 hours
    try:
        from src.redis_client import get_redis

        r = get_redis()
        key = "ag:mktg:draft_notify"
        already = await r.get(key)
        if already:
            logger.debug("Draft notification already sent recently")
            return False
    except Exception:
        pass

    from src.marketing.config import marketing_settings

    platforms = ", ".join(
        d.get("platform", "unknown").title() for d in drafts
    )
    topics = ", ".join(
        d.get("topic", "general") for d in drafts
    )
    today = datetime.now(timezone.utc).strftime("%A, %B %d")

    from src.email import _load_template, send_email

    html = _load_template(
        "marketing_draft_notify.html",
        today_date=today,
        platforms=platforms,
        topics=topics,
        draft_count=str(len(drafts)),
        dashboard_url="https://agentgraph.co/admin",
        fallback=(
            f"{len(drafts)} marketing draft(s) need review: {platforms}. "
            "Visit https://agentgraph.co/admin"
        ),
    )

    sent = await send_email(
        marketing_settings.marketing_notify_email,
        f"AgentGraph \u2014 {len(drafts)} draft(s) need approval",
        html,
    )

    if sent:
        logger.info("Draft approval notification sent (%d drafts)", len(drafts))
        try:
            from src.redis_client import get_redis

            r = get_redis()
            await r.set(key, "1", ex=21600)  # 6hr cooldown
        except Exception:
            pass

    return sent
