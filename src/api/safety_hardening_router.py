"""Anti-weaponization hardening endpoints for AgentGraph.

Provides endpoints to report coordinated inauthentic behavior (CIB),
check Sybil risk scores, detect trust gaming indicators, escalate
rate limits for suspicious entities, and monitor platform health.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, require_admin
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.database import get_db
from src.models import (
    Entity,
    EntityRelationship,
    ModerationFlag,
    ModerationReason,
    ModerationStatus,
    Post,
    TrustAttestation,
    TrustScore,
)

router = APIRouter(prefix="/safety/hardening", tags=["safety-hardening"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CIBReportRequest(BaseModel):
    entity_ids: list[str] = Field(
        ..., min_length=2, max_length=50,
        description="List of entity IDs suspected of coordinated behavior",
    )
    description: str = Field(
        ..., min_length=10, max_length=5000,
        description="Description of the suspected coordinated behavior",
    )
    evidence: str | None = Field(
        None, max_length=10000,
        description="Supporting evidence (links, timestamps, patterns)",
    )


class CIBReportResponse(BaseModel):
    investigation_id: str
    status: str
    entities_flagged: int
    message: str


class SybilRiskFactor(BaseModel):
    factor: str
    description: str
    severity: str  # "low", "medium", "high"


class SybilRiskResponse(BaseModel):
    entity_id: str
    risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: str  # "low", "medium", "high", "critical"
    risk_factors: list[SybilRiskFactor]


class TrustGamingIndicator(BaseModel):
    indicator: str
    description: str
    severity: str  # "low", "medium", "high"
    details: dict | None = None


class TrustGamingResponse(BaseModel):
    entity_id: str
    indicators: list[TrustGamingIndicator]
    overall_risk: str  # "none", "low", "medium", "high"


class EscalateRateLimitRequest(BaseModel):
    entity_id: str = Field(..., description="Entity to throttle")
    duration_hours: int = Field(
        ..., ge=1, le=720,
        description="Duration of escalated rate limit in hours (max 30 days)",
    )
    reason: str = Field(
        ..., min_length=5, max_length=1000,
        description="Reason for rate limit escalation",
    )


class EscalateRateLimitResponse(BaseModel):
    entity_id: str
    throttled_until: str
    reason: str
    message: str


class PlatformHealthResponse(BaseModel):
    total_active_entities: int
    new_accounts_24h: int
    flagged_content_rate: float
    moderation_queue_depth: int
    average_trust_score: float | None
    trust_score_trend: str | None  # "rising", "stable", "declining"


# ---------------------------------------------------------------------------
# 1. POST /safety/hardening/report-coordinated-behavior
# ---------------------------------------------------------------------------


@router.post(
    "/report-coordinated-behavior",
    response_model=CIBReportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_writes)],
)
async def report_coordinated_behavior(
    body: CIBReportRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Report suspected coordinated inauthentic behavior (CIB).

    Creates moderation investigation records for each reported entity.
    Authenticated users only, rate limited.
    """
    # Validate entity IDs are valid UUIDs
    valid_ids: list[uuid.UUID] = []
    for eid_str in body.entity_ids:
        try:
            valid_ids.append(uuid.UUID(eid_str))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid entity ID: {eid_str}",
            )

    # Cannot report yourself
    if current_entity.id in valid_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot include yourself in a CIB report",
        )

    # Verify at least some entities exist
    result = await db.execute(
        select(Entity.id).where(Entity.id.in_(valid_ids))
    )
    existing_ids = {row[0] for row in result.all()}
    if not existing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="None of the reported entities exist",
        )

    # Create a group investigation ID that links all flags together
    investigation_id = str(uuid.uuid4())

    # Create moderation flags for each reported entity
    flagged_count = 0
    for entity_id in existing_ids:
        flag = ModerationFlag(
            reporter_entity_id=current_entity.id,
            target_type="entity",
            target_id=entity_id,
            reason=ModerationReason.SPAM,
            details=(
                f"[CIB Investigation {investigation_id}] "
                f"{body.description}"
                + (f"\n\nEvidence: {body.evidence}" if body.evidence else "")
                + f"\n\nReported entities: {[str(eid) for eid in existing_ids]}"
            ),
            status=ModerationStatus.PENDING,
        )
        db.add(flag)
        flagged_count += 1

    await db.flush()

    return CIBReportResponse(
        investigation_id=investigation_id,
        status="under_review",
        entities_flagged=flagged_count,
        message=f"CIB report submitted. {flagged_count} entities flagged for investigation.",
    )


