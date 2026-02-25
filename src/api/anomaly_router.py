"""Anomaly detection API endpoints.

Provides endpoints to list, inspect, scan for, and resolve anomaly alerts.
Admin users see all alerts; regular users see only their own.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, require_admin
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.database import get_db
from src.models import AnomalyAlert, Entity

router = APIRouter(tags=["anomalies"])


# --- Schemas ---


class AnomalyAlertResponse(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    alert_type: str
    severity: str
    z_score: float
    details: dict | None = None
    is_resolved: bool
    resolved_by: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnomalyScanResponse(BaseModel):
    trust_velocity_alerts: int
    relationship_churn_alerts: int
    cluster_anomaly_alerts: int
    total_alerts: int
    duration_seconds: float


class ResolveResponse(BaseModel):
    id: uuid.UUID
    is_resolved: bool
    resolved_by: uuid.UUID
    resolved_at: datetime

    model_config = {"from_attributes": True}


# --- Helpers ---


# --- Endpoints ---


@router.get(
    "/anomalies",
    response_model=list[AnomalyAlertResponse],
    dependencies=[Depends(rate_limit_reads)],
)
async def list_anomalies(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[AnomalyAlertResponse]:
    """List anomaly alerts.

    Admin users see all alerts. Regular users see only their own.
    """
    query = select(AnomalyAlert)

    if not current_entity.is_admin:
        query = query.where(AnomalyAlert.entity_id == current_entity.id)

    query = (
        query.order_by(AnomalyAlert.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(query)
    alerts = result.scalars().all()
    return [AnomalyAlertResponse.model_validate(a) for a in alerts]


@router.get(
    "/anomalies/{entity_id}",
    response_model=list[AnomalyAlertResponse],
    dependencies=[Depends(rate_limit_reads)],
)
async def get_entity_anomalies(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[AnomalyAlertResponse]:
    """Get anomaly alerts for a specific entity.

    Admin users can view any entity. Regular users can only view their own.
    """
    if not current_entity.is_admin and current_entity.id != entity_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify entity exists
    target = await db.get(Entity, entity_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    query = (
        select(AnomalyAlert)
        .where(AnomalyAlert.entity_id == entity_id)
        .order_by(AnomalyAlert.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(query)
    alerts = result.scalars().all()
    return [AnomalyAlertResponse.model_validate(a) for a in alerts]


@router.post(
    "/admin/anomalies/scan",
    response_model=AnomalyScanResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def trigger_anomaly_scan(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> AnomalyScanResponse:
    """Trigger a manual anomaly scan. Admin only."""
    require_admin(current_entity)

    from src.jobs.anomaly_scan import run_anomaly_scan

    summary = await run_anomaly_scan(db, auto_flag=True)
    return AnomalyScanResponse(**summary)


@router.patch(
    "/admin/anomalies/{alert_id}/resolve",
    response_model=ResolveResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def resolve_anomaly_alert(
    alert_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> ResolveResponse:
    """Resolve an anomaly alert. Admin only."""
    require_admin(current_entity)

    alert = await db.get(AnomalyAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.is_resolved:
        raise HTTPException(status_code=409, detail="Alert already resolved")

    from datetime import timezone

    alert.is_resolved = True
    alert.resolved_by = current_entity.id
    alert.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(alert)

    return ResolveResponse.model_validate(alert)
