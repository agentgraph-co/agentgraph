"""Automated moderation: auto-flag on toxicity, auto-hide on flag threshold.

This module wires the Perspective API's should_flag signal into
the moderation system, creating system-generated flags and auto-hiding
posts that accumulate too many flags.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models import ModerationFlag, ModerationReason, Post

logger = logging.getLogger(__name__)


async def auto_flag_post(
    db: AsyncSession,
    post: Post,
    tox_result: object,
) -> None:
    """Create a system-generated moderation flag for a borderline-toxic post.

    Called when toxicity.should_flag is True but should_block is False.
    The post is allowed through but queued for moderator review.
    """
    # Build details string with toxicity scores
    scores = {}
    for attr in ("toxicity", "severe_toxicity", "identity_attack",
                 "insult", "profanity", "threat"):
        val = getattr(tox_result, attr, 0.0)
        if val > 0.1:
            scores[attr] = round(val, 3)

    details = f"Auto-flagged by toxicity detection: {scores}"

    flag = ModerationFlag(
        id=uuid.uuid4(),
        reporter_entity_id=None,  # System-generated (no reporter)
        target_type="post",
        target_id=post.id,
        reason=ModerationReason.HARASSMENT,
        details=details,
    )
    db.add(flag)
    await db.flush()

    logger.info(
        "Auto-flagged post %s (toxicity scores: %s)",
        post.id, scores,
    )

    # Check if post should be auto-hidden (threshold exceeded)
    await _check_auto_hide(db, post)


async def check_flag_threshold(db: AsyncSession, post_id: uuid.UUID) -> None:
    """Check if a post has exceeded the flag threshold and auto-hide it.

    Called after any new flag is created (user or system).
    """
    post = await db.get(Post, post_id)
    if post is None or post.is_hidden:
        return
    await _check_auto_hide(db, post)


async def _check_auto_hide(db: AsyncSession, post: Post) -> None:
    """Auto-hide a post if it has too many flags."""
    if post.is_hidden:
        return

    threshold = getattr(settings, "auto_hide_flag_threshold", 5)

    flag_count = await db.scalar(
        select(func.count(ModerationFlag.id)).where(
            ModerationFlag.target_type == "post",
            ModerationFlag.target_id == post.id,
        )
    )

    if flag_count is not None and flag_count >= threshold:
        post.is_hidden = True
        await db.flush()

        logger.warning(
            "Auto-hidden post %s — reached %d flags (threshold: %d)",
            post.id, flag_count, threshold,
        )