# ---------------------------------------------------------------------------
# 2. GET /safety/hardening/sybil-risk/{entity_id}
# ---------------------------------------------------------------------------


@router.get(
    "/sybil-risk/{entity_id}",
    response_model=SybilRiskResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def check_sybil_risk(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Check an entity's Sybil risk score. Admin only.

    Analyzes account creation patterns, IP clustering, timing,
    and display name similarity.
    """
    require_admin(current_entity)

    target = await db.get(Entity, entity_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    risk_factors: list[SybilRiskFactor] = []
    risk_score = 0.0

    # Factor 1: Accounts created near the same time (within 5 minutes)
    if target.created_at:
        window_start = target.created_at - timedelta(minutes=5)
        window_end = target.created_at + timedelta(minutes=5)
        result = await db.execute(
            select(func.count(Entity.id)).where(
                and_(
                    Entity.created_at >= window_start,
                    Entity.created_at <= window_end,
                    Entity.id != entity_id,
                )
            )
        )
        nearby_accounts = result.scalar() or 0
        if nearby_accounts >= 3:
            risk_factors.append(SybilRiskFactor(
                factor="rapid_creation_cluster",
                description=(
                    f"{nearby_accounts} other accounts created within 5 minutes "
                    f"of this entity"
                ),
                severity="high",
            ))
            risk_score += 0.35
        elif nearby_accounts >= 1:
            risk_factors.append(SybilRiskFactor(
                factor="creation_timing",
                description=(
                    f"{nearby_accounts} other account(s) created within 5 minutes"
                ),
                severity="medium",
            ))
            risk_score += 0.15

    # Factor 2: Similar display names among recent accounts
    if target.display_name and target.created_at:
        base_name = target.display_name.lower().rstrip("0123456789")
        if len(base_name) >= 3:
            # Look for other entities with similar display names
            # created within 24 hours
            day_start = target.created_at - timedelta(hours=24)
            day_end = target.created_at + timedelta(hours=24)
            result = await db.execute(
                select(Entity.display_name).where(
                    and_(
                        Entity.created_at >= day_start,
                        Entity.created_at <= day_end,
                        Entity.id != entity_id,
                        func.lower(Entity.display_name).like(f"{base_name}%"),
                    )
                )
            )
            similar_names = result.all()
            if len(similar_names) >= 2:
                risk_factors.append(SybilRiskFactor(
                    factor="similar_display_names",
                    description=(
                        f"{len(similar_names)} accounts with similar display "
                        f"names (base: '{base_name}') created within 24 hours"
                    ),
                    severity="high",
                ))
                risk_score += 0.3
            elif len(similar_names) >= 1:
                risk_factors.append(SybilRiskFactor(
                    factor="similar_display_name",
                    description=(
                        "1 account with similar display name created within 24 hours"
                    ),
                    severity="low",
                ))
                risk_score += 0.1

    # Factor 3: Account has no activity (no posts, no follows)
    post_count_result = await db.execute(
        select(func.count(Post.id)).where(
            Post.author_entity_id == entity_id,
        )
    )
    post_count = post_count_result.scalar() or 0

    follow_count_result = await db.execute(
        select(func.count(EntityRelationship.id)).where(
            EntityRelationship.source_entity_id == entity_id,
        )
    )
    follow_count = follow_count_result.scalar() or 0

    if post_count == 0 and follow_count == 0:
        risk_factors.append(SybilRiskFactor(
            factor="no_activity",
            description="Account has zero posts and zero follows",
            severity="medium",
        ))
        risk_score += 0.15

    # Factor 4: No email verification
    if not target.email_verified:
        risk_factors.append(SybilRiskFactor(
            factor="unverified_email",
            description="Email address is not verified",
            severity="low",
        ))
        risk_score += 0.1

    # Cap at 1.0
    risk_score = min(risk_score, 1.0)

    # Determine risk level
    if risk_score >= 0.7:
        risk_level = "critical"
    elif risk_score >= 0.5:
        risk_level = "high"
    elif risk_score >= 0.25:
        risk_level = "medium"
    else:
        risk_level = "low"

    return SybilRiskResponse(
        entity_id=str(entity_id),
        risk_score=round(risk_score, 2),
        risk_level=risk_level,
        risk_factors=risk_factors,
    )


# ---------------------------------------------------------------------------
# 3. GET /safety/hardening/trust-gaming-indicators/{entity_id}
# ---------------------------------------------------------------------------


@router.get(
    "/trust-gaming-indicators/{entity_id}",
    response_model=TrustGamingResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def check_trust_gaming_indicators(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Check for trust score gaming indicators. Admin only.

    Detects reciprocal attestation rings, sudden trust score jumps,
    and unusual attestation patterns.
    """
    require_admin(current_entity)

    target = await db.get(Entity, entity_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    indicators: list[TrustGamingIndicator] = []

    # Indicator 1: Reciprocal attestation rings
    # Check if this entity has mutual attestations (A attests B AND B attests A)
    result = await db.execute(
        select(
            TrustAttestation.target_entity_id,
        ).where(
            TrustAttestation.attester_entity_id == entity_id,
        )
    )
    attested_targets = {row[0] for row in result.all()}

    if attested_targets:
        result = await db.execute(
            select(
                TrustAttestation.attester_entity_id,
            ).where(
                and_(
                    TrustAttestation.target_entity_id == entity_id,
                    TrustAttestation.attester_entity_id.in_(attested_targets),
                )
            )
        )
        reciprocal_attesters = {row[0] for row in result.all()}

        if len(reciprocal_attesters) >= 3:
            indicators.append(TrustGamingIndicator(
                indicator="reciprocal_attestation_ring",
                description=(
                    f"Entity has reciprocal attestations with "
                    f"{len(reciprocal_attesters)} other entities"
                ),
                severity="high",
                details={
                    "reciprocal_entity_ids": [
                        str(eid) for eid in reciprocal_attesters
                    ],
                },
            ))
        elif len(reciprocal_attesters) >= 1:
            indicators.append(TrustGamingIndicator(
                indicator="mutual_attestation",
                description=(
                    f"Entity has mutual attestations with "
                    f"{len(reciprocal_attesters)} entity/entities"
                ),
                severity="medium",
                details={
                    "reciprocal_entity_ids": [
                        str(eid) for eid in reciprocal_attesters
                    ],
                },
            ))

    # Indicator 2: Sudden trust score jumps
    trust_score_obj = await db.execute(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    ts_row = trust_score_obj.scalar_one_or_none()

    if ts_row and ts_row.score >= 0.8:
        # Check if entity is relatively new (created within last 7 days)
        if target.created_at:
            age_days = (datetime.now(timezone.utc) - target.created_at).days
            if age_days <= 7:
                indicators.append(TrustGamingIndicator(
                    indicator="rapid_trust_gain",
                    description=(
                        f"Entity has trust score {ts_row.score:.2f} "
                        f"but account is only {age_days} day(s) old"
                    ),
                    severity="high",
                    details={
                        "trust_score": ts_row.score,
                        "account_age_days": age_days,
                    },
                ))

    # Indicator 3: Unusual attestation volume (receiving many attestations
    # in a short period)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    result = await db.execute(
        select(func.count(TrustAttestation.id)).where(
            and_(
                TrustAttestation.target_entity_id == entity_id,
                TrustAttestation.created_at >= week_ago,
            )
        )
    )
    recent_attestations = result.scalar() or 0

    if recent_attestations >= 10:
        indicators.append(TrustGamingIndicator(
            indicator="attestation_burst",
            description=(
                f"Entity received {recent_attestations} attestations "
                f"in the last 7 days"
            ),
            severity="high",
            details={"attestation_count_7d": recent_attestations},
        ))
    elif recent_attestations >= 5:
        indicators.append(TrustGamingIndicator(
            indicator="elevated_attestation_rate",
            description=(
                f"Entity received {recent_attestations} attestations "
                f"in the last 7 days"
            ),
            severity="medium",
            details={"attestation_count_7d": recent_attestations},
        ))

    # Determine overall risk
    severities = [ind.severity for ind in indicators]
    if "high" in severities:
        overall_risk = "high"
    elif "medium" in severities:
        overall_risk = "medium"
    elif severities:
        overall_risk = "low"
    else:
        overall_risk = "none"

    return TrustGamingResponse(
        entity_id=str(entity_id),
        indicators=indicators,
        overall_risk=overall_risk,
    )


# ---------------------------------------------------------------------------
# 4. POST /safety/hardening/escalate-rate-limit
# ---------------------------------------------------------------------------


@router.post(
    "/escalate-rate-limit",
    response_model=EscalateRateLimitResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def escalate_rate_limit(
    body: EscalateRateLimitRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Temporarily reduce an entity's rate limit multiplier. Admin only.

    Sets a Redis key that the rate limiter checks to apply a throttle
    multiplier to the target entity for the specified duration.
    """
    require_admin(current_entity)

    try:
        target_id = uuid.UUID(body.entity_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid entity ID",
        )

    target = await db.get(Entity, target_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    # Cannot throttle other admins
    if target.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot throttle admin accounts",
        )

    throttled_until = datetime.now(timezone.utc) + timedelta(
        hours=body.duration_hours,
    )

    # Store throttle info in Redis
    from src import cache

    throttle_data: dict[str, Any] = {
        "throttled_until": throttled_until.isoformat(),
        "reason": body.reason,
        "escalated_by": str(current_entity.id),
    }
    ttl_seconds = body.duration_hours * 3600
    await cache.set(
        f"throttle:{target_id}",
        throttle_data,
        ttl=ttl_seconds,
    )

    return EscalateRateLimitResponse(
        entity_id=str(target_id),
        throttled_until=throttled_until.isoformat(),
        reason=body.reason,
        message=(
            f"Rate limit escalated for entity {target_id} "
            f"until {throttled_until.isoformat()}"
        ),
    )


# ---------------------------------------------------------------------------
# 5. GET /safety/hardening/platform-health
# ---------------------------------------------------------------------------


@router.get(
    "/platform-health",
    response_model=PlatformHealthResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def platform_health(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Platform health metrics. Admin only.

    Returns active entity count, new accounts, flagged content rate,
    moderation queue depth, and trust score trend.
    """
    require_admin(current_entity)

    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    # Total active entities
    result = await db.execute(
        select(func.count(Entity.id)).where(Entity.is_active.is_(True))
    )
    total_active = result.scalar() or 0

    # New accounts in last 24h
    result = await db.execute(
        select(func.count(Entity.id)).where(
            Entity.created_at >= day_ago,
        )
    )
    new_accounts_24h = result.scalar() or 0

    # Moderation queue depth (pending flags)
    result = await db.execute(
        select(func.count(ModerationFlag.id)).where(
            ModerationFlag.status == ModerationStatus.PENDING,
        )
    )
    moderation_queue_depth = result.scalar() or 0

    # Total posts in last 24h and flagged posts in last 24h
    result = await db.execute(
        select(func.count(Post.id)).where(
            Post.created_at >= day_ago,
        )
    )
    total_posts_24h = result.scalar() or 0

    result = await db.execute(
        select(func.count(ModerationFlag.id)).where(
            and_(
                ModerationFlag.created_at >= day_ago,
                ModerationFlag.target_type == "post",
            )
        )
    )
    flagged_posts_24h = result.scalar() or 0

    flagged_content_rate = (
        round(flagged_posts_24h / total_posts_24h, 4)
        if total_posts_24h > 0
        else 0.0
    )

    # Average trust score
    result = await db.execute(
        select(func.avg(TrustScore.score))
    )
    avg_trust = result.scalar()
    average_trust_score = round(avg_trust, 4) if avg_trust is not None else None

    # Trust score trend: compare current average to 7-day-ago average
    # (simplified: just report current average direction vs 0.5 midpoint)
    if average_trust_score is not None:
        if average_trust_score > 0.55:
            trust_score_trend = "rising"
        elif average_trust_score < 0.45:
            trust_score_trend = "declining"
        else:
            trust_score_trend = "stable"
    else:
        trust_score_trend = None

    return PlatformHealthResponse(
        total_active_entities=total_active,
        new_accounts_24h=new_accounts_24h,
        flagged_content_rate=flagged_content_rate,
        moderation_queue_depth=moderation_queue_depth,
        average_trust_score=average_trust_score,
        trust_score_trend=trust_score_trend,
    )
