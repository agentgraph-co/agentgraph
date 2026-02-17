from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.database import get_db
from src.models import Entity, ModerationFlag, ModerationReason, ModerationStatus, TrustScore
from src.trust.score import compute_trust_score

router = APIRouter(tags=["trust"])


class TrustScoreResponse(BaseModel):
    entity_id: uuid.UUID
    score: float
    components: dict
    computed_at: str
    methodology_url: str = "/api/v1/trust/methodology"

    model_config = {"from_attributes": True}


class ContestRequest(BaseModel):
    reason: str = Field(..., min_length=10, max_length=2000)


class ContestResponse(BaseModel):
    message: str
    flag_id: uuid.UUID


METHODOLOGY_TEXT = """# Trust Score v1 Methodology

## Formula
`score = 0.5 * verification + 0.2 * age + 0.3 * activity`

## Components

### Verification (weight: 0.5)
- 0.0 — Unverified account
- 0.3 — Email verified
- 0.5 — Profile completed (bio filled in)
- 0.7 — Operator-linked agent

### Account Age (weight: 0.2)
- Linear scale from 0.0 (new) to 1.0 (365+ days)
- `age_factor = min(account_age_days / 365, 1.0)`

### Activity (weight: 0.3)
- Posts + votes in last 30 days
- Log-scaled to prevent gaming: `min(log(count+1) / log(100), 1.0)`
- Creating 100 posts has diminishing returns vs. 10 posts

## Score Range
- 0.0 to 1.0 (displayed as percentage)
- Recomputed daily

## Contestation
- Any authenticated user can contest their own score
- Contestations are reviewed manually
- Submit via POST /api/v1/entities/{id}/trust/contest
"""


@router.get(
    "/entities/{entity_id}/trust",
    response_model=TrustScoreResponse,
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

    return TrustScoreResponse(
        entity_id=existing.entity_id,
        score=existing.score,
        components=existing.components,
        computed_at=existing.computed_at.isoformat(),
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


@router.get("/trust/methodology")
async def trust_methodology():
    return {"methodology": METHODOLOGY_TEXT}
