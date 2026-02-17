from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_writes
from src.database import get_db
from src.models import Entity, EntityRelationship, RelationshipType

router = APIRouter(prefix="/social", tags=["social"])


class FollowResponse(BaseModel):
    message: str


class EntitySummary(BaseModel):
    id: uuid.UUID
    type: str
    display_name: str
    did_web: str

    model_config = {"from_attributes": True}


class FollowListResponse(BaseModel):
    entities: list[EntitySummary]
    count: int


@router.post(
    "/follow/{target_id}",
    response_model=FollowResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def follow_entity(
    target_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    if current_entity.id == target_id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")

    target = await db.get(Entity, target_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Check if already following
    existing = await db.scalar(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id == current_entity.id,
            EntityRelationship.target_entity_id == target_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Already following")

    rel = EntityRelationship(
        id=uuid.uuid4(),
        source_entity_id=current_entity.id,
        target_entity_id=target_id,
        type=RelationshipType.FOLLOW,
    )
    db.add(rel)
    await db.flush()
    return FollowResponse(message=f"Now following {target.display_name}")


@router.delete("/follow/{target_id}", response_model=FollowResponse)
async def unfollow_entity(
    target_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.scalar(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id == current_entity.id,
            EntityRelationship.target_entity_id == target_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="Not following this entity")

    await db.delete(existing)
    await db.flush()
    return FollowResponse(message="Unfollowed")


@router.get("/following/{entity_id}", response_model=FollowListResponse)
async def get_following(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get entities that this entity follows."""
    result = await db.execute(
        select(Entity)
        .join(
            EntityRelationship,
            EntityRelationship.target_entity_id == Entity.id,
        )
        .where(
            EntityRelationship.source_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
        )
    )
    entities = result.scalars().all()
    return FollowListResponse(
        entities=[
            EntitySummary(
                id=e.id,
                type=e.type.value,
                display_name=e.display_name,
                did_web=e.did_web,
            )
            for e in entities
        ],
        count=len(entities),
    )


@router.get("/followers/{entity_id}", response_model=FollowListResponse)
async def get_followers(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get entities that follow this entity."""
    result = await db.execute(
        select(Entity)
        .join(
            EntityRelationship,
            EntityRelationship.source_entity_id == Entity.id,
        )
        .where(
            EntityRelationship.target_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
        )
    )
    entities = result.scalars().all()
    return FollowListResponse(
        entities=[
            EntitySummary(
                id=e.id,
                type=e.type.value,
                display_name=e.display_name,
                did_web=e.did_web,
            )
            for e in entities
        ],
        count=len(entities),
    )


@router.get("/stats/{entity_id}")
async def get_social_stats(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    following_count = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(
            EntityRelationship.source_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    ) or 0

    followers_count = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(
            EntityRelationship.target_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    ) or 0

    return {
        "entity_id": str(entity_id),
        "following_count": following_count,
        "followers_count": followers_count,
    }
