"""Human-in-the-loop draft queue for HN, Product Hunt, and other
platforms where bot posting would get flagged or banned.

Posts go to status='human_review' and wait for admin approval.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.marketing.content.engine import content_hash
from src.marketing.models import MarketingPost

logger = logging.getLogger(__name__)


async def enqueue_draft(
    db: AsyncSession,
    platform: str,
    content: str,
    topic: str,
    post_type: str = "proactive",
    llm_model: str | None = None,
    llm_tokens_in: int = 0,
    llm_tokens_out: int = 0,
    llm_cost_usd: float = 0.0,
    utm_params: dict | None = None,
    campaign_id: uuid.UUID | None = None,
) -> MarketingPost:
    """Create a draft post awaiting human review."""
    post = MarketingPost(
        id=uuid.uuid4(),
        campaign_id=campaign_id,
        platform=platform,
        content=content,
        content_hash=content_hash(content),
        post_type=post_type,
        topic=topic,
        status="human_review",
        llm_model=llm_model,
        llm_tokens_in=llm_tokens_in,
        llm_tokens_out=llm_tokens_out,
        llm_cost_usd=llm_cost_usd,
        utm_params=utm_params,
    )
    db.add(post)
    await db.flush()
    logger.info("Draft enqueued for %s: %s (topic=%s)", platform, post.id, topic)
    return post


async def get_pending_drafts(
    db: AsyncSession,
    platform: str | None = None,
    limit: int = 50,
) -> list[MarketingPost]:
    """Get drafts awaiting human review."""
    q = select(MarketingPost).where(
        MarketingPost.status == "human_review",
    ).order_by(MarketingPost.created_at.desc()).limit(limit)

    if platform:
        q = q.where(MarketingPost.platform == platform)

    result = await db.execute(q)
    return list(result.scalars().all())


async def approve_draft(db: AsyncSession, post_id: uuid.UUID) -> MarketingPost | None:
    """Approve a draft — moves it to 'queued' for posting."""
    result = await db.execute(
        select(MarketingPost).where(
            MarketingPost.id == post_id,
            MarketingPost.status == "human_review",
        ),
    )
    post = result.scalar_one_or_none()
    if not post:
        return None

    post.status = "queued"
    await db.flush()
    logger.info("Draft approved: %s (%s)", post.id, post.platform)
    return post


async def reject_draft(
    db: AsyncSession, post_id: uuid.UUID, reason: str = "",
) -> MarketingPost | None:
    """Reject a draft — marks it as 'failed'."""
    result = await db.execute(
        select(MarketingPost).where(
            MarketingPost.id == post_id,
            MarketingPost.status == "human_review",
        ),
    )
    post = result.scalar_one_or_none()
    if not post:
        return None

    post.status = "failed"
    post.error_message = f"Rejected: {reason}" if reason else "Rejected by admin"
    await db.flush()
    logger.info("Draft rejected: %s (%s)", post.id, post.platform)
    return post


async def edit_and_approve(
    db: AsyncSession, post_id: uuid.UUID, new_content: str,
) -> MarketingPost | None:
    """Edit a draft's content and approve it."""
    result = await db.execute(
        select(MarketingPost).where(
            MarketingPost.id == post_id,
            MarketingPost.status == "human_review",
        ),
    )
    post = result.scalar_one_or_none()
    if not post:
        return None

    post.content = new_content
    post.content_hash = content_hash(new_content)
    post.status = "queued"
    await db.flush()
    logger.info("Draft edited and approved: %s (%s)", post.id, post.platform)
    return post
