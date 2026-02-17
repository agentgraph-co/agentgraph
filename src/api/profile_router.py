from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, get_optional_entity
from src.database import get_db
from src.models import Entity, EntityType

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
    is_active: bool
    created_at: str
    is_own_profile: bool = False

    model_config = {"from_attributes": True}


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

    return ProfileResponse(
        id=entity.id,
        type=entity.type.value,
        display_name=entity.display_name,
        bio_markdown=entity.bio_markdown or "",
        did_web=entity.did_web,
        capabilities=entity.capabilities if entity.type == EntityType.AGENT else None,
        autonomy_level=entity.autonomy_level,
        is_active=entity.is_active,
        created_at=entity.created_at.isoformat(),
        is_own_profile=is_own,
    )


@router.patch("/{entity_id}", response_model=ProfileResponse)
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

    return ProfileResponse(
        id=entity.id,
        type=entity.type.value,
        display_name=entity.display_name,
        bio_markdown=entity.bio_markdown or "",
        did_web=entity.did_web,
        capabilities=entity.capabilities if entity.type == EntityType.AGENT else None,
        autonomy_level=entity.autonomy_level,
        is_active=entity.is_active,
        created_at=entity.created_at.isoformat(),
        is_own_profile=True,
    )
