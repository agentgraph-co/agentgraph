from __future__ import annotations

import logging
import math
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    CapabilityEndorsement,
    Entity,
    LinkedAccount,
    Post,
    Review,
    TrustAttestation,
    TrustScore,
    TrustScoreHistory,
    Vote,
)

logger = logging.getLogger(__name__)

# Weights for trust score components (v3: 6 components)
# External reputation is additive — 0.0 if no accounts linked
VERIFICATION_WEIGHT = 0.30
AGE_WEIGHT = 0.08
ACTIVITY_WEIGHT = 0.18
REPUTATION_WEIGHT = 0.14
COMMUNITY_WEIGHT = 0.18
EXTERNAL_WEIGHT = 0.12

# Age cap: 1 year
AGE_CAP_DAYS = 365

# Activity log scale denominator
ACTIVITY_LOG_CAP = 100  # log(100) is the max normalizer

# Community attestation config
ATTESTATION_MAX_PER_ATTESTER = 10  # gaming cap
ATTESTATION_DECAY_90_DAYS = 0.5
ATTESTATION_DECAY_180_DAYS = 0.25

# Contextual attestation boost: matching-context attestations count 1.5x
CONTEXTUAL_MATCH_MULTIPLIER = 1.5

# Blended score weights when context parameter is provided
CONTEXT_BLEND_BASE_WEIGHT = 0.70
CONTEXT_BLEND_CONTEXTUAL_WEIGHT = 0.30


