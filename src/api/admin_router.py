from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.database import get_db
from src.models import (
    Entity,
    EntityType,
    ModerationFlag,
    ModerationStatus,
    Post,
    WebhookSubscription,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(entity: Entity) -> None:
    if not entity.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")


class PlatformStats(BaseModel):
    total_entities: int
    total_humans: int
    total_agents: int
    total_posts: int
    pending_moderation_flags: int
    active_webhooks: int


class EntityListItem(BaseModel):
    id: uuid.UUID
    type: str
    display_name: str
    email: str | None
    did_web: str
    is_active: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class EntityListResponse(BaseModel):
    entities: list[EntityListItem]
    total: int


@router.get("/stats", response_model=PlatformStats)
async def platform_stats(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get platform-wide statistics. Admin only."""
    _require_admin(current_entity)

    total_entities = await db.scalar(
        select(func.count()).select_from(Entity)
    ) or 0
    total_humans = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.type == EntityType.HUMAN
        )
    ) or 0
    total_agents = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.type == EntityType.AGENT
        )
    ) or 0
    total_posts = await db.scalar(
        select(func.count()).select_from(Post)
    ) or 0
    pending_flags = await db.scalar(
        select(func.count()).select_from(ModerationFlag).where(
            ModerationFlag.status == ModerationStatus.PENDING
        )
    ) or 0
    active_webhooks = await db.scalar(
        select(func.count()).select_from(WebhookSubscription).where(
            WebhookSubscription.is_active.is_(True)
        )
    ) or 0

    return PlatformStats(
        total_entities=total_entities,
        total_humans=total_humans,
        total_agents=total_agents,
        total_posts=total_posts,
        pending_moderation_flags=pending_flags,
        active_webhooks=active_webhooks,
    )


@router.get("/entities", response_model=EntityListResponse)
async def list_entities(
    type: str | None = Query(None, pattern="^(human|agent)$"),
    active_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List all entities. Admin only."""
    _require_admin(current_entity)

    query = select(Entity).order_by(Entity.created_at.desc())
    count_query = select(func.count()).select_from(Entity)

    if type == "human":
        query = query.where(Entity.type == EntityType.HUMAN)
        count_query = count_query.where(Entity.type == EntityType.HUMAN)
    elif type == "agent":
        query = query.where(Entity.type == EntityType.AGENT)
        count_query = count_query.where(Entity.type == EntityType.AGENT)

    if active_only:
        query = query.where(Entity.is_active.is_(True))
        count_query = count_query.where(Entity.is_active.is_(True))

    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(offset).limit(limit))
    entities = result.scalars().all()

    return EntityListResponse(
        entities=[
            EntityListItem(
                id=e.id,
                type=e.type.value,
                display_name=e.display_name,
                email=e.email,
                did_web=e.did_web,
                is_active=e.is_active,
                is_admin=e.is_admin,
                created_at=e.created_at,
            )
            for e in entities
        ],
        total=total,
    )


@router.patch("/entities/{entity_id}/deactivate")
async def deactivate_entity(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate an entity. Admin only."""
    _require_admin(current_entity)

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if entity.id == current_entity.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    entity.is_active = False
    await db.flush()
    return {"message": f"Entity {entity.display_name} deactivated"}


@router.patch("/entities/{entity_id}/reactivate")
async def reactivate_entity(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Reactivate an entity. Admin only."""
    _require_admin(current_entity)

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity.is_active = True
    await db.flush()
    return {"message": f"Entity {entity.display_name} reactivated"}


@router.patch("/entities/{entity_id}/promote")
async def promote_to_admin(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Promote an entity to admin. Admin only."""
    _require_admin(current_entity)

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if entity.is_admin:
        raise HTTPException(status_code=409, detail="Already an admin")

    entity.is_admin = True
    await db.flush()
    return {"message": f"Entity {entity.display_name} promoted to admin"}


@router.post("/trust/recompute")
async def recompute_trust_scores(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Recompute trust scores for all active entities. Admin only."""
    _require_admin(current_entity)

    from src.trust.score import batch_recompute

    count = await batch_recompute(db)
    return {"message": f"Recomputed trust scores for {count} entities"}
