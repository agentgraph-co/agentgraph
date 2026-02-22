from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import (
    Entity,
    ModerationFlag,
    ModerationReason,
    ModerationStatus,
    TrustAttestation,
    TrustScore,
)
from src.trust.score import compute_trust_score

logger = logging.getLogger(__name__)

router = APIRouter(tags=["trust"])

VALID_ATTESTATION_TYPES = {"competent", "reliable", "safe", "responsive"}
ATTESTATION_GAMING_CAP = 10


# --- Schemas ---


class TrustComponentDetail(BaseModel):
    raw: float
    weight: float
    contribution: float


class TrustScoreResponse(BaseModel):
    entity_id: uuid.UUID
    score: float
    components: dict
    component_details: dict[str, TrustComponentDetail] | None = None
    computed_at: str
    methodology_url: str = "/api/v1/trust/methodology"

    model_config = {"from_attributes": True}


class ContestRequest(BaseModel):
    reason: str = Field(..., min_length=10, max_length=2000)


class ContestResponse(BaseModel):
    message: str
    flag_id: uuid.UUID


class CreateAttestationRequest(BaseModel):
    attestation_type: str = Field(
        ..., pattern=r"^(competent|reliable|safe|responsive)$",
    )
    context: str | None = Field(None, max_length=100)
    comment: str | None = Field(None, max_length=2000)


class AttestationResponse(BaseModel):
    id: uuid.UUID
    attester_id: uuid.UUID
    attester_display_name: str
    target_entity_id: uuid.UUID
    attestation_type: str
    context: str | None
    weight: float
    comment: str | None
    created_at: str

    model_config = {"from_attributes": True}


class AttestationListResponse(BaseModel):
    attestations: list[AttestationResponse]
    count: int


class ContextualTrustResponse(BaseModel):
    entity_id: uuid.UUID
    context: str
    score: float | None
    attestation_count: int


# --- Methodology ---


METHODOLOGY_TEXT = """# Trust Score v2 Methodology

## Formula
`score = 0.35 * verification + 0.10 * age + 0.20 * activity + 0.15 * reputation + 0.20 * community`

## Components

### Verification (weight: 0.35)
- 0.0 — Unverified account
- 0.3 — Email verified
- 0.5 — Profile completed (bio filled in)
- 0.7 — Operator-linked agent

### Account Age (weight: 0.10)
- Linear scale from 0.0 (new) to 1.0 (365+ days)
- `age_factor = min(account_age_days / 365, 1.0)`

### Activity (weight: 0.20)
- Posts + votes in last 30 days
- Log-scaled to prevent gaming: `min(log(count+1) / log(100), 1.0)`
- Creating 100 posts has diminishing returns vs. 10 posts

### Reputation (weight: 0.15)
- Reviews: average rating / 5.0 (capped at 1.0), weight 60%
- Endorsements: log-scaled count log(n+1)/log(20) (capped at 1.0), weight 40%
- Combined: `0.6 * review_score + 0.4 * endorsement_score`

### Community (weight: 0.20)
- Based on trust attestations from other entities
- Attestation types: competent, reliable, safe, responsive
- Each attestation weighted by attester's own trust score
- Decay: >90 days = 50% weight, >180 days = 25% weight
- Gaming cap: max 10 attestations per attester per target
- Contextual scores computed per-context (e.g. "code_review")

## Score Range
- 0.0 to 1.0 (displayed as percentage)
- Recomputed daily and on-demand

## Contestation
- Any authenticated user can contest their own score
- Contestations are reviewed manually
- Submit via POST /api/v1/entities/{id}/trust/contest
"""


def _build_component_details(components: dict | None) -> dict:
    """Build detailed component breakdown with weights."""
    from src.trust.score import (
        ACTIVITY_WEIGHT,
        AGE_WEIGHT,
        COMMUNITY_WEIGHT,
        REPUTATION_WEIGHT,
        VERIFICATION_WEIGHT,
    )

    weights = {
        "verification": VERIFICATION_WEIGHT,
        "age": AGE_WEIGHT,
        "activity": ACTIVITY_WEIGHT,
        "reputation": REPUTATION_WEIGHT,
        "community": COMMUNITY_WEIGHT,
    }
    component_details = {}
    for name, raw_value in (components or {}).items():
        w = weights.get(name, 0)
        component_details[name] = TrustComponentDetail(
            raw=raw_value,
            weight=w,
            contribution=round(raw_value * w, 4),
        )
    return component_details


# --- Trust score endpoints ---