def _verification_factor(entity: Entity) -> float:
    """0.0 (unverified) to 1.0 (fully verified)."""
    score = 0.0
    # Source-verified imports get a floor of 0.15
    if getattr(entity, "source_verified_at", None) is not None:
        score = 0.15
    if entity.email_verified:
        score = max(score, 0.3)
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
    db: AsyncSession,
    entity_id: uuid.UUID,
    boost_context: str | None = None,
) -> tuple[float, dict[str, float]]:
    """Community attestation factor based on trust attestations.

    Returns (overall_community_score, contextual_scores_dict).

    Attestations are weighted by the attester's trust score at creation time.
    Decay: >90 days = 50% weight, >180 days = 25% weight.
    Gaming cap: max 10 attestations per attester for this target.

    When ``boost_context`` is provided, attestations whose context matches
    are weighted at CONTEXTUAL_MATCH_MULTIPLIER (1.5x) in the overall
    community score calculation.
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

        # Apply contextual match boost: attestations in the requested context
        # are weighted 1.5x to promote contextual trust into the overall score.
        effective_w = w
        if boost_context and att.context and att.context == boost_context:
            effective_w = w * CONTEXTUAL_MATCH_MULTIPLIER

        weighted_sum += effective_w
        total_weight += 1.0

        # Per-context tracking (uses base weight, not boosted)
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


async def _external_reputation_factor(
    db: AsyncSession, entity_id: uuid.UUID
) -> float:
    """External reputation based on linked accounts.

    Returns AVG(reputation_score * verification_weight) across linked accounts.
    Returns 0.0 if no linked accounts (never penalizes).
    """
    from src.external_reputation import VERIFICATION_WEIGHTS

    result = await db.execute(
        select(LinkedAccount).where(
            LinkedAccount.entity_id == entity_id,
        )
    )
    accounts = result.scalars().all()

    if not accounts:
        return 0.0

    total = 0.0
    count = 0
    for acct in accounts:
        weight = VERIFICATION_WEIGHTS.get(acct.verification_status, 0.0)
        if weight > 0 and acct.reputation_score is not None:
            total += acct.reputation_score * weight
            count += 1

    return total / count if count > 0 else 0.0


def _source_reputation_score(community_signals: dict) -> float:
    """Map community signals (GitHub stars, npm downloads, etc.) to a 0-1 score.

    Used for imported bots to populate the external_reputation component
    based on their source platform community standing.
    """
    score = 0.0

    stars = community_signals.get("stars") or 0
    if stars > 0:
        # log-scaled: 10 stars ~0.2, 100 ~0.4, 1000 ~0.6, 10000 ~0.8
        score = max(score, min(math.log10(stars + 1) / 5.0, 1.0))

    downloads = community_signals.get("downloads_monthly") or 0
    if downloads > 0:
        # log-scaled: 100 ~0.2, 1000 ~0.3, 10000 ~0.4, 100000 ~0.5
        dl_score = min(math.log10(downloads + 1) / 6.0, 1.0)
        score = max(score, dl_score)

    forks = community_signals.get("forks") or 0
    if forks > 0:
        forks_score = min(math.log10(forks + 1) / 4.0, 1.0)
        score = max(score, forks_score)

    likes = community_signals.get("likes") or 0
    if likes > 0:
        likes_score = min(math.log10(likes + 1) / 4.0, 1.0)
        score = max(score, likes_score)

    return round(score, 4)


async def create_import_trust_score(
    db: AsyncSession,
    entity_id: uuid.UUID,
    source_type: str,
    community_signals: dict,
    framework_trust_modifier: float | None = None,
) -> TrustScore:
    """Create an initial TrustScore for a source-imported bot.

    Produces a starting score around 0.20-0.30 depending on:
    - Base verification credit (0.15) for being source-verified
    - Community signals mapped to external_reputation
    - Framework trust modifier (e.g. 0.65 for Moltbook)

    This avoids the imported bot showing 0.0 on its profile page.
    """
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise ValueError(f"Entity {entity_id} not found")

    # Verification: source-verified floor
    verification = _verification_factor(entity)

    # Age: brand new, will be ~0
    age = _age_factor(entity)

    # Activity/reputation/community: 0 for a fresh import
    activity = 0.0
    reputation = 0.0
    community = 0.0

    # External reputation from community signals
    external = _source_reputation_score(community_signals)

    score = (
        VERIFICATION_WEIGHT * verification
        + AGE_WEIGHT * age
        + ACTIVITY_WEIGHT * activity
        + REPUTATION_WEIGHT * reputation
        + COMMUNITY_WEIGHT * community
        + EXTERNAL_WEIGHT * external
    )

    # Apply framework trust modifier (e.g. Moltbook 0.65x)
    if framework_trust_modifier is not None and framework_trust_modifier != 1.0:
        score *= framework_trust_modifier

    components = {
        "verification": round(verification, 4),
        "age": round(age, 4),
        "activity": round(activity, 4),
        "reputation": round(reputation, 4),
        "community": round(community, 4),
        "external_reputation": round(external, 4),
        "import_source": source_type,
    }

    trust_score = TrustScore(
        id=uuid.uuid4(),
        entity_id=entity_id,
        score=round(score, 4),
        components=components,
        contextual_scores={},
        computed_at=datetime.now(timezone.utc),
    )
    db.add(trust_score)
    await db.flush()
    await db.refresh(trust_score)

    # Record initial history snapshot
    history = TrustScoreHistory(
        id=uuid.uuid4(),
        entity_id=entity_id,
        score=round(score, 4),
        components=components,
        recorded_at=datetime.now(timezone.utc),
    )
    db.add(history)
    await db.flush()

    return trust_score


def _update_primary_context(
    entity: Entity,
    contextual_scores: dict[str, float],
) -> None:
    """Set entity.primary_context to the most frequent context.

    Uses the contextual_scores dict (which is keyed by context) as a proxy
    for attestation frequency — the context with the highest score is
    selected as the primary domain for this entity.

    Skips silently if no contextual attestations exist.
    """
    if not contextual_scores:
        return
    # Pick the context with the highest score (ties broken arbitrarily)
    best_ctx = max(contextual_scores, key=lambda c: contextual_scores[c])
    entity.primary_context = best_ctx


async def compute_contextual_blend(
    db: AsyncSession,
    entity_id: uuid.UUID,
    context: str,
) -> dict:
    """Compute a blended trust score: 70% base + 30% contextual for *context*.

    Returns a dict with ``base_score``, ``contextual_score``, and the blended
    ``score``.  If no contextual data exists for *context*, the base score is
    returned as-is (with ``contextual_score`` set to ``None``).
    """
    # Get or compute the base trust score
    ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    if ts is None:
        ts = await compute_trust_score(db, entity_id)

    base_score = ts.score
    contextual_scores = ts.contextual_scores or {}
    ctx_score = contextual_scores.get(context)

    if ctx_score is None:
        return {
            "score": base_score,
            "base_score": base_score,
            "contextual_score": None,
        }

    blended = round(
        CONTEXT_BLEND_BASE_WEIGHT * base_score
        + CONTEXT_BLEND_CONTEXTUAL_WEIGHT * ctx_score,
        4,
    )
    return {
        "score": blended,
        "base_score": base_score,
        "contextual_score": ctx_score,
    }


_TRUST_MILESTONES = [
    (0.25, "Bronze", "Your trust score reached 0.25 — Bronze tier!"),
    (0.50, "Silver", "Your trust score reached 0.50 — Silver tier!"),
    (0.75, "Gold", "Your trust score reached 0.75 — Gold tier!"),
]


async def _check_trust_milestones(
    db: AsyncSession,
    entity_id: uuid.UUID,
    old_score: float,
    new_score: float,
) -> None:
    """Create notification when crossing trust milestones upward."""
    from src.models import Notification

    for threshold, tier, message in _TRUST_MILESTONES:
        if old_score < threshold <= new_score:
            notif = Notification(
                id=uuid.uuid4(),
                entity_id=entity_id,
                kind="trust_milestone",
                title=f"Trust Milestone: {tier}",
                body=message,
                reference_id=str(entity_id),
            )
            db.add(notif)
    await db.flush()


# Anomaly thresholds: flag when single-computation delta exceeds these
_ANOMALY_THRESHOLD_HIGH = 0.25  # immediate concern
_ANOMALY_THRESHOLD_MEDIUM = 0.15  # worth investigating


async def _check_trust_anomaly(
    db: AsyncSession,
    entity_id: uuid.UUID,
    old_score: float,
    new_score: float,
) -> None:
    """Create an anomaly alert when trust score changes too rapidly."""
    delta = abs(new_score - old_score)
    if delta < _ANOMALY_THRESHOLD_MEDIUM:
        return

    from src.models import AnomalyAlert

    severity = "high" if delta >= _ANOMALY_THRESHOLD_HIGH else "medium"
    # Use delta / threshold as a rough z-score proxy
    z = round(delta / _ANOMALY_THRESHOLD_MEDIUM, 2)

    alert = AnomalyAlert(
        id=uuid.uuid4(),
        entity_id=entity_id,
        alert_type="trust_velocity",
        severity=severity,
        z_score=z,
        details={
            "old_score": round(old_score, 4),
            "new_score": round(new_score, 4),
            "delta": round(delta, 4),
            "direction": "up" if new_score > old_score else "down",
        },
    )
    db.add(alert)
    await db.flush()


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
    external = await _external_reputation_factor(db, entity_id)

    score = (
        VERIFICATION_WEIGHT * verification
        + AGE_WEIGHT * age
        + ACTIVITY_WEIGHT * activity
        + REPUTATION_WEIGHT * reputation
        + COMMUNITY_WEIGHT * community
        + EXTERNAL_WEIGHT * external
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
        "external_reputation": round(external, 4),
    }

    # Compute primary_context from attestation frequency
    _update_primary_context(entity, contextual_scores)

    # Upsert trust score
    existing = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    old_score = existing.score if existing else 0.0
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

    # Record history snapshot
    history = TrustScoreHistory(
        id=uuid.uuid4(),
        entity_id=entity_id,
        score=round(score, 4),
        components=components,
        recorded_at=datetime.now(timezone.utc),
    )
    db.add(history)
    await db.flush()

    await db.refresh(trust_score)

    # Invalidate trust gate cache so new score takes effect immediately
    try:
        from src.cache import invalidate
        await invalidate(f"trust_gate:{entity_id}")
    except Exception:
        pass  # Best-effort

    # WebSocket push: real-time trust score update to connected clients
    try:
        from src.ws import manager

        await manager.send_to_entity(str(entity_id), "trust", {
            "type": "trust_updated",
            "score": trust_score.score,
            "components": components,
        })
    except Exception:
        pass  # Best-effort

    # Trust milestone notifications (0.25, 0.50, 0.75)
    try:
        await _check_trust_milestones(db, entity_id, old_score, trust_score.score)
    except Exception:
        pass  # Best-effort

    # Anomaly detection: flag rapid trust score changes
    try:
        await _check_trust_anomaly(db, entity_id, old_score, trust_score.score)
    except Exception:
        pass  # Best-effort

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


async def refresh_attestation_weights(db: AsyncSession) -> int:
    """Re-weight attestations based on current attester trust scores.

    When an attester's trust score changes, their past attestations still
    carry the old weight.  This function refreshes all attestation weights
    to match each attester's current score.
    """
    # Fetch all attestations with their attester's current trust score
    result = await db.execute(
        select(TrustAttestation, TrustScore.score)
        .outerjoin(
            TrustScore,
            TrustAttestation.attester_entity_id == TrustScore.entity_id,
        )
    )
    rows = result.all()
    updated = 0
    for att, current_score in rows:
        new_weight = current_score if current_score is not None else 0.5
        if att.weight != new_weight:
            att.weight = new_weight
            updated += 1

    if updated:
        await db.flush()
    return updated


def _compute_community_from_attestations(
    attestations: list[TrustAttestation],
) -> tuple[float, dict[str, float]]:
    """Compute community factor from pre-loaded attestations (no DB query).

    Same logic as ``_community_factor`` but operates on a pre-fetched list
    instead of querying the database per entity.
    """
    if not attestations:
        return 0.0, {}

    now = datetime.now(timezone.utc)
    cutoff_90 = now - timedelta(days=90)
    cutoff_180 = now - timedelta(days=180)

    # Apply gaming cap: group by attester, keep max ATTESTATION_MAX_PER_ATTESTER
    attester_counts: dict[uuid.UUID, int] = {}
    filtered: list[TrustAttestation] = []
    for att in attestations:
        count = attester_counts.get(att.attester_entity_id, 0)
        if count < ATTESTATION_MAX_PER_ATTESTER:
            filtered.append(att)
            attester_counts[att.attester_entity_id] = count + 1

    if not filtered:
        return 0.0, {}

    total_weight = 0.0
    weighted_sum = 0.0
    context_weights: dict[str, float] = {}
    context_sums: dict[str, float] = {}

    for att in filtered:
        w = att.weight or 0.5
        created = att.created_at
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        if created and created < cutoff_180:
            w *= ATTESTATION_DECAY_180_DAYS
        elif created and created < cutoff_90:
            w *= ATTESTATION_DECAY_90_DAYS

        weighted_sum += w
        total_weight += 1.0

        ctx = att.context
        if ctx:
            context_sums[ctx] = context_sums.get(ctx, 0.0) + w
            context_weights[ctx] = context_weights.get(ctx, 0.0) + 1.0

    overall = weighted_sum / total_weight if total_weight > 0 else 0.0
    overall = min(overall, 1.0)

    contextual_scores: dict[str, float] = {}
    for ctx in context_sums:
        ctx_score = context_sums[ctx] / context_weights[ctx]
        contextual_scores[ctx] = round(min(ctx_score, 1.0), 4)

    return overall, contextual_scores


def _compute_external_from_accounts(
    accounts: list[LinkedAccount],
) -> float:
    """Compute external reputation factor from pre-loaded linked accounts.

    Same logic as ``_external_reputation_factor`` but operates on a
    pre-fetched list instead of querying the database per entity.
    """
    from src.external_reputation import VERIFICATION_WEIGHTS

    if not accounts:
        return 0.0

    total = 0.0
    count = 0
    for acct in accounts:
        weight = VERIFICATION_WEIGHTS.get(acct.verification_status, 0.0)
        if weight > 0 and acct.reputation_score is not None:
            total += acct.reputation_score * weight
            count += 1

    return total / count if count > 0 else 0.0


# Default chunk size for batch_recompute; callers may override.
BATCH_CHUNK_SIZE = 1000


async def batch_recompute(
    db: AsyncSession, chunk_size: int = BATCH_CHUNK_SIZE,
) -> int:
    """Recompute trust scores for all active entities.

    Processes entities in chunks of *chunk_size* (default 1000) to bound
    memory usage at scale (tested target: 700K+ entities).  Each chunk
    bulk-loads attestations, linked accounts, and existing trust scores
    to avoid N+1 query patterns, then flushes and expunges objects to
    release memory before moving to the next chunk.

    Also refreshes attestation weights before recomputing.
    """
    # Step 0: refresh attestation weights so community scores use current data
    await refresh_attestation_weights(db)

    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)

    # Count total active entities for logging
    # Skip bulk-imported Moltbook entities — they have static trust scores
    # and no activity to decay. Recomputing 700K+ static scores wastes resources.
    _recompute_filter = (
        Entity.is_active.is_(True),
        Entity.framework_source != "moltbook",
    )
    total_entities = await db.scalar(
        select(func.count())
        .select_from(Entity)
        .where(*_recompute_filter)
    ) or 0
    if total_entities == 0:
        return 0

    total_chunks = (total_entities + chunk_size - 1) // chunk_size
    processed = 0
    chunk_num = 0

    logger.info(
        "Batch recompute starting: %d entities in ~%d chunks of %d",
        total_entities, total_chunks, chunk_size,
    )

    # Keyset pagination: order by id, fetch chunk_size at a time
    last_id: uuid.UUID | None = None

    while True:
        chunk_num += 1

        # Fetch one chunk of entities via keyset pagination
        q = (
            select(Entity)
            .where(*_recompute_filter)
            .order_by(Entity.id)
            .limit(chunk_size)
        )
        if last_id is not None:
            q = q.where(Entity.id > last_id)

        entities_result = await db.execute(q)
        entities = entities_result.scalars().all()
        if not entities:
            break

        entity_ids = [e.id for e in entities]
        entity_map = {e.id: e for e in entities}
        last_id = entity_ids[-1]

        logger.info(
            "Processing chunk %d/%d (%d/%d entities)",
            chunk_num, total_chunks, processed + len(entity_ids), total_entities,
        )

        # -- Bulk queries for this chunk --

        # Bulk query 1: post counts per entity (last 30 days)
        post_result = await db.execute(
            select(Post.author_entity_id, func.count())
            .where(
                Post.author_entity_id.in_(entity_ids),
                Post.created_at >= cutoff_30d,
            )
            .group_by(Post.author_entity_id)
        )
        post_counts = dict(post_result.all())

        # Bulk query 2: vote counts per entity (last 30 days)
        vote_result = await db.execute(
            select(Vote.entity_id, func.count())
            .where(
                Vote.entity_id.in_(entity_ids),
                Vote.created_at >= cutoff_30d,
            )
            .group_by(Vote.entity_id)
        )
        vote_counts = dict(vote_result.all())

        # Bulk query 3: review averages per entity
        review_result = await db.execute(
            select(Review.target_entity_id, func.avg(Review.rating))
            .where(Review.target_entity_id.in_(entity_ids))
            .group_by(Review.target_entity_id)
        )
        review_avgs = dict(review_result.all())

        # Bulk query 4: endorsement counts per entity
        endorse_result = await db.execute(
            select(CapabilityEndorsement.agent_entity_id, func.count())
            .where(CapabilityEndorsement.agent_entity_id.in_(entity_ids))
            .group_by(CapabilityEndorsement.agent_entity_id)
        )
        endorse_counts = dict(endorse_result.all())

        # Bulk query 5: all attestations for this chunk (replaces per-entity query)
        att_result = await db.execute(
            select(TrustAttestation).where(
                TrustAttestation.target_entity_id.in_(entity_ids),
            )
        )
        all_attestations = att_result.scalars().all()
        att_map: dict[uuid.UUID, list[TrustAttestation]] = defaultdict(list)
        for att in all_attestations:
            att_map[att.target_entity_id].append(att)

        # Bulk query 6: all linked accounts for this chunk (replaces per-entity query)
        acct_result = await db.execute(
            select(LinkedAccount).where(
                LinkedAccount.entity_id.in_(entity_ids),
            )
        )
        all_accounts = acct_result.scalars().all()
        acct_map: dict[uuid.UUID, list[LinkedAccount]] = defaultdict(list)
        for acct in all_accounts:
            acct_map[acct.entity_id].append(acct)

        # Bulk query 7: existing trust scores for this chunk (replaces per-entity SELECT)
        ts_result = await db.execute(
            select(TrustScore).where(TrustScore.entity_id.in_(entity_ids))
        )
        existing_scores = {ts.entity_id: ts for ts in ts_result.scalars().all()}

        # -- Compute scores in-memory --

        now_ts = datetime.now(timezone.utc)
        upsert_rows: list[dict] = []
        history_rows: list[dict] = []

        for eid in entity_ids:
            entity = entity_map[eid]
            verification = _verification_factor(entity)
            age = _age_factor(entity)

            # Activity factor from pre-loaded data
            total_activity = post_counts.get(eid, 0) + vote_counts.get(eid, 0)
            activity = (
                min(math.log(total_activity + 1) / math.log(ACTIVITY_LOG_CAP), 1.0)
                if total_activity > 0
                else 0.0
            )

            # Reputation from pre-loaded data
            avg_rating_raw = review_avgs.get(eid)
            review_score = float(avg_rating_raw) / 5.0 if avg_rating_raw else 0.0
            ec = endorse_counts.get(eid, 0)
            endorsement_score = (
                min(math.log(ec + 1) / math.log(20), 1.0) if ec > 0 else 0.0
            )
            if avg_rating_raw is not None and ec > 0:
                reputation = 0.6 * review_score + 0.4 * endorsement_score
            elif avg_rating_raw is not None:
                reputation = review_score
            elif ec > 0:
                reputation = endorsement_score
            else:
                reputation = 0.0

            # Community factor from pre-loaded attestations (no per-entity query)
            community, contextual_scores = _compute_community_from_attestations(
                att_map.get(eid, []),
            )

            # External reputation from pre-loaded linked accounts (no per-entity query)
            external = _compute_external_from_accounts(acct_map.get(eid, []))

            score = (
                VERIFICATION_WEIGHT * verification
                + AGE_WEIGHT * age
                + ACTIVITY_WEIGHT * activity
                + REPUTATION_WEIGHT * reputation
                + COMMUNITY_WEIGHT * community
                + EXTERNAL_WEIGHT * external
            )

            framework_modifier = getattr(entity, "framework_trust_modifier", None)
            if framework_modifier is not None and framework_modifier != 1.0:
                score *= framework_modifier

            components = {
                "verification": round(verification, 4),
                "age": round(age, 4),
                "activity": round(activity, 4),
                "reputation": round(reputation, 4),
                "community": round(community, 4),
                "external_reputation": round(external, 4),
            }

            # Update primary_context from attestation frequency
            _update_primary_context(entity, contextual_scores)

            rounded_score = round(score, 4)

            # Collect upsert row for batch INSERT ... ON CONFLICT UPDATE
            existing_ts = existing_scores.get(eid)
            upsert_rows.append({
                "id": existing_ts.id if existing_ts else uuid.uuid4(),
                "entity_id": eid,
                "score": rounded_score,
                "components": components,
                "contextual_scores": contextual_scores,
                "computed_at": now_ts,
            })

            # Collect history row for batch insert
            history_rows.append({
                "id": uuid.uuid4(),
                "entity_id": eid,
                "score": rounded_score,
                "components": components,
                "recorded_at": now_ts,
            })

            # Anomaly detection for batch recompute
            old_score = existing_ts.score if existing_ts else 0.0
            try:
                await _check_trust_anomaly(db, eid, old_score, rounded_score)
            except Exception:
                pass

        # Batch upsert trust scores: INSERT ... ON CONFLICT(entity_id) DO UPDATE
        if upsert_rows:
            stmt = pg_insert(TrustScore).values(upsert_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["entity_id"],
                set_={
                    "score": stmt.excluded.score,
                    "components": stmt.excluded.components,
                    "contextual_scores": stmt.excluded.contextual_scores,
                    "computed_at": stmt.excluded.computed_at,
                },
            )
            await db.execute(stmt)

        # Batch insert history rows
        if history_rows:
            await db.execute(
                pg_insert(TrustScoreHistory).values(history_rows)
            )

        await db.flush()
        processed += len(entity_ids)

        # Expunge loaded objects from session to release memory before next chunk.
        # expire() keeps objects in the identity map; expunge() fully detaches them
        # so the garbage collector can reclaim memory — critical at 700K+ entities.
        for entity in entities:
            db.expunge(entity)
        for ts in existing_scores.values():
            db.expunge(ts)
        for att in all_attestations:
            db.expunge(att)
        for acct in all_accounts:
            db.expunge(acct)

        # Clear local references to allow GC within this iteration
        del entities, entity_ids, entity_map
        del post_counts, vote_counts, review_avgs, endorse_counts
        del att_map, all_attestations, acct_map, all_accounts
        del existing_scores, upsert_rows, history_rows

    logger.info(
        "Batch recompute complete: %d entities processed in %d chunks",
        processed, chunk_num,
    )
    return processed
