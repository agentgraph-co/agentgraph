from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_writes
from src.database import get_db
from src.models import (
    CapabilityEndorsement,
    Entity,
    EntityType,
    Review,
)

router = APIRouter(tags=["endorsements & reviews"])

# --- Schemas ---


class EndorseCapabilityRequest(BaseModel):
    capability: str = Field(..., min_length=1, max_length=200)
    comment: str | None = Field(None, max_length=1000)


class EndorsementResponse(BaseModel):
    id: uuid.UUID
    agent_entity_id: uuid.UUID
    endorser_entity_id: uuid.UUID
    endorser_display_name: str = ""
    capability: str
    tier: str
    comment: str | None = None
    created_at: datetime


class CapabilitySummary(BaseModel):
    capability: str
    tier: str  # highest tier: formally_audited > community_verified > self_declared
    endorsement_count: int
    endorsers: list[str]  # display names


class CreateReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    text: str | None = Field(None, max_length=5000)


class ReviewResponse(BaseModel):
    id: uuid.UUID
    target_entity_id: uuid.UUID
    reviewer_entity_id: uuid.UUID
    reviewer_display_name: str = ""
    rating: int
    text: str | None = None
    created_at: datetime
    updated_at: datetime


class ReviewSummary(BaseModel):
    average_rating: float | None = None
    review_count: int = 0
    rating_distribution: dict[str, int] = {}  # {"1": 0, "2": 0, ...}


# --- Capability Endorsement Endpoints ---


TIER_RANK = {
    "self_declared": 0,
    "community_verified": 1,
    "formally_audited": 2,
}


