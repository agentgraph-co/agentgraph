"""Account management endpoints.

Provides password change, account deactivation, and audit log
access for the authenticated entity.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.api.auth_service import hash_password, verify_password
from src.api.deactivation import cascade_deactivate
from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import AuditLog, Entity, PrivacyTier

router = APIRouter(prefix="/account", tags=["account"])


# --- Schemas ---


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class SetPrivacyTierRequest(BaseModel):
    tier: str = Field(
        ..., pattern="^(public|verified|private)$",
    )


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    action: str
    resource_type: str | None
    resource_id: uuid.UUID | None
    details: dict
    ip_address: str | None
    created_at: str

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    entries: list[AuditLogResponse]
    total: int


# --- Endpoints ---


@router.post("/change-password", dependencies=[Depends(rate_limit_writes)])
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    if current_entity.password_hash is None:
        raise HTTPException(
            status_code=400, detail="Agent entities cannot change password",
        )

    if not verify_password(body.current_password, current_entity.password_hash):
        raise HTTPException(
            status_code=401, detail="Current password is incorrect",
        )

    current_entity.password_hash = hash_password(body.new_password)
    await db.flush()

    await log_action(
        db,
        action="auth.password_change",
        entity_id=current_entity.id,
        ip_address=request.client.host if request.client else None,
    )

    return {"message": "Password changed successfully"}


@router.post("/deactivate", dependencies=[Depends(rate_limit_writes)])
async def deactivate_account(
    request: Request,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate the current user's account."""
    ip = request.client.host if request.client else None

    current_entity.is_active = False
    await db.flush()

    await log_action(
        db,
        action="account.self_deactivate",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=current_entity.id,
        ip_address=ip,
    )

    cascade = await cascade_deactivate(
        db, current_entity.id, performed_by=current_entity.id, ip_address=ip,
    )

    return {
        "message": "Account deactivated",
        "cascade": cascade,
    }


@router.get("/privacy")
async def get_privacy_tier(
    current_entity: Entity = Depends(get_current_entity),
):
    """Get the current entity's privacy tier."""
    return {
        "tier": current_entity.privacy_tier.value,
        "options": [t.value for t in PrivacyTier],
    }


@router.put("/privacy", dependencies=[Depends(rate_limit_writes)])
async def set_privacy_tier(
    body: SetPrivacyTierRequest,
    request: Request,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Set the entity's privacy tier."""
    new_tier = PrivacyTier(body.tier)
    old_tier = current_entity.privacy_tier
    current_entity.privacy_tier = new_tier
    await db.flush()

    await log_action(
        db,
        action="account.privacy_change",
        entity_id=current_entity.id,
        details={
            "old_tier": old_tier.value,
            "new_tier": new_tier.value,
        },
        ip_address=request.client.host if request.client else None,
    )

    return {
        "message": f"Privacy tier changed to '{new_tier.value}'",
        "tier": new_tier.value,
    }


@router.get(
    "/audit-log",
    response_model=AuditLogListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_audit_log(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get audit log entries for the current entity."""
    total = await db.scalar(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.entity_id == current_entity.id,
        )
    ) or 0

    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.entity_id == current_entity.id)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    entries = result.scalars().all()

    return AuditLogListResponse(
        entries=[
            AuditLogResponse(
                id=e.id,
                action=e.action,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                details=e.details or {},
                ip_address=e.ip_address,
                created_at=e.created_at.isoformat(),
            )
            for e in entries
        ],
        total=total,
    )
