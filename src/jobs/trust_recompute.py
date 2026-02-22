from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, Post, TrustScore, Vote
from src.trust.score import compute_trust_score

logger = logging.getLogger(__name__)

# Attestation decay thresholds (days)
DECAY_THRESHOLD_90 = 90
DECAY_THRESHOLD_180 = 180
DECAY_FACTOR_90 = 0.5   # 50% weight for 90-180 day old attestations
DECAY_FACTOR_180 = 0.25  # 25% weight for >180 day old attestations

# Activity recency thresholds (days)
RECENCY_WINDOW_ACTIVE = 30    # last 30 days = 100%
RECENCY_WINDOW_MODERATE = 90  # 30-90 days = 50%
RECENCY_FACTOR_ACTIVE = 1.0
RECENCY_FACTOR_MODERATE = 0.5
RECENCY_FACTOR_STALE = 0.25   # >90 days = 25%


def apply_attestation_decay(
    attestation_created_at: datetime | None,
    original_weight: float,
    now: datetime | None = None,
) -> float:
    """Apply time-based decay to an attestation weight.

    Attestations > 90 days old get 50% weight.
    Attestations > 180 days old get 25% weight.
    Does NOT modify the stored attestation -- returns decayed value only.
    """
    if attestation_created_at is None:
        return original_weight

    if now is None:
        now = datetime.now(timezone.utc)

    created = attestation_created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    age_days = (now - created).days

    if age_days > DECAY_THRESHOLD_180:
        return original_weight * DECAY_FACTOR_180
    elif age_days > DECAY_THRESHOLD_90:
        return original_weight * DECAY_FACTOR_90
    return original_weight


async def get_last_activity_date(
    db: AsyncSession, entity_id: uuid.UUID,
) -> datetime | None:
    """Get the most recent activity date for an entity (post or vote)."""
    last_post = await db.scalar(
        select(func.max(Post.created_at)).where(
            Post.author_entity_id == entity_id,
        )
    )
    last_vote = await db.scalar(
        select(func.max(Vote.created_at)).where(
            Vote.entity_id == entity_id,
        )
    )

    dates = [d for d in [last_post, last_vote] if d is not None]
    if not dates:
        return None
    return max(dates)


def apply_activity_recency(
    last_activity: datetime | None,
    now: datetime | None = None,
) -> float:
    """Compute activity recency multiplier.

    Last 30 days = 1.0 (100%)
    30-90 days = 0.5 (50%)
    >90 days = 0.25 (25%)
    No activity at all = 0.25 (minimum)
    """
    if last_activity is None:
        return RECENCY_FACTOR_STALE

    if now is None:
        now = datetime.now(timezone.utc)

    if last_activity.tzinfo is None:
        last_activity = last_activity.replace(tzinfo=timezone.utc)

    days_since = (now - last_activity).days

    if days_since <= RECENCY_WINDOW_ACTIVE:
        return RECENCY_FACTOR_ACTIVE
    elif days_since <= RECENCY_WINDOW_MODERATE:
        return RECENCY_FACTOR_MODERATE
    return RECENCY_FACTOR_STALE


async def run_trust_recompute(
    db: AsyncSession,
) -> dict:
    """Batch recompute trust scores for all active entities.

    Applies attestation decay and activity recency weighting.

    Returns a summary dict:
        entities_processed: int
        scores_changed: int  (score change > 0.1)
        avg_score: float
        duration_seconds: float
    """
    start = time.monotonic()

    # Fetch all active entity IDs
    result = await db.execute(
        select(Entity.id).where(Entity.is_active.is_(True))
    )
    entity_ids = [row[0] for row in result.fetchall()]

    entities_processed = 0
    scores_changed = 0
    total_score = 0.0

    for eid in entity_ids:
        # Get old score for comparison
        old_ts = await db.scalar(
            select(TrustScore).where(TrustScore.entity_id == eid)
        )
        old_score = old_ts.score if old_ts else 0.0

        # Compute new score (this uses the existing trust computation which
        # already applies attestation decay internally in _community_factor)
        new_ts = await compute_trust_score(db, eid)

        # Apply activity recency weighting as a post-processing multiplier
        last_activity = await get_last_activity_date(db, eid)
        recency = apply_activity_recency(last_activity)

        # Blend: recency affects the score as a soft multiplier
        # We scale between the raw score and a recency-weighted score
        # to avoid zeroing out scores for inactive but well-attested entities
        if recency < 1.0:
            adjusted_score = new_ts.score * (0.5 + 0.5 * recency)
            new_ts.score = round(adjusted_score, 4)
            await db.flush()

        entities_processed += 1
        total_score += new_ts.score

        if abs(new_ts.score - old_score) > 0.1:
            scores_changed += 1

    duration = time.monotonic() - start
    avg_score = total_score / entities_processed if entities_processed > 0 else 0.0

    summary = {
        "entities_processed": entities_processed,
        "scores_changed": scores_changed,
        "avg_score": round(avg_score, 4),
        "duration_seconds": round(duration, 3),
    }

    logger.info(
        "Trust recomputation complete: %d entities processed, "
        "%d scores changed (>0.1), avg=%.4f, took %.3fs",
        entities_processed, scores_changed, avg_score, duration,
    )

    return summary
