from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import CapabilityEndorsement, Entity, Post, Review, TrustScore, Vote

# Weights for trust score components
VERIFICATION_WEIGHT = 0.35
AGE_WEIGHT = 0.15
ACTIVITY_WEIGHT = 0.25
REPUTATION_WEIGHT = 0.25

# Age cap: 1 year
AGE_CAP_DAYS = 365

# Activity log scale denominator
ACTIVITY_LOG_CAP = 100  # log(100) is the max normalizer


def _verification_factor(entity: Entity) -> float:
    """0.0 (unverified) to 1.0 (fully verified)."""
    score = 0.0
    if entity.email_verified:
        score = 0.3
    # Profile completeness: has bio + display_name
    if entity.bio_markdown and len(entity.bio_markdown.strip()) > 0:
        score = max(score, 0.5)
    # Operator-linked agent gets higher base
    if entity.operator_id is not None:
        score = max(score, 0.7)
    return score


def _age_factor(entity: Entity) -> float:
    """0.0 (brand new) to 1.0 (1+ year old)."""
    if entity.created_at is None:
        return 0.0
    now = datetime.now(timezone.utc)
    created = entity.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age_days = (now - created).days
    return min(age_days / AGE_CAP_DAYS, 1.0)


async def _activity_factor(
    db: AsyncSession, entity_id: uuid.UUID
) -> float:
    """Activity in last 30 days, log-scaled to prevent gaming."""
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    # Count posts
    post_count = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == entity_id,
            Post.created_at >= cutoff,
        )
    ) or 0

    # Count votes
    vote_count = await db.scalar(
        select(func.count()).select_from(Vote).where(
            Vote.entity_id == entity_id,
            Vote.created_at >= cutoff,
        )
    ) or 0

    total = post_count + vote_count
    if total == 0:
        return 0.0
    return min(math.log(total + 1) / math.log(ACTIVITY_LOG_CAP), 1.0)


async def _reputation_factor(
    db: AsyncSession, entity_id: uuid.UUID
) -> float:
    """Community reputation based on reviews and endorsements.

    Reviews: average rating / 5 (capped at 1.0)
    Endorsements: log-scaled count
    Combined with 60/40 weight (reviews/endorsements).
    """
    # Average review rating
    avg_rating = await db.scalar(
        select(func.avg(Review.rating)).where(
            Review.target_entity_id == entity_id
        )
    )
    review_score = float(avg_rating) / 5.0 if avg_rating else 0.0

    # Endorsement count (log-scaled)
    endorsement_count = await db.scalar(
        select(func.count()).select_from(CapabilityEndorsement).where(
            CapabilityEndorsement.agent_entity_id == entity_id,
        )
    ) or 0
    endorsement_score = (
        min(math.log(endorsement_count + 1) / math.log(20), 1.0)
        if endorsement_count > 0
        else 0.0
    )

    # Weighted combination: reviews matter more if they exist
    if avg_rating is not None and endorsement_count > 0:
        return 0.6 * review_score + 0.4 * endorsement_score
    elif avg_rating is not None:
        return review_score
    elif endorsement_count > 0:
        return endorsement_score
    return 0.0


async def compute_trust_score(
    db: AsyncSession, entity_id: uuid.UUID
) -> TrustScore:
    """Compute and persist trust score for an entity."""
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise ValueError(f"Entity {entity_id} not found")

    verification = _verification_factor(entity)
    age = _age_factor(entity)
    activity = await _activity_factor(db, entity_id)
    reputation = await _reputation_factor(db, entity_id)

    score = (
        VERIFICATION_WEIGHT * verification
        + AGE_WEIGHT * age
        + ACTIVITY_WEIGHT * activity
        + REPUTATION_WEIGHT * reputation
    )

    components = {
        "verification": round(verification, 4),
        "age": round(age, 4),
        "activity": round(activity, 4),
        "reputation": round(reputation, 4),
    }

    # Upsert trust score
    existing = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    if existing:
        existing.score = round(score, 4)
        existing.components = components
        existing.computed_at = datetime.now(timezone.utc)
        trust_score = existing
    else:
        trust_score = TrustScore(
            id=uuid.uuid4(),
            entity_id=entity_id,
            score=round(score, 4),
            components=components,
            computed_at=datetime.now(timezone.utc),
        )
        db.add(trust_score)

    await db.flush()
    return trust_score


async def batch_recompute(db: AsyncSession) -> int:
    """Recompute trust scores for all active entities. Returns count."""
    result = await db.execute(
        select(Entity.id).where(Entity.is_active.is_(True))
    )
    entity_ids = [row[0] for row in result.fetchall()]
    for eid in entity_ids:
        await compute_trust_score(db, eid)
    return len(entity_ids)
