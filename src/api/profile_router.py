from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.api.deps import get_current_entity, get_optional_entity
from src.api.rate_limit import rate_limit_writes
from src.database import get_db
from src.models import (
    CapabilityEndorsement,
    Entity,
    EntityRelationship,
    EntityType,
    Post,
    PrivacyTier,
    RelationshipType,
    Review,
    TrustScore,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=100)
    bio_markdown: str | None = Field(None, max_length=5000)


class ProfileResponse(BaseModel):
    id: uuid.UUID
    type: str
    display_name: str
    bio_markdown: str
    did_web: str
    capabilities: list | None = None
    autonomy_level: int | None = None
    privacy_tier: str = "public"
    is_active: bool
    email_verified: bool = False
    trust_score: float | None = None
    badges: list[str] = []
    average_rating: float | None = None
    review_count: int = 0
    endorsement_count: int = 0
    post_count: int = 0
    follower_count: int = 0
    following_count: int = 0
    created_at: str
    is_own_profile: bool = False

    model_config = {"from_attributes": True}


async def _get_counts(
    db: AsyncSession, entity_id: uuid.UUID,
) -> tuple[int, int, int]:
    """Return (post_count, follower_count, following_count)."""
    post_count = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == entity_id,
            Post.is_hidden.is_(False),
        )
    ) or 0

    follower_count = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(
            EntityRelationship.target_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    ) or 0

    following_count = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(
            EntityRelationship.source_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    ) or 0

    return post_count, follower_count, following_count


async def _get_review_stats(
    db: AsyncSession, entity_id: uuid.UUID,
) -> tuple[float | None, int, int]:
    """Return (average_rating, review_count, endorsement_count)."""
    result = await db.execute(
        select(
            func.avg(Review.rating),
            func.count(Review.id),
        ).where(Review.target_entity_id == entity_id)
    )
    row = result.one()
    avg_rating = round(float(row[0]), 2) if row[0] is not None else None
    review_count = row[1]

    endorsement_count = await db.scalar(
        select(func.count()).select_from(CapabilityEndorsement).where(
            CapabilityEndorsement.agent_entity_id == entity_id,
        )
    ) or 0

    return avg_rating, review_count, endorsement_count


def _compute_badges(entity: Entity) -> list[str]:
    """Compute verification badges for an entity."""
    badges = []
    if entity.email_verified:
        badges.append("email_verified")
    if entity.bio_markdown and len(entity.bio_markdown) > 10:
        badges.append("profile_complete")
    if entity.type == EntityType.AGENT and entity.operator_id:
        badges.append("operator_linked")
    if entity.is_admin:
        badges.append("admin")
    return badges


@router.get("/{entity_id}", response_model=ProfileResponse)
async def get_profile(
    entity_id: uuid.UUID,
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    entity = await db.get(Entity, entity_id)
    if entity is None or not entity.is_active:
        raise HTTPException(status_code=404, detail="Profile not found")

    is_own = current_entity is not None and current_entity.id == entity_id

    # Privacy tier enforcement
    if not is_own and entity.privacy_tier != PrivacyTier.PUBLIC:
        can_view = False
        if entity.privacy_tier == PrivacyTier.VERIFIED:
            # Verified tier: visible to any authenticated, verified entity
            can_view = (
                current_entity is not None and current_entity.email_verified
            )
        elif entity.privacy_tier == PrivacyTier.PRIVATE:
            # Private tier: visible only to followers
            if current_entity is not None:
                is_follower = await db.scalar(
                    select(EntityRelationship).where(
                        EntityRelationship.source_entity_id
                        == current_entity.id,
                        EntityRelationship.target_entity_id == entity_id,
                        EntityRelationship.type == RelationshipType.FOLLOW,
                    )
                )
                can_view = is_follower is not None

        if not can_view:
            # Return limited profile
            return ProfileResponse(
                id=entity.id,
                type=entity.type.value,
                display_name=entity.display_name,
                bio_markdown="",
                did_web=entity.did_web,
                privacy_tier=entity.privacy_tier.value,
                is_active=entity.is_active,
                created_at=entity.created_at.isoformat(),
                is_own_profile=False,
            )

    ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    post_count, follower_count, following_count = await _get_counts(
        db, entity_id
    )
    avg_rating, review_count, endorsement_count = await _get_review_stats(
        db, entity_id
    )

    return ProfileResponse(
        id=entity.id,
        type=entity.type.value,
        display_name=entity.display_name,
        bio_markdown=entity.bio_markdown or "",
        did_web=entity.did_web,
        capabilities=(
            entity.capabilities
            if entity.type == EntityType.AGENT
            else None
        ),
        autonomy_level=entity.autonomy_level,
        privacy_tier=entity.privacy_tier.value,
        is_active=entity.is_active,
        email_verified=entity.email_verified,
        trust_score=ts.score if ts else None,
        badges=_compute_badges(entity),
        average_rating=avg_rating,
        review_count=review_count,
        endorsement_count=endorsement_count,
        post_count=post_count,
        follower_count=follower_count,
        following_count=following_count,
        created_at=entity.created_at.isoformat(),
        is_own_profile=is_own,
    )


@router.patch(
    "/{entity_id}", response_model=ProfileResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def update_profile(
    entity_id: uuid.UUID,
    body: UpdateProfileRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    if current_entity.id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own profile",
        )

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entity, field, value)
    await db.flush()

    ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    post_count, follower_count, following_count = await _get_counts(
        db, entity_id
    )
    avg_rating, review_count, endorsement_count = await _get_review_stats(
        db, entity_id
    )

    return ProfileResponse(
        id=entity.id,
        type=entity.type.value,
        display_name=entity.display_name,
        bio_markdown=entity.bio_markdown or "",
        did_web=entity.did_web,
        capabilities=(
            entity.capabilities
            if entity.type == EntityType.AGENT
            else None
        ),
        autonomy_level=entity.autonomy_level,
        privacy_tier=entity.privacy_tier.value,
        is_active=entity.is_active,
        email_verified=entity.email_verified,
        trust_score=ts.score if ts else None,
        badges=_compute_badges(entity),
        average_rating=avg_rating,
        review_count=review_count,
        endorsement_count=endorsement_count,
        post_count=post_count,
        follower_count=follower_count,
        following_count=following_count,
        created_at=entity.created_at.isoformat(),
        is_own_profile=True,
    )
