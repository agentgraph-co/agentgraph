from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, require_admin
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import (
    AuditRecord,
    Entity,
    TrustScore,
    VerificationBadge,
)
from src.ssrf import validate_url_https_optional

logger = logging.getLogger(__name__)

router = APIRouter(tags=["badges"])

VALID_BADGE_TYPES = {
    "email_verified",
    "identity_verified",
    "capability_audited",
    "agentgraph_verified",
}

VALID_AUDIT_TYPES = {"security", "capability", "compliance"}
VALID_AUDIT_RESULTS = {"pass", "fail", "partial"}

AUDITOR_TRUST_THRESHOLD = 0.7


# --- Schemas ---


class BadgeResponse(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    badge_type: str
    issued_by: uuid.UUID | None = None
    issued_by_display_name: str | None = None
    proof_url: str | None = None
    expires_at: datetime | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class BadgeListResponse(BaseModel):
    badges: list[BadgeResponse]
    total: int

class CreateBadgeRequest(BaseModel):
    badge_type: str = Field(
        ..., pattern=r"^(email_verified|identity_verified|capability_audited|agentgraph_verified)$",
    )
    proof_url: str | None = Field(None, max_length=1000)
    expires_at: datetime | None = None

    @field_validator("proof_url")
    @classmethod
    def check_proof_url(cls, v: str | None) -> str | None:
        return validate_url_https_optional(v, field_name="proof_url")


class AuditRecordResponse(BaseModel):
    id: uuid.UUID
    target_entity_id: uuid.UUID
    auditor_entity_id: uuid.UUID
    auditor_display_name: str = ""
    audit_type: str
    result: str
    findings: dict | None = None
    report_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditRecordListResponse(BaseModel):
    audit_records: list[AuditRecordResponse]
    total: int


class CreateAuditRecordRequest(BaseModel):
    audit_type: str = Field(
        ..., pattern=r"^(security|capability|compliance)$",
    )
    result: str = Field(
        ..., pattern=r"^(pass|fail|partial)$",
    )
    findings: dict | None = None
    report_url: str | None = Field(None, max_length=1000)

    @field_validator("report_url")
    @classmethod
    def check_report_url(cls, v: str | None) -> str | None:
        return validate_url_https_optional(v, field_name="report_url")



# --- Badge Endpoints ---


@router.get(
    "/entities/{entity_id}/badges",
    response_model=BadgeListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_badges(
    entity_id: uuid.UUID,
    include_expired: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List verification badges for an entity."""
    target = await db.get(Entity, entity_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    query = select(VerificationBadge).where(
        VerificationBadge.entity_id == entity_id,
    )

    if not include_expired:
        query = query.where(VerificationBadge.is_active.is_(True))

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Fetch with issuer display name
    full_query = (
        select(VerificationBadge, Entity.display_name)
        .outerjoin(Entity, VerificationBadge.issued_by == Entity.id)
        .where(VerificationBadge.entity_id == entity_id)
    )
    if not include_expired:
        full_query = full_query.where(VerificationBadge.is_active.is_(True))

    full_query = (
        full_query.order_by(VerificationBadge.created_at.desc())
        .limit(limit).offset(offset)
    )
    result = await db.execute(full_query)

    badges = []
    now = datetime.now(timezone.utc)
    for badge, issuer_name in result.all():
        is_expired = badge.expires_at is not None and badge.expires_at < now
        badges.append(BadgeResponse(
            id=badge.id,
            entity_id=badge.entity_id,
            badge_type=badge.badge_type,
            issued_by=badge.issued_by,
            issued_by_display_name=issuer_name,
            proof_url=badge.proof_url,
            expires_at=badge.expires_at,
            is_active=badge.is_active and not is_expired,
            created_at=badge.created_at,
        ))

    return BadgeListResponse(badges=badges, total=total)


@router.post(
    "/entities/{entity_id}/badges",
    response_model=BadgeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_writes)],
)
async def issue_badge(
    entity_id: uuid.UUID,
    body: CreateBadgeRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Issue a verification badge to an entity (admin only)."""
    require_admin(current_entity)

    target = await db.get(Entity, entity_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    if body.badge_type not in VALID_BADGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid badge_type. Must be one of: {', '.join(sorted(VALID_BADGE_TYPES))}",
        )

    existing = await db.scalar(
        select(VerificationBadge).where(
            VerificationBadge.entity_id == entity_id,
            VerificationBadge.badge_type == body.badge_type,
            VerificationBadge.is_active.is_(True),
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Entity already has an active '{body.badge_type}' badge",
        )

    badge = VerificationBadge(
        id=uuid.uuid4(),
        entity_id=entity_id,
        badge_type=body.badge_type,
        issued_by=current_entity.id,
        proof_url=body.proof_url,
        expires_at=body.expires_at,
        is_active=True,
    )
    db.add(badge)
    await db.flush()

    await log_action(
        db,
        action="badge.issue",
        entity_id=current_entity.id,
        resource_type="verification_badge",
        resource_id=badge.id,
        details={
            "target_entity_id": str(entity_id),
            "badge_type": body.badge_type,
        },
    )

    try:
        from src.api.notification_router import create_notification
        await create_notification(
            db,
            entity_id=entity_id,
            kind="badge",
            title="Verification badge issued",
            body=f"You received a '{body.badge_type}' verification badge",
            reference_id=str(badge.id),
        )
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return BadgeResponse(
        id=badge.id,
        entity_id=badge.entity_id,
        badge_type=badge.badge_type,
        issued_by=badge.issued_by,
        issued_by_display_name=current_entity.display_name,
        proof_url=badge.proof_url,
        expires_at=badge.expires_at,
        is_active=badge.is_active,
        created_at=badge.created_at,
    )


@router.patch(
    "/entities/{entity_id}/badges/{badge_id}/deactivate",
    response_model=BadgeResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def deactivate_badge(
    entity_id: uuid.UUID,
    badge_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a verification badge (admin only)."""
    require_admin(current_entity)

    badge = await db.get(VerificationBadge, badge_id)
    if badge is None or badge.entity_id != entity_id:
        raise HTTPException(status_code=404, detail="Badge not found")

    badge.is_active = False
    await db.flush()
    await db.refresh(badge)

    await log_action(
        db,
        action="badge.deactivate",
        entity_id=current_entity.id,
        resource_type="verification_badge",
        resource_id=badge.id,
        details={
            "target_entity_id": str(entity_id),
            "badge_type": badge.badge_type,
        },
    )

    return BadgeResponse(
        id=badge.id,
        entity_id=badge.entity_id,
        badge_type=badge.badge_type,
        issued_by=badge.issued_by,
        issued_by_display_name=None,
        proof_url=badge.proof_url,
        expires_at=badge.expires_at,
        is_active=badge.is_active,
        created_at=badge.created_at,
    )



# --- Audit Record Endpoints ---


@router.post(
    "/entities/{entity_id}/audit",
    response_model=AuditRecordResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_writes)],
)
async def submit_audit_record(
    entity_id: uuid.UUID,
    body: CreateAuditRecordRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Submit an audit record for an entity. Only entities with trust > 0.7 can audit."""
    if current_entity.id == entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot audit yourself",
        )

    target = await db.get(Entity, entity_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    auditor_ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == current_entity.id)
    )
    auditor_score = auditor_ts.score if auditor_ts else 0.0
    if auditor_score < AUDITOR_TRUST_THRESHOLD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Auditor trust score ({auditor_score:.2f})"
                f" must be >= {AUDITOR_TRUST_THRESHOLD}"
            ),
        )

    if body.audit_type not in VALID_AUDIT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid audit_type. Must be one of: {', '.join(sorted(VALID_AUDIT_TYPES))}",
        )

    if body.result not in VALID_AUDIT_RESULTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid result. Must be one of: {', '.join(sorted(VALID_AUDIT_RESULTS))}",
        )

    audit_record = AuditRecord(
        id=uuid.uuid4(),
        target_entity_id=entity_id,
        auditor_entity_id=current_entity.id,
        audit_type=body.audit_type,
        result=body.result,
        findings=body.findings,
        report_url=body.report_url,
    )
    db.add(audit_record)
    await db.flush()

    await log_action(
        db,
        action="audit.submit",
        entity_id=current_entity.id,
        resource_type="audit_record",
        resource_id=audit_record.id,
        details={
            "target_entity_id": str(entity_id),
            "audit_type": body.audit_type,
            "result": body.result,
        },
    )

    if body.result == "pass" and body.audit_type == "capability":
        from src.models import CapabilityEndorsement
        endorsement_result = await db.execute(
            select(CapabilityEndorsement).where(
                CapabilityEndorsement.agent_entity_id == entity_id,
                CapabilityEndorsement.tier != "formally_audited",
            )
        )
        for endorsement in endorsement_result.scalars().all():
            endorsement.tier = "formally_audited"
        await db.flush()

    try:
        from src.api.notification_router import create_notification
        await create_notification(
            db,
            entity_id=entity_id,
            kind="audit",
            title="Audit completed",
            body=f"Your entity was audited ({body.audit_type}): {body.result}",
            reference_id=str(audit_record.id),
        )
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return AuditRecordResponse(
        id=audit_record.id,
        target_entity_id=audit_record.target_entity_id,
        auditor_entity_id=audit_record.auditor_entity_id,
        auditor_display_name=current_entity.display_name,
        audit_type=audit_record.audit_type,
        result=audit_record.result,
        findings=audit_record.findings,
        report_url=audit_record.report_url,
        created_at=audit_record.created_at,
    )