@router.post(
    "/entities/{entity_id}/endorsements",
    response_model=EndorsementResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_writes)],
)
async def endorse_capability(
    entity_id: uuid.UUID,
    body: EndorseCapabilityRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Endorse a capability of an agent."""
    target = await db.get(Entity, entity_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")
    if target.type != EntityType.AGENT:
        raise HTTPException(
            status_code=400,
            detail="Can only endorse agent capabilities",
        )
    if current_entity.id == entity_id:
        raise HTTPException(
            status_code=400, detail="Cannot endorse your own capabilities",
        )

    # Check if already endorsed this capability
    existing = await db.scalar(
        select(CapabilityEndorsement).where(
            CapabilityEndorsement.agent_entity_id == entity_id,
            CapabilityEndorsement.endorser_entity_id == current_entity.id,
            CapabilityEndorsement.capability == body.capability,
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Already endorsed this capability",
        )

    endorsement = CapabilityEndorsement(
        id=uuid.uuid4(),
        agent_entity_id=entity_id,
        endorser_entity_id=current_entity.id,
        capability=body.capability,
        tier="community_verified",
        comment=body.comment,
    )
    db.add(endorsement)
    await db.flush()

    # Send notification
    from src.api.notification_router import create_notification

    await create_notification(
        db,
        entity_id=entity_id,
        kind="endorsement",
        title="Capability endorsed",
        body=(
            f"{current_entity.display_name} endorsed your "
            f"'{body.capability}' capability"
        ),
        reference_id=str(endorsement.id),
    )

    return EndorsementResponse(
        id=endorsement.id,
        agent_entity_id=entity_id,
        endorser_entity_id=current_entity.id,
        endorser_display_name=current_entity.display_name,
        capability=body.capability,
        tier=endorsement.tier,
        comment=body.comment,
        created_at=endorsement.created_at,
    )


@router.get(
    "/entities/{entity_id}/endorsements",
    response_model=list[EndorsementResponse],
)
async def list_endorsements(
    entity_id: uuid.UUID,
    capability: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List endorsements for an entity, optionally filtered by capability."""
    target = await db.get(Entity, entity_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    query = (
        select(CapabilityEndorsement, Entity.display_name)
        .join(
            Entity,
            CapabilityEndorsement.endorser_entity_id == Entity.id,
        )
        .where(CapabilityEndorsement.agent_entity_id == entity_id)
    )
    if capability:
        query = query.where(
            CapabilityEndorsement.capability == capability,
        )
    query = query.order_by(CapabilityEndorsement.created_at.desc())

    result = await db.execute(query)
    return [
        EndorsementResponse(
            id=e.id,
            agent_entity_id=e.agent_entity_id,
            endorser_entity_id=e.endorser_entity_id,
            endorser_display_name=name,
            capability=e.capability,
            tier=e.tier,
            comment=e.comment,
            created_at=e.created_at,
        )
        for e, name in result.all()
    ]


@router.get(
    "/entities/{entity_id}/capabilities",
    response_model=list[CapabilitySummary],
)
async def get_capability_summary(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated capability summary with endorsement counts and tiers."""
    target = await db.get(Entity, entity_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Get all endorsements grouped by capability
    result = await db.execute(
        select(
            CapabilityEndorsement.capability,
            CapabilityEndorsement.tier,
            Entity.display_name,
        )
        .join(
            Entity,
            CapabilityEndorsement.endorser_entity_id == Entity.id,
        )
        .where(CapabilityEndorsement.agent_entity_id == entity_id)
        .order_by(CapabilityEndorsement.capability)
    )
    rows = result.all()

    # Also include self-declared capabilities from the entity
    caps: dict[str, dict] = {}

    # Add self-declared from entity.capabilities
    if target.capabilities:
        for cap in target.capabilities:
            cap_name = cap if isinstance(cap, str) else str(cap)
            caps[cap_name] = {
                "tier": "self_declared",
                "endorsers": [],
                "count": 0,
            }

    # Overlay endorsements
    for capability, tier, endorser_name in rows:
        if capability not in caps:
            caps[capability] = {
                "tier": tier,
                "endorsers": [],
                "count": 0,
            }
        entry = caps[capability]
        entry["count"] += 1
        entry["endorsers"].append(endorser_name)
        # Promote tier to highest
        if TIER_RANK.get(tier, 0) > TIER_RANK.get(entry["tier"], 0):
            entry["tier"] = tier

    return [
        CapabilitySummary(
            capability=name,
            tier=data["tier"],
            endorsement_count=data["count"],
            endorsers=data["endorsers"],
        )
        for name, data in sorted(caps.items())
    ]


@router.delete(
    "/entities/{entity_id}/endorsements/{capability}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit_writes)],
)
async def remove_endorsement(
    entity_id: uuid.UUID,
    capability: str,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Remove your endorsement of a capability."""
    endorsement = await db.scalar(
        select(CapabilityEndorsement).where(
            CapabilityEndorsement.agent_entity_id == entity_id,
            CapabilityEndorsement.endorser_entity_id == current_entity.id,
            CapabilityEndorsement.capability == capability,
        )
    )
    if endorsement is None:
        raise HTTPException(
            status_code=404, detail="Endorsement not found",
        )
    await db.delete(endorsement)
    await db.flush()


# --- Review Endpoints ---


@router.post(
    "/entities/{entity_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_writes)],
)
async def create_review(
    entity_id: uuid.UUID,
    body: CreateReviewRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Create or update a review for an entity."""
    target = await db.get(Entity, entity_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")
    if current_entity.id == entity_id:
        raise HTTPException(
            status_code=400, detail="Cannot review yourself",
        )

    # Content filter on review text
    if body.text:
        from src.content_filter import check_content

        filter_result = check_content(body.text)
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Content rejected: {', '.join(filter_result.flags)}",
            )

    # Upsert: update if already reviewed
    existing = await db.scalar(
        select(Review).where(
            Review.target_entity_id == entity_id,
            Review.reviewer_entity_id == current_entity.id,
        )
    )

    if existing:
        existing.rating = body.rating
        existing.text = body.text
        await db.flush()
        await db.refresh(existing)
        return ReviewResponse(
            id=existing.id,
            target_entity_id=entity_id,
            reviewer_entity_id=current_entity.id,
            reviewer_display_name=current_entity.display_name,
            rating=existing.rating,
            text=existing.text,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )

    review = Review(
        id=uuid.uuid4(),
        target_entity_id=entity_id,
        reviewer_entity_id=current_entity.id,
        rating=body.rating,
        text=body.text,
    )
    db.add(review)
    await db.flush()

    # Notify reviewed entity
    from src.api.notification_router import create_notification

    await create_notification(
        db,
        entity_id=entity_id,
        kind="review",
        title="New review",
        body=(
            f"{current_entity.display_name} rated you "
            f"{body.rating}/5"
        ),
        reference_id=str(review.id),
    )

    return ReviewResponse(
        id=review.id,
        target_entity_id=entity_id,
        reviewer_entity_id=current_entity.id,
        reviewer_display_name=current_entity.display_name,
        rating=review.rating,
        text=review.text,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


@router.get(
    "/entities/{entity_id}/reviews",
    response_model=list[ReviewResponse],
)
async def list_reviews(
    entity_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """List reviews for an entity."""
    target = await db.get(Entity, entity_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    result = await db.execute(
        select(Review, Entity.display_name)
        .join(Entity, Review.reviewer_entity_id == Entity.id)
        .where(Review.target_entity_id == entity_id)
        .order_by(Review.created_at.desc())
        .limit(limit)
    )
    return [
        ReviewResponse(
            id=r.id,
            target_entity_id=r.target_entity_id,
            reviewer_entity_id=r.reviewer_entity_id,
            reviewer_display_name=name,
            rating=r.rating,
            text=r.text,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r, name in result.all()
    ]


@router.get(
    "/entities/{entity_id}/reviews/summary",
    response_model=ReviewSummary,
)
async def get_review_summary(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get review summary (average rating, distribution) for an entity."""
    target = await db.get(Entity, entity_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    result = await db.execute(
        select(
            func.avg(Review.rating),
            func.count(Review.id),
        ).where(Review.target_entity_id == entity_id)
    )
    row = result.one()
    avg_rating = float(row[0]) if row[0] is not None else None
    count = row[1]

    # Rating distribution
    dist_result = await db.execute(
        select(Review.rating, func.count())
        .where(Review.target_entity_id == entity_id)
        .group_by(Review.rating)
    )
    distribution = {str(i): 0 for i in range(1, 6)}
    for rating, cnt in dist_result.all():
        distribution[str(rating)] = cnt

    return ReviewSummary(
        average_rating=round(avg_rating, 2) if avg_rating else None,
        review_count=count,
        rating_distribution=distribution,
    )


@router.delete(
    "/entities/{entity_id}/reviews",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit_writes)],
)
async def delete_review(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Delete your review of an entity."""
    review = await db.scalar(
        select(Review).where(
            Review.target_entity_id == entity_id,
            Review.reviewer_entity_id == current_entity.id,
        )
    )
    if review is None:
        raise HTTPException(
            status_code=404, detail="Review not found",
        )
    await db.delete(review)
    await db.flush()
