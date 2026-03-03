"""Behavioral baseline computation job.

Computes rolling weekly behavioral metrics for each active entity and
stores them in the behavioral_baselines table.  Prunes baselines older
than 12 weeks (84 days) to keep the rolling window bounded.

No alerting or anomaly detection logic lives here — this is pure data
collection infrastructure for future shaping-dynamics detection.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import date, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    BehavioralBaseline,
    Entity,
    EntityRelationship,
    EvolutionRecord,
    InteractionEvent,
    Post,
    RelationshipType,
    TrustAttestation,
    TrustScore,
    Vote,
)

logger = logging.getLogger(__name__)

# Rolling window: keep 12 weeks of baselines
_ROLLING_WINDOW_DAYS = 84


async def compute_baseline(
    db: AsyncSession,
    entity_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> BehavioralBaseline:
    """Compute behavioral baseline metrics for a single entity over a period.

    Args:
        db: Async database session.
        entity_id: The entity to compute metrics for.
        period_start: Start of the period (inclusive).
        period_end: End of the period (inclusive).

    Returns:
        A persisted BehavioralBaseline record.
    """
    from datetime import datetime

    # Convert dates to datetimes for timestamp comparisons
    start_dt = datetime(
        period_start.year, period_start.month, period_start.day,
        tzinfo=timezone.utc,
    )
    end_dt = datetime(
        period_end.year, period_end.month, period_end.day,
        hour=23, minute=59, second=59, microsecond=999999,
        tzinfo=timezone.utc,
    )

    days_in_period = max((period_end - period_start).days, 1)

    # --- Posts ---
    total_posts = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == entity_id,
            Post.created_at >= start_dt,
            Post.created_at <= end_dt,
        )
    ) or 0

    # --- Replies (posts with parent_post_id set) ---
    total_replies = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == entity_id,
            Post.parent_post_id.isnot(None),
            Post.created_at >= start_dt,
            Post.created_at <= end_dt,
        )
    ) or 0

    # --- Average post length ---
    avg_post_length_val = await db.scalar(
        select(func.avg(func.length(Post.content))).where(
            Post.author_entity_id == entity_id,
            Post.created_at >= start_dt,
            Post.created_at <= end_dt,
        )
    )
    avg_post_length = round(float(avg_post_length_val), 1) if avg_post_length_val else 0.0

    # --- Votes ---
    total_votes = await db.scalar(
        select(func.count()).select_from(Vote).where(
            Vote.entity_id == entity_id,
            Vote.created_at >= start_dt,
            Vote.created_at <= end_dt,
        )
    ) or 0

    # --- New follows (entity is the source) ---
    total_follows = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(
            EntityRelationship.source_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
            EntityRelationship.created_at >= start_dt,
            EntityRelationship.created_at <= end_dt,
        )
    ) or 0

    # --- Attestations given (entity is the attester) ---
    attestations_given = await db.scalar(
        select(func.count()).select_from(TrustAttestation).where(
            TrustAttestation.attester_entity_id == entity_id,
            TrustAttestation.created_at >= start_dt,
            TrustAttestation.created_at <= end_dt,
        )
    ) or 0

    # --- Attestations received (entity is the target) ---
    attestations_received = await db.scalar(
        select(func.count()).select_from(TrustAttestation).where(
            TrustAttestation.target_entity_id == entity_id,
            TrustAttestation.created_at >= start_dt,
            TrustAttestation.created_at <= end_dt,
        )
    ) or 0

    # --- Unique interaction partners (from InteractionEvent) ---
    # Count distinct partners where this entity is entity_a OR entity_b
    partners_as_a = (
        select(InteractionEvent.entity_b_id.label("partner"))
        .where(
            InteractionEvent.entity_a_id == entity_id,
            InteractionEvent.created_at >= start_dt,
            InteractionEvent.created_at <= end_dt,
        )
    )
    partners_as_b = (
        select(InteractionEvent.entity_a_id.label("partner"))
        .where(
            InteractionEvent.entity_b_id == entity_id,
            InteractionEvent.created_at >= start_dt,
            InteractionEvent.created_at <= end_dt,
        )
    )
    all_partners = partners_as_a.union(partners_as_b).subquery()
    unique_partners = await db.scalar(
        select(func.count(func.distinct(all_partners.c.partner)))
    ) or 0

    # --- Top 5 interaction partners by count ---
    # Count interactions where entity is entity_a
    count_a = (
        select(
            InteractionEvent.entity_b_id.label("partner"),
            func.count().label("cnt"),
        )
        .where(
            InteractionEvent.entity_a_id == entity_id,
            InteractionEvent.created_at >= start_dt,
            InteractionEvent.created_at <= end_dt,
        )
        .group_by(InteractionEvent.entity_b_id)
    )
    # Count interactions where entity is entity_b
    count_b = (
        select(
            InteractionEvent.entity_a_id.label("partner"),
            func.count().label("cnt"),
        )
        .where(
            InteractionEvent.entity_b_id == entity_id,
            InteractionEvent.created_at >= start_dt,
            InteractionEvent.created_at <= end_dt,
        )
        .group_by(InteractionEvent.entity_a_id)
    )
    combined = count_a.union_all(count_b).subquery()
    top_result = await db.execute(
        select(
            combined.c.partner,
            func.sum(combined.c.cnt).label("total"),
        )
        .group_by(combined.c.partner)
        .order_by(func.sum(combined.c.cnt).desc())
        .limit(5)
    )
    top_partners: list[dict[str, Any]] = [
        {"entity_id": str(row[0]), "interaction_count": int(row[1])}
        for row in top_result.all()
    ]

    # --- Capability changes (EvolutionRecord count) ---
    capability_changes = await db.scalar(
        select(func.count()).select_from(EvolutionRecord).where(
            EvolutionRecord.entity_id == entity_id,
            EvolutionRecord.created_at >= start_dt,
            EvolutionRecord.created_at <= end_dt,
        )
    ) or 0

    # --- Trust score delta ---
    # TrustScore is a single row per entity (no history table), so we
    # can only capture the current score.  Delta is meaningful when compared
    # across consecutive baselines.  For a single baseline we store 0.0.
    current_trust = await db.scalar(
        select(TrustScore.score).where(TrustScore.entity_id == entity_id)
    )
    trust_score_delta = 0.0  # placeholder — compare across baselines externally

    # --- Assemble metrics ---
    reply_ratio = round(total_replies / total_posts, 4) if total_posts > 0 else 0.0

    metrics: dict[str, Any] = {
        "posts_per_day": round(total_posts / days_in_period, 2),
        "votes_per_day": round(total_votes / days_in_period, 2),
        "follows_per_day": round(total_follows / days_in_period, 2),
        "attestations_given": attestations_given,
        "attestations_received": attestations_received,
        "avg_post_length": avg_post_length,
        "reply_ratio": reply_ratio,
        "unique_interaction_partners": unique_partners,
        "top_partners": top_partners,
        "capability_changes": capability_changes,
        "trust_score_delta": trust_score_delta,
        "trust_score_current": (
            round(float(current_trust), 4) if current_trust is not None else None
        ),
    }

    baseline = BehavioralBaseline(
        entity_id=entity_id,
        period_start=period_start,
        period_end=period_end,
        metrics=metrics,
    )
    db.add(baseline)
    await db.flush()
    return baseline


async def run_weekly_baselines(db: AsyncSession) -> dict:
    """Compute baselines for all active entities for the last 7 days.

    Also prunes baselines older than 12 weeks (84 days) to maintain
    a rolling window.

    Returns:
        Summary dict with entities_processed, baselines_created, pruned,
        and duration_seconds.
    """
    start = time.monotonic()

    today = date.today()
    period_end = today - timedelta(days=1)  # yesterday
    period_start = period_end - timedelta(days=6)  # 7-day window

    # Fetch all active entity IDs
    result = await db.execute(
        select(Entity.id).where(Entity.is_active.is_(True))
    )
    entity_ids = [row[0] for row in result.all()]

    baselines_created = 0
    for eid in entity_ids:
        try:
            await compute_baseline(db, eid, period_start, period_end)
            baselines_created += 1
        except Exception:
            logger.warning(
                "Failed to compute baseline for entity %s", eid, exc_info=True,
            )

    # Prune old baselines (rolling 12-week window)
    cutoff = today - timedelta(days=_ROLLING_WINDOW_DAYS)
    prune_result = await db.execute(
        delete(BehavioralBaseline).where(
            BehavioralBaseline.period_end < cutoff,
        )
    )
    pruned = prune_result.rowcount  # type: ignore[union-attr]

    duration = time.monotonic() - start

    summary = {
        "entities_processed": len(entity_ids),
        "baselines_created": baselines_created,
        "pruned": pruned,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "duration_seconds": round(duration, 3),
    }

    logger.info(
        "Weekly baselines complete: %d entities, %d baselines, %d pruned, %.3fs",
        len(entity_ids),
        baselines_created,
        pruned,
        duration,
    )

    return summary
