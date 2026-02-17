from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.database import get_db
from src.models import (
    Entity,
    ModerationFlag,
    ModerationReason,
    ModerationStatus,
    Post,
)

router = APIRouter(prefix="/moderation", tags=["moderation"])


class CreateFlagRequest(BaseModel):
    target_type: str = Field(..., pattern="^(post|entity)$")
    target_id: uuid.UUID
    reason: ModerationReason
    details: str | None = Field(None, max_length=2000)


class FlagResponse(BaseModel):
    id: uuid.UUID
    reporter_entity_id: uuid.UUID | None
    target_type: str
    target_id: uuid.UUID
    reason: str
    details: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ResolveFlagRequest(BaseModel):
    status: ModerationStatus = Field(
        ...,
        description="Must be one of: dismissed, warned, removed, suspended, banned",
    )
    resolution_note: str | None = Field(None, max_length=2000)


class FlagListResponse(BaseModel):
    flags: list[FlagResponse]
    count: int


@router.post("/flag", response_model=FlagResponse, status_code=201)
async def create_flag(
    body: CreateFlagRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    # Verify target exists
    if body.target_type == "post":
        target = await db.get(Post, body.target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Target post not found")
        if target.author_entity_id == current_entity.id:
            raise HTTPException(status_code=400, detail="Cannot flag your own content")
    elif body.target_type == "entity":
        target = await db.get(Entity, body.target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Target entity not found")
        if target.id == current_entity.id:
            raise HTTPException(status_code=400, detail="Cannot flag yourself")

    # Prevent duplicate active flags from the same reporter on the same target
    existing = await db.scalar(
        select(ModerationFlag).where(
            ModerationFlag.reporter_entity_id == current_entity.id,
            ModerationFlag.target_type == body.target_type,
            ModerationFlag.target_id == body.target_id,
            ModerationFlag.status == ModerationStatus.PENDING,
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="You already have a pending flag on this target",
        )

    flag = ModerationFlag(
        id=uuid.uuid4(),
        reporter_entity_id=current_entity.id,
        target_type=body.target_type,
        target_id=body.target_id,
        reason=body.reason,
        details=body.details,
        status=ModerationStatus.PENDING,
    )
    db.add(flag)
    await db.flush()

    return FlagResponse(
        id=flag.id,
        reporter_entity_id=flag.reporter_entity_id,
        target_type=flag.target_type,
        target_id=flag.target_id,
        reason=flag.reason.value,
        details=flag.details,
        status=flag.status.value,
        created_at=flag.created_at,
    )


@router.get("/flags", response_model=FlagListResponse)
async def list_flags(
    status: ModerationStatus | None = Query(None),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List moderation flags. Only admins can see all flags."""
    if not current_entity.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    query = select(ModerationFlag).order_by(ModerationFlag.created_at.desc())
    if status is not None:
        query = query.where(ModerationFlag.status == status)

    result = await db.execute(query)
    flags = result.scalars().all()

    return FlagListResponse(
        flags=[
            FlagResponse(
                id=f.id,
                reporter_entity_id=f.reporter_entity_id,
                target_type=f.target_type,
                target_id=f.target_id,
                reason=f.reason.value,
                details=f.details,
                status=f.status.value,
                created_at=f.created_at,
            )
            for f in flags
        ],
        count=len(flags),
    )


@router.patch("/flags/{flag_id}/resolve", response_model=FlagResponse)
async def resolve_flag(
    flag_id: uuid.UUID,
    body: ResolveFlagRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a moderation flag. Admin only."""
    if not current_entity.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    if body.status == ModerationStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Cannot resolve to 'pending' status",
        )

    flag = await db.get(ModerationFlag, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag not found")
    if flag.status != ModerationStatus.PENDING:
        raise HTTPException(status_code=409, detail="Flag already resolved")

    flag.status = body.status
    flag.resolved_by = current_entity.id
    flag.resolution_note = body.resolution_note
    flag.resolved_at = func.now()

    # Auto-hide post if removal action
    if body.status == ModerationStatus.REMOVED and flag.target_type == "post":
        post = await db.get(Post, flag.target_id)
        if post:
            post.is_hidden = True

    # Suspend entity if suspension action
    if body.status in (ModerationStatus.SUSPENDED, ModerationStatus.BANNED):
        if flag.target_type == "entity":
            target_entity = await db.get(Entity, flag.target_id)
            if target_entity:
                target_entity.is_active = False

    await db.flush()

    return FlagResponse(
        id=flag.id,
        reporter_entity_id=flag.reporter_entity_id,
        target_type=flag.target_type,
        target_id=flag.target_id,
        reason=flag.reason.value,
        details=flag.details,
        status=flag.status.value,
        created_at=flag.created_at,
    )


@router.get("/stats")
async def moderation_stats(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get moderation statistics. Admin only."""
    if not current_entity.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    pending = await db.scalar(
        select(func.count()).select_from(ModerationFlag).where(
            ModerationFlag.status == ModerationStatus.PENDING,
        )
    ) or 0

    total = await db.scalar(
        select(func.count()).select_from(ModerationFlag)
    ) or 0

    resolved = total - pending

    return {
        "total_flags": total,
        "pending_flags": pending,
        "resolved_flags": resolved,
    }