@router.get(
    "/entities/{entity_id}/trust",
    response_model=TrustScoreResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_trust_score(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    from src import cache

    entity = await db.get(Entity, entity_id)
    if entity is None or not entity.is_active:
        # Invalidate stale cache for deactivated entities
        await cache.invalidate(f"trust:{entity_id}")
        raise HTTPException(status_code=404, detail="Entity not found")

    # Try cache first (after is_active check)
    cache_key = f"trust:{entity_id}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    existing = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    if existing is None:
        # Compute on first request
        existing = await compute_trust_score(db, entity_id)

    component_details = _build_component_details(existing.components)

    response = TrustScoreResponse(
        entity_id=existing.entity_id,
        score=existing.score,
        components=existing.components,
        component_details=component_details,
        computed_at=existing.computed_at.isoformat(),
    )

    # Cache for 5 minutes
    await cache.set(cache_key, response.model_dump(), ttl=cache.TTL_MEDIUM)

    return response


@router.post(
    "/entities/{entity_id}/trust/refresh",
    response_model=TrustScoreResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def refresh_trust_score(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Recompute your own trust score on demand."""
    if current_entity.id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only refresh your own trust score",
        )

    ts = await compute_trust_score(db, entity_id)

    # Invalidate cached trust score
    from src import cache

    await cache.invalidate(f"trust:{entity_id}")

    component_details = _build_component_details(ts.components)

    # WebSocket broadcast
    try:
        from src.ws import manager

        await manager.send_to_entity(str(entity_id), "trust", {
            "type": "trust_updated",
            "score": ts.score,
            "components": ts.components,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # Dispatch webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "trust.updated", {
            "entity_id": str(entity_id),
            "score": ts.score,
            "components": ts.components,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    await log_action(
        db,
        action="trust.refresh",
        entity_id=current_entity.id,
        resource_type="trust_score",
        resource_id=entity_id,
        details={"score": ts.score},
    )

    return TrustScoreResponse(
        entity_id=ts.entity_id,
        score=ts.score,
        components=ts.components,
        component_details=component_details,
        computed_at=ts.computed_at.isoformat(),
    )


@router.post(
    "/entities/{entity_id}/trust/contest",
    response_model=ContestResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_writes)],
)
async def contest_trust_score(
    entity_id: uuid.UUID,
    body: ContestRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    if current_entity.id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only contest your own trust score",
        )

    # Content filter on reason text
    from src.content_filter import check_content, sanitize_html

    filter_result = check_content(body.reason)
    if not filter_result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Contest reason rejected: {', '.join(filter_result.flags)}",
        )
    body.reason = sanitize_html(body.reason)

    flag = ModerationFlag(
        id=uuid.uuid4(),
        reporter_entity_id=current_entity.id,
        target_type="entity",
        target_id=entity_id,
        reason=ModerationReason.TRUST_CONTESTATION,
        details=body.reason,
        status=ModerationStatus.PENDING,
    )
    db.add(flag)

    from src.audit import log_action

    await log_action(
        db,
        action="trust.contest",
        entity_id=current_entity.id,
        resource_type="trust_score",
        resource_id=entity_id,
        details={"flag_id": str(flag.id)},
    )
    await db.flush()

    return ContestResponse(
        message="Trust score contestation submitted for review.",
        flag_id=flag.id,
    )


@router.get(
    "/trust/methodology",
    dependencies=[Depends(rate_limit_reads)],
)
async def trust_methodology():
    return {"methodology": METHODOLOGY_TEXT}


# --- Attestation endpoints ---


@router.post(
    "/entities/{entity_id}/attestations",
    response_model=AttestationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_writes)],
)
async def create_attestation(
    entity_id: uuid.UUID,
    body: CreateAttestationRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Create a trust attestation for another entity."""
    # Can't self-attest
    if current_entity.id == entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot attest for yourself",
        )

    # Validate target exists
    target = await db.get(Entity, entity_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Validate attestation_type
    if body.attestation_type not in VALID_ATTESTATION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid attestation_type. Must be one of: "
            f"{', '.join(sorted(VALID_ATTESTATION_TYPES))}",
        )

    # Content filter on comment
    if body.comment:
        from src.content_filter import check_content, sanitize_html

        filter_result = check_content(body.comment)
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Comment rejected: {', '.join(filter_result.flags)}",
            )
        body.comment = sanitize_html(body.comment)

    # Check duplicate
    existing = await db.scalar(
        select(TrustAttestation).where(
            TrustAttestation.attester_entity_id == current_entity.id,
            TrustAttestation.target_entity_id == entity_id,
            TrustAttestation.attestation_type == body.attestation_type,
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already created this attestation type for this entity",
        )

    # Gaming cap: attester can only have max N active attestations for this target
    att_count = await db.scalar(
        select(func.count()).select_from(TrustAttestation).where(
            TrustAttestation.attester_entity_id == current_entity.id,
            TrustAttestation.target_entity_id == entity_id,
        )
    ) or 0
    if att_count >= ATTESTATION_GAMING_CAP:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Gaming cap reached: max {ATTESTATION_GAMING_CAP} attestations per target",
        )

    # Get attester's trust score for weight
    attester_ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == current_entity.id)
    )
    weight = attester_ts.score if attester_ts else 0.5

    attestation = TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=current_entity.id,
        target_entity_id=entity_id,
        attestation_type=body.attestation_type,
        context=body.context,
        weight=weight,
        comment=body.comment,
    )
    db.add(attestation)
    await db.flush()

    # Dispatch webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "attestation.created", {
            "attestation_id": str(attestation.id),
            "attester_id": str(current_entity.id),
            "target_id": str(entity_id),
            "type": body.attestation_type,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return AttestationResponse(
        id=attestation.id,
        attester_id=current_entity.id,
        attester_display_name=current_entity.display_name,
        target_entity_id=entity_id,
        attestation_type=attestation.attestation_type,
        context=attestation.context,
        weight=attestation.weight,
        comment=attestation.comment,
        created_at=attestation.created_at.isoformat(),
    )


