"""Account management endpoints.

Provides password change, account deactivation, and audit log
access for the authenticated entity.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.api.auth_service import hash_password, verify_password
from src.api.deactivation import cascade_deactivate
from src.api.deps import get_current_entity, require_scope
from src.api.rate_limit import rate_limit_auth, rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.config import settings
from src.database import get_db
from src.models import AuditLog, Entity, PrivacyTier

router = APIRouter(prefix="/account", tags=["account"])


# --- Schemas ---


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        from src.api.schemas import validate_password_strength

        return validate_password_strength(v)


class SetPrivacyTierRequest(BaseModel):
    tier: str = Field(
        ..., pattern="^(public|verified|private)$",
    )


class TrustWeightsRequest(BaseModel):
    verification: float = Field(0.35, ge=0.0, le=1.0)
    age: float = Field(0.10, ge=0.0, le=1.0)
    activity: float = Field(0.20, ge=0.0, le=1.0)
    reputation: float = Field(0.15, ge=0.0, le=1.0)
    community: float = Field(0.20, ge=0.0, le=1.0)


class TrustWeightsResponse(BaseModel):
    verification: float
    age: float
    activity: float
    reputation: float
    community: float
    is_custom: bool = False


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


@router.post(
    "/change-password",
    dependencies=[Depends(rate_limit_auth), require_scope("account:password")],
)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password.

    Invalidates all existing tokens (access + refresh) for this entity.
    """
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

    # 1) Blacklist the current access token by JTI (immediate, exact)
    from datetime import datetime, timezone

    from src.api.auth_service import blacklist_token, decode_token

    auth_header = request.headers.get("Authorization", "")
    token_str = auth_header.replace("Bearer ", "")
    payload = decode_token(token_str)
    if payload and payload.get("jti"):
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        await blacklist_token(db, payload["jti"], current_entity.id, exp)

    # 2) Invalidate all other tokens via Redis timestamp.
    # Tokens with iat <= this value are rejected in deps.py and refresh.
    import time

    from src import cache

    await cache.set(
        f"token:inv:{current_entity.id}",
        int(time.time()),
        ttl=settings.jwt_refresh_token_expire_days * 86400,
    )

    await log_action(
        db,
        action="auth.password_change",
        entity_id=current_entity.id,
        ip_address=request.client.host if request.client else None,
    )

    return {"message": "Password changed successfully. All sessions have been invalidated."}


@router.post(
    "/deactivate",
    dependencies=[Depends(rate_limit_writes), require_scope("account:deactivate")],
)
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

    # Invalidate search cache — deactivated entities/posts must not appear
    from src import cache
    await cache.invalidate_pattern("search:*")

    return {
        "message": "Account deactivated",
        "cascade": cascade,
    }


@router.get("/privacy", dependencies=[Depends(rate_limit_reads)])
async def get_privacy_tier(
    current_entity: Entity = Depends(get_current_entity),
):
    """Get the current entity's privacy tier."""
    return {
        "tier": current_entity.privacy_tier.value,
        "options": [t.value for t in PrivacyTier],
    }


@router.put("/privacy", dependencies=[Depends(rate_limit_writes), require_scope("account:update")])
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
                created_at=e.created_at.isoformat() if e.created_at else None,
            )
            for e in entries
        ],
        total=total,
    )


# --- Trust Weights ---


_DEFAULT_TRUST_WEIGHTS = {
    "verification": 0.35,
    "age": 0.10,
    "activity": 0.20,
    "reputation": 0.15,
    "community": 0.20,
}


@router.get(
    "/trust-weights",
    response_model=TrustWeightsResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_trust_weights(
    current_entity: Entity = Depends(get_current_entity),
):
    """Get the current user's custom trust weights (or defaults)."""
    data = current_entity.onboarding_data or {}
    custom = data.get("trust_weights")
    if custom:
        return TrustWeightsResponse(
            verification=custom.get("verification", _DEFAULT_TRUST_WEIGHTS["verification"]),
            age=custom.get("age", _DEFAULT_TRUST_WEIGHTS["age"]),
            activity=custom.get("activity", _DEFAULT_TRUST_WEIGHTS["activity"]),
            reputation=custom.get("reputation", _DEFAULT_TRUST_WEIGHTS["reputation"]),
            community=custom.get("community", _DEFAULT_TRUST_WEIGHTS["community"]),
            is_custom=True,
        )
    return TrustWeightsResponse(**_DEFAULT_TRUST_WEIGHTS, is_custom=False)


@router.put(
    "/trust-weights",
    response_model=TrustWeightsResponse,
    dependencies=[Depends(rate_limit_writes), require_scope("account:update")],
)
async def set_trust_weights(
    body: TrustWeightsRequest,
    request: Request,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Save custom trust weights. Weights must sum to approximately 1.0 (+-0.05)."""
    total = body.verification + body.age + body.activity + body.reputation + body.community
    if abs(total - 1.0) > 0.05:
        raise HTTPException(
            status_code=422,
            detail=f"Weights must sum to ~1.0 (got {total:.4f})",
        )

    weights = {
        "verification": body.verification,
        "age": body.age,
        "activity": body.activity,
        "reputation": body.reputation,
        "community": body.community,
    }

    new_data = dict(current_entity.onboarding_data or {})
    new_data["trust_weights"] = weights
    current_entity.onboarding_data = new_data
    await db.flush()
    await db.refresh(current_entity)

    await log_action(
        db,
        action="account.trust_weights_update",
        entity_id=current_entity.id,
        details={"weights": weights},
        ip_address=request.client.host if request.client else None,
    )

    return TrustWeightsResponse(**weights, is_custom=True)


@router.delete(
    "/trust-weights",
    response_model=TrustWeightsResponse,
    dependencies=[Depends(rate_limit_writes), require_scope("account:update")],
)
async def reset_trust_weights(
    request: Request,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Reset trust weights to defaults."""
    new_data = dict(current_entity.onboarding_data or {})
    new_data.pop("trust_weights", None)
    current_entity.onboarding_data = new_data
    await db.flush()
    await db.refresh(current_entity)

    await log_action(
        db,
        action="account.trust_weights_reset",
        entity_id=current_entity.id,
        ip_address=request.client.host if request.client else None,
    )

    return TrustWeightsResponse(**_DEFAULT_TRUST_WEIGHTS, is_custom=False)
