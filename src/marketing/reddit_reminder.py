"""Reddit posting day email reminder.

Sends a reminder email to the admin on Tuesday and Thursday mornings
with the latest Reddit draft content and target subreddits.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.marketing.config import marketing_settings
from src.marketing.models import MarketingPost

logger = logging.getLogger(__name__)

# Reddit posting days: Tuesday (1) and Thursday (3)
_REDDIT_DAYS = {1, 3}


def _is_reddit_posting_day() -> bool:
    """Return True if today is Tuesday or Thursday (UTC)."""
    return datetime.now(timezone.utc).weekday() in _REDDIT_DAYS


async def _get_latest_reddit_draft(db: AsyncSession) -> MarketingPost | None:
    """Fetch the most recent Reddit draft awaiting human review."""
    result = await db.execute(
        select(MarketingPost)
        .where(
            MarketingPost.platform == "reddit",
            MarketingPost.status == "human_review",
        )
        .order_by(MarketingPost.created_at.desc())
        .limit(1),
    )
    return result.scalar_one_or_none()


async def _ensure_reddit_draft(db: AsyncSession) -> MarketingPost | None:
    """Get an existing Reddit draft, or generate one if none exists."""
    draft = await _get_latest_reddit_draft(db)
    if draft is not None:
        return draft

    # No draft exists — generate one via the content engine + draft queue
    logger.info("No Reddit draft found, generating one for today's reminder")
    try:
        from src.marketing.content.engine import generate_proactive
        from src.marketing.draft_queue import enqueue_draft
        from src.marketing.scheduler import get_recent_topics

        recent_topics = await get_recent_topics("reddit")
        content = await generate_proactive("reddit", recent_topics=recent_topics)
        if content.error:
            logger.warning("Failed to generate Reddit content: %s", content.error)
            return None

        draft = await enqueue_draft(
            db,
            platform="reddit",
            content=content.text,
            topic=content.topic,
            llm_model=content.llm_model,
            llm_tokens_in=content.llm_tokens_in,
            llm_tokens_out=content.llm_tokens_out,
            llm_cost_usd=content.llm_cost_usd,
            utm_params=content.utm_params,
        )
        await db.commit()
        return draft
    except Exception:
        logger.exception("Failed to generate Reddit draft for reminder")
        return None


async def send_reddit_reminder(db: AsyncSession) -> bool:
    """Send a Reddit posting day reminder email to the admin.

    Returns True if the email was sent, False otherwise.
    Only sends on Tuesday and Thursday (UTC).
    """
    if not _is_reddit_posting_day():
        logger.debug("Not a Reddit posting day, skipping reminder")
        return False

    # Guard against sending multiple reminders per day
    try:
        from src.redis_client import get_redis

        r = get_redis()
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        sent_key = f"ag:mktg:reddit_reminder:{today_str}"
        already_sent = await r.get(sent_key)
        if already_sent:
            logger.debug("Reddit reminder already sent today")
            return False
    except Exception:
        # If Redis is down, proceed anyway (better to double-send than miss)
        pass

    draft = await _ensure_reddit_draft(db)

    # Build template variables
    from src.marketing.adapters.reddit import TARGET_SUBREDDITS

    subreddits_str = ", ".join(f"r/{s}" for s in TARGET_SUBREDDITS)
    today_date = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")

    if draft:
        draft_content = draft.content
        topic = draft.topic or "General"
    else:
        draft_content = (
            "(No draft was generated — visit the dashboard to create one manually.)"
        )
        topic = "N/A"

    # Build image section (empty if no image)
    image_section = ""

    # Render the email template
    from src.email import _load_template

    html = _load_template(
        "marketing_reddit_reminder.html",
        today_date=today_date,
        subreddits=subreddits_str,
        topic=topic,
        draft_content=draft_content,
        image_section=image_section,
        fallback=(
            f"Reddit posting day! Topic: {topic}. "
            f"Review at https://agentgraph.co/admin"
        ),
    )

    # Send via the email system
    from src.email import send_email

    sent = await send_email(
        marketing_settings.marketing_notify_email,
        "AgentGraph \u2014 Reddit posting day",
        html,
    )

    if sent:
        logger.info("Reddit reminder email sent to %s", marketing_settings.marketing_notify_email)
        # Mark as sent for today
        try:
            from src.redis_client import get_redis

            r = get_redis()
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            sent_key = f"ag:mktg:reddit_reminder:{today_str}"
            await r.set(sent_key, "1", ex=86400)
        except Exception:
            pass
    else:
        logger.warning("Failed to send Reddit reminder email")

    return sent
