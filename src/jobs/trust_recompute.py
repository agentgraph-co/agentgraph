from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, Post, TrustScore, Vote
from src.trust.score import BATCH_CHUNK_SIZE, batch_recompute

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


async def _apply_recency_chunked(
    db: AsyncSession,
    chunk_size: int = BATCH_CHUNK_SIZE,
) -> tuple[int, float]:
    """Apply activity recency weighting in chunks.

    Iterates over all trust scores using keyset pagination, bulk-loads
    the most recent post/vote dates per chunk, and applies the recency
    multiplier.  Returns (scores_adjusted, total_score_sum).
    """
    last_id: uuid.UUID | None = None
    adjusted = 0
    total_score = 0.0

    while True:
        # Fetch a chunk of trust scores via keyset pagination
        # Skip Moltbook bulk-imported entities (static scores, no activity)
        q = (
            select(TrustScore)
            .join(Entity, TrustScore.entity_id == Entity.id)
            .where(Entity.is_active.is_(True), Entity.framework_source != "moltbook")
            .order_by(TrustScore.entity_id)
            .limit(chunk_size)
        )
        if last_id is not None:
            q = q.where(TrustScore.entity_id > last_id)

        result = await db.execute(q)
        scores = result.scalars().all()
        if not scores:
            break

        entity_ids = [ts.entity_id for ts in scores]
        last_id = entity_ids[-1]

        # Bulk-load last post date per entity
        post_result = await db.execute(
            select(Post.author_entity_id, func.max(Post.created_at))
            .where(Post.author_entity_id.in_(entity_ids))
            .group_by(Post.author_entity_id)
        )
        last_post_map = dict(post_result.all())

        # Bulk-load last vote date per entity
        vote_result = await db.execute(
            select(Vote.entity_id, func.max(Vote.created_at))
            .where(Vote.entity_id.in_(entity_ids))
            .group_by(Vote.entity_id)
        )
        last_vote_map = dict(vote_result.all())

        for ts in scores:
            eid = ts.entity_id
            last_post = last_post_map.get(eid)
            last_vote = last_vote_map.get(eid)
            dates = [d for d in [last_post, last_vote] if d is not None]
            last_activity = max(dates) if dates else None

            recency = apply_activity_recency(last_activity)
            if recency < 1.0:
                ts.score = round(ts.score * (0.5 + 0.5 * recency), 4)
                adjusted += 1

            total_score += ts.score

        await db.flush()

        # Expunge to release memory
        for ts in scores:
            db.expunge(ts)
        del scores, entity_ids, last_post_map, last_vote_map

    return adjusted, total_score


async def run_trust_recompute(
    db: AsyncSession,
) -> dict:
    """Batch recompute trust scores for all active entities.

    Delegates the heavy lifting to ``batch_recompute()`` (which processes
    entities in chunks of 1000 with bulk queries), then applies activity
    recency weighting in a second chunked pass.

    Returns a summary dict:
        entities_processed: int
        scores_changed: int  (score change > 0.1)
        avg_score: float
        duration_seconds: float
    """
    start = time.monotonic()

    # Snapshot old scores for change-detection (lightweight: id + score only)
    old_result = await db.execute(
        select(TrustScore.entity_id, TrustScore.score)
    )
    old_scores: dict[uuid.UUID, float] = dict(old_result.all())

    # Phase 1: chunked batch recompute (handles OOM prevention internally)
    entities_processed = await batch_recompute(db)

    # Phase 2: apply activity recency weighting in chunks
    _, total_score = await _apply_recency_chunked(db)

    # Phase 3: count significant changes
    new_result = await db.execute(
        select(TrustScore.entity_id, TrustScore.score)
    )
    scores_changed = 0
    new_total = 0.0
    new_count = 0
    for eid, new_score in new_result.all():
        new_total += new_score
        new_count += 1
        old = old_scores.get(eid, 0.0)
        if abs(new_score - old) > 0.1:
            scores_changed += 1

    duration = time.monotonic() - start
    avg_score = new_total / new_count if new_count > 0 else 0.0

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
