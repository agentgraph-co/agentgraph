from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    CapabilityEndorsement,
    Entity,
    Post,
    Review,
    TrustAttestation,
    TrustScore,
    Vote,
)

# Weights for trust score components (v2: 5 components)
VERIFICATION_WEIGHT = 0.35
AGE_WEIGHT = 0.10
ACTIVITY_WEIGHT = 0.20
REPUTATION_WEIGHT = 0.15
COMMUNITY_WEIGHT = 0.20

# Age cap: 1 year
AGE_CAP_DAYS = 365

# Activity log scale denominator
ACTIVITY_LOG_CAP = 100  # log(100) is the max normalizer

# Community attestation config
ATTESTATION_MAX_PER_ATTESTER = 10  # gaming cap
ATTESTATION_DECAY_90_DAYS = 0.5
ATTESTATION_DECAY_180_DAYS = 0.25


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


async def _community_factor(
    db: AsyncSession, entity_id: uuid.UUID
) -> tuple[float, dict[str, float]]:
    """Community attestation factor based on trust attestations.

    Returns (overall_community_score, contextual_scores_dict).

    Attestations are weighted by the attester's trust score at creation time.
    Decay: >90 days = 50% weight, >180 days = 25% weight.
    Gaming cap: max 10 attestations per attester for this target.
    """
    now = datetime.now(timezone.utc)
    cutoff_90 = now - timedelta(days=90)
    cutoff_180 = now - timedelta(days=180)

    # Fetch all attestations for this entity
    result = await db.execute(
        select(TrustAttestation).where(
            TrustAttestation.target_entity_id == entity_id,
        )
    )
    attestations = result.scalars().all()

    if not attestations:
        return 0.0, {}

    # Apply gaming cap: group by attester, keep max ATTESTATION_MAX_PER_ATTESTER per attester
    attester_counts: dict[uuid.UUID, int] = {}
    filtered: list[TrustAttestation] = []
    for att in attestations:
        count = attester_counts.get(att.attester_entity_id, 0)
        if count < ATTESTATION_MAX_PER_ATTESTER:
            filtered.append(att)
            attester_counts[att.attester_entity_id] = count + 1

    if not filtered:
        return 0.0, {}

    # Compute overall weighted average with decay
    total_weight = 0.0
    weighted_sum = 0.0
    # Track per-context scores
    context_weights: dict[str, float] = {}
    context_sums: dict[str, float] = {}

    for att in filtered:
        w = att.weight or 0.5
        created = att.created_at
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        # Apply age decay
        if created and created < cutoff_180:
            w *= ATTESTATION_DECAY_180_DAYS
        elif created and created < cutoff_90:
            w *= ATTESTATION_DECAY_90_DAYS

        weighted_sum += w
        total_weight += 1.0

        # Per-context tracking
        ctx = att.context
        if ctx:
            context_sums[ctx] = context_sums.get(ctx, 0.0) + w
            context_weights[ctx] = context_weights.get(ctx, 0.0) + 1.0

    overall = weighted_sum / total_weight if total_weight > 0 else 0.0
    # Cap at 1.0
    overall = min(overall, 1.0)

    # Compute contextual scores
    contextual_scores: dict[str, float] = {}
    for ctx in context_sums:
        ctx_score = context_sums[ctx] / context_weights[ctx]
        contextual_scores[ctx] = round(min(ctx_score, 1.0), 4)

    return overall, contextual_scores


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
    community, contextual_scores = await _community_factor(db, entity_id)

    score = (
        VERIFICATION_WEIGHT * verification
        + AGE_WEIGHT * age
        + ACTIVITY_WEIGHT * activity
        + REPUTATION_WEIGHT * reputation
        + COMMUNITY_WEIGHT * community
    )

    # Apply framework trust modifier (e.g. OpenClaw agents start at 0.8x)
    framework_modifier = getattr(entity, "framework_trust_modifier", None)
    if framework_modifier is not None and framework_modifier != 1.0:
        score *= framework_modifier

    components = {
        "verification": round(verification, 4),
        "age": round(age, 4),
        "activity": round(activity, 4),
        "reputation": round(reputation, 4),
        "community": round(community, 4),
    }

    # Upsert trust score
    existing = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    if existing:
        existing.score = round(score, 4)
        existing.components = components
        existing.contextual_scores = contextual_scores
        existing.computed_at = datetime.now(timezone.utc)
        trust_score = existing
    else:
        trust_score = TrustScore(
            id=uuid.uuid4(),
            entity_id=entity_id,
            score=round(score, 4),
            components=components,
            contextual_scores=contextual_scores,
            computed_at=datetime.now(timezone.utc),
        )
        db.add(trust_score)

    await db.flush()

    # Dispatch webhook event
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "trust.updated", {
            "entity_id": str(entity_id),
            "score": trust_score.score,
            "components": components,
        })
    except Exception:
        pass  # Best-effort

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