@router.get(
    "/entities/{entity_id}/audit-history",
    response_model=AuditRecordListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_audit_records(
    entity_id: uuid.UUID,
    audit_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List audit records for an entity."""
    target = await db.get(Entity, entity_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    base_query = select(AuditRecord).where(
        AuditRecord.target_entity_id == entity_id,
    )
    if audit_type and audit_type in VALID_AUDIT_TYPES:
        base_query = base_query.where(AuditRecord.audit_type == audit_type)

    count_query = select(func.count()).select_from(base_query.subquery())
    total = await db.scalar(count_query) or 0

    full_query = (
        select(AuditRecord, Entity.display_name)
        .join(Entity, AuditRecord.auditor_entity_id == Entity.id)
        .where(AuditRecord.target_entity_id == entity_id)
    )
    if audit_type and audit_type in VALID_AUDIT_TYPES:
        full_query = full_query.where(AuditRecord.audit_type == audit_type)

    full_query = full_query.order_by(
        AuditRecord.created_at.desc(),
    ).offset(offset).limit(limit)

    result = await db.execute(full_query)

    audit_records = []
    for record, auditor_name in result.all():
        audit_records.append(AuditRecordResponse(
            id=record.id,
            target_entity_id=record.target_entity_id,
            auditor_entity_id=record.auditor_entity_id,
            auditor_display_name=auditor_name,
            audit_type=record.audit_type,
            result=record.result,
            findings=record.findings,
            report_url=record.report_url,
            created_at=record.created_at,
        ))

    return AuditRecordListResponse(audit_records=audit_records, total=total)
