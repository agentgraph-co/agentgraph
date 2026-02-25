"""Safety router - admin-only emergency endpoints for propagation control.

Provides endpoints to activate/deactivate propagation freeze,
quarantine/release entities, and broadcast network alerts.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, require_admin
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.database import get_db
from src.models import Entity

router = APIRouter(prefix="/admin/safety", tags=["safety"])


# --- Request/Response schemas ---


class FreezeRequest(BaseModel):
    active: bool
    reason: str = Field(..., min_length=1, max_length=1000)


class FreezeStatusResponse(BaseModel):
    frozen: bool
    since: str | None = None


class QuarantineRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


class QuarantineResponse(BaseModel):
    entity_id: uuid.UUID
    is_quarantined: bool
    reason: str


class AlertRequest(BaseModel):
    alert_type: str = Field(..., min_length=1, max_length=50)
    message: str = Field(..., min_length=1, max_length=2000)
    severity: str = Field(..., min_length=1, max_length=20)

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        valid = {"info", "warning", "critical"}
        if v not in valid:
            raise ValueError(f"severity must be one of {valid}")
        return v


class AlertResponse(BaseModel):
    id: uuid.UUID
    alert_type: str
    severity: str
    message: str
    issued_by: uuid.UUID | None
    is_resolved: bool
    resolved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Freeze endpoints ---


@router.post(
    "/freeze",
    response_model=FreezeStatusResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def activate_freeze(
    body: FreezeRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Activate or deactivate propagation freeze. Admin only."""
    require_admin(current_entity)

    from src.safety.emergency import broadcast_network_alert
    from src.safety.propagation import set_propagation_freeze

    await set_propagation_freeze(body.active)

    action = "activated" if body.active else "deactivated"
    await broadcast_network_alert(
        db,
        alert_type="freeze",
        message=f"Propagation freeze {action}: {body.reason}",
        severity="critical" if body.active else "info",
        issued_by=current_entity.id,
    )

    return FreezeStatusResponse(
        frozen=body.active,
        since=datetime.utcnow().isoformat() if body.active else None,
    )


@router.get(
    "/freeze",
    response_model=FreezeStatusResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def freeze_status(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Check current propagation freeze status. Admin only."""
    require_admin(current_entity)

    from src.safety.propagation import is_propagation_frozen

    frozen = await is_propagation_frozen()
    return FreezeStatusResponse(frozen=frozen, since=None)


# --- Quarantine endpoints ---


@router.post(
    "/quarantine/{entity_id}",
    response_model=QuarantineResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def quarantine_entity_endpoint(
    entity_id: uuid.UUID,
    body: QuarantineRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Quarantine an entity. Admin only."""
    require_admin(current_entity)

    target = await db.get(Entity, entity_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    from src.safety.emergency import broadcast_network_alert
    from src.safety.propagation import quarantine_entity

    await quarantine_entity(db, entity_id, body.reason)

    await broadcast_network_alert(
        db,
        alert_type="quarantine",
        message=f"Entity {entity_id} quarantined: {body.reason}",
        severity="warning",
        issued_by=current_entity.id,
    )

    return QuarantineResponse(
        entity_id=entity_id,
        is_quarantined=True,
        reason=body.reason,
    )


@router.delete(
    "/quarantine/{entity_id}",
    response_model=QuarantineResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def release_quarantine_endpoint(
    entity_id: uuid.UUID,
    body: QuarantineRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Release an entity from quarantine. Admin only."""
    require_admin(current_entity)

    target = await db.get(Entity, entity_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    from src.safety.emergency import broadcast_network_alert
    from src.safety.propagation import release_quarantine

    await release_quarantine(db, entity_id, body.reason)

    await broadcast_network_alert(
        db,
        alert_type="quarantine",
        message=f"Entity {entity_id} released from quarantine: {body.reason}",
        severity="info",
        issued_by=current_entity.id,
    )

    return QuarantineResponse(
        entity_id=entity_id,
        is_quarantined=False,
        reason=body.reason,
    )


# --- Alert endpoints ---


@router.post(
    "/alert",
    response_model=AlertResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def create_alert(
    body: AlertRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Broadcast a network alert. Admin only."""
    require_admin(current_entity)

    from src.safety.emergency import broadcast_network_alert

    alert = await broadcast_network_alert(
        db,
        alert_type=body.alert_type,
        message=body.message,
        severity=body.severity,
        issued_by=current_entity.id,
    )

    return AlertResponse.model_validate(alert)


@router.get(
    "/alerts",
    dependencies=[Depends(rate_limit_reads)],
)
async def list_alerts(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List recent propagation alerts. Admin only."""
    require_admin(current_entity)

    from src.safety.emergency import count_alerts, get_recent_alerts

    total = await count_alerts(db)
    alerts = await get_recent_alerts(db, limit=limit, offset=offset)
    return {
        "alerts": [AlertResponse.model_validate(a) for a in alerts],
        "total": total,
    }