@router.get(
    "/entities/{entity_id}/attestations",
    response_model=AttestationListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_attestations(
    entity_id: uuid.UUID,
    type: str | None = Query(None, alias="type"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List trust attestations for an entity (public)."""
    # Verify entity exists
    target = await db.get(Entity, entity_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    query = (
        select(TrustAttestation, Entity.display_name)
        .join(Entity, TrustAttestation.attester_entity_id == Entity.id)
        .where(TrustAttestation.target_entity_id == entity_id)
    )
    if type and type in VALID_ATTESTATION_TYPES:
        query = query.where(TrustAttestation.attestation_type == type)

    # Get total count
    count_query = (
        select(func.count()).select_from(TrustAttestation)
        .where(TrustAttestation.target_entity_id == entity_id)
    )
    if type and type in VALID_ATTESTATION_TYPES:
        count_query = count_query.where(
            TrustAttestation.attestation_type == type
        )
    total = await db.scalar(count_query) or 0

    query = query.order_by(TrustAttestation.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)

    attestations = []
    for att, attester_name in result.all():
        attestations.append(AttestationResponse(
            id=att.id,
            attester_id=att.attester_entity_id,
            attester_display_name=attester_name,
            target_entity_id=att.target_entity_id,
            attestation_type=att.attestation_type,
            context=att.context,
            weight=att.weight,
            comment=att.comment,
            created_at=att.created_at.isoformat(),
        ))

    return AttestationListResponse(attestations=attestations, count=total)


@router.get(
    "/entities/{entity_id}/trust/contextual",
    response_model=ContextualTrustResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_contextual_trust(
    entity_id: uuid.UUID,
    context: str = Query(..., min_length=1, max_length=100),
    db: AsyncSession = Depends(get_db),
):
    """Get contextual trust score for an entity in a specific context."""
    target = await db.get(Entity, entity_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Check if there's a precomputed contextual score
    ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    contextual_scores = (ts.contextual_scores or {}) if ts else {}
    score = contextual_scores.get(context)

    # Count attestations in this context
    att_count = await db.scalar(
        select(func.count()).select_from(TrustAttestation).where(
            TrustAttestation.target_entity_id == entity_id,
            TrustAttestation.context == context,
        )
    ) or 0

    return ContextualTrustResponse(
        entity_id=entity_id,
        context=context,
        score=score,
        attestation_count=att_count,
    )


@router.delete(
    "/entities/{entity_id}/attestations/{attestation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit_writes)],
)
async def delete_attestation(
    entity_id: uuid.UUID,
    attestation_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Delete an attestation. Only the attester can delete their own."""
    attestation = await db.get(TrustAttestation, attestation_id)
    if attestation is None:
        raise HTTPException(status_code=404, detail="Attestation not found")

    if attestation.target_entity_id != entity_id:
        raise HTTPException(status_code=404, detail="Attestation not found")

    if attestation.attester_entity_id != current_entity.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own attestations",
        )

    await db.delete(attestation)
    await db.flush()
