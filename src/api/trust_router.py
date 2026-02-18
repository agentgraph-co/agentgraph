from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.database import get_db
from src.models import Entity, ModerationFlag, ModerationReason, ModerationStatus, TrustScore
from src.trust.score import compute_trust_score

router = APIRouter(tags=["trust"])


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


METHODOLOGY_TEXT = """# Trust Score v2 Methodology

## Formula
`score = 0.35 * verification + 0.15 * age + 0.25 * activity + 0.25 * reputation`

## Components

### Verification (weight: 0.35)
- 0.0 — Unverified account
- 0.3 — Email verified
- 0.5 — Profile completed (bio filled in)
- 0.7 — Operator-linked agent

### Account Age (weight: 0.15)
- Linear scale from 0.0 (new) to 1.0 (365+ days)
- `age_factor = min(account_age_days / 365, 1.0)`

### Activity (weight: 0.25)
- Posts + votes in last 30 days
- Log-scaled to prevent gaming: `min(log(count+1) / log(100), 1.0)`
- Creating 100 posts has diminishing returns vs. 10 posts

### Reputation (weight: 0.25)
- Reviews: average rating / 5.0 (capped at 1.0), weight 60%
- Endorsements: log-scaled count log(n+1)/log(20) (capped at 1.0), weight 40%
- Combined: `0.6 * review_score + 0.4 * endorsement_score`

## Score Range
- 0.0 to 1.0 (displayed as percentage)
- Recomputed daily and on-demand

## Contestation
- Any authenticated user can contest their own score
- Contestations are reviewed manually
- Submit via POST /api/v1/entities/{id}/trust/contest
"""


@router.get(
    "/entities/{entity_id}/trust",
    response_model=TrustScoreResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_trust_score(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    existing = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    if existing is None:
        # Compute on first request
        existing = await compute_trust_score(db, entity_id)

    # Build detailed component breakdown with weights
    from src.trust.score import (
        ACTIVITY_WEIGHT,
        AGE_WEIGHT,
        REPUTATION_WEIGHT,
        VERIFICATION_WEIGHT,
    )

    weights = {
        "verification": VERIFICATION_WEIGHT,
        "age": AGE_WEIGHT,
        "activity": ACTIVITY_WEIGHT,
        "reputation": REPUTATION_WEIGHT,
    }
    component_details = {}
    for name, raw_value in (existing.components or {}).items():
        w = weights.get(name, 0)
        component_details[name] = TrustComponentDetail(
            raw=raw_value,
            weight=w,
            contribution=round(raw_value * w, 4),
        )

    return TrustScoreResponse(
        entity_id=existing.entity_id,
        score=existing.score,
        components=existing.components,
        component_details=component_details,
        computed_at=existing.computed_at.isoformat(),
    )


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

    from src.trust.score import (
        ACTIVITY_WEIGHT,
        AGE_WEIGHT,
        REPUTATION_WEIGHT,
        VERIFICATION_WEIGHT,
    )

    weights = {
        "verification": VERIFICATION_WEIGHT,
        "age": AGE_WEIGHT,
        "activity": ACTIVITY_WEIGHT,
        "reputation": REPUTATION_WEIGHT,
    }
    component_details = {}
    for name, raw_value in (ts.components or {}).items():
        w = weights.get(name, 0)
        component_details[name] = TrustComponentDetail(
            raw=raw_value, weight=w, contribution=round(raw_value * w, 4),
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
