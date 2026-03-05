from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, require_admin
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import (
    AuditLog,
    Entity,
    EntityRelationship,
    EvolutionRecord,
    ModerationFlag,
    ModerationStatus,
    Post,
    TrustScore,
)

router = APIRouter(prefix="/compliance", tags=["compliance"])


# --- Schemas ---


class ReportType(str, Enum):
    GDPR = "gdpr"
    SOC2 = "soc2"
    SUMMARY = "summary"


class AuditReportResponse(BaseModel):
    report_type: str
    start_date: str
    end_date: str
    total_entities: int
    active_entities: int
    inactive_entities: int
    deactivated_entities: int
    total_posts: int
    total_evolution_records: int
    moderation_actions_taken: int
    data_deletion_requests: int
    security_incidents: int
    active_admin_accounts: int
    generated_at: str


class DataRetentionResponse(BaseModel):
    entity_id: str
    posts_retention_days: int | None
    audit_log_retention_days: int
    inactive_account_policy_days: int
    entity_data_categories: list[str]


class DataDeletionRequestResponse(BaseModel):
    request_id: str
    entity_id: str
    status: str
    estimated_processing_days: int
    created_at: str


class ConsentRecordResponse(BaseModel):
    entity_id: str
    tos_agreed_at: str
    tos_version: str
    privacy_policy_version: str
    data_processing_consent: bool
    marketing_consent: bool


class DataExportResponse(BaseModel):
    entity_id: str
    profile: dict
    posts: list[dict]
    relationships: list[dict]
    trust_score: dict | None
    evolution_records: list[dict]
    audit_logs: list[dict]
    exported_at: str


# --- Endpoints ---


@router.get("/audit-report", response_model=AuditReportResponse)
async def get_audit_report(
    start_date: date = Query(..., description="Report start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Report end date (YYYY-MM-DD)"),
    report_type: ReportType = Query(
        ReportType.SUMMARY, description="Report type: gdpr, soc2, or summary"
    ),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit_reads),
):
    """Generate a compliance audit report. Admin-only."""
    require_admin(current_entity)

    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be before or equal to end_date",
        )

    start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
    end_dt = datetime(
        end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc
    )

    # Total entities (all)
    total_entities = await db.scalar(select(func.count(Entity.id))) or 0

    # Active entities
    active_entities = await db.scalar(
        select(func.count(Entity.id)).where(Entity.is_active.is_(True))
    ) or 0

    # Inactive entities (not active but not deactivated/quarantined distinction)
    inactive_entities = total_entities - active_entities

    # Deactivated = not active (same count for now; the system marks deactivated as is_active=False)
    deactivated_entities = inactive_entities

    # Posts in date range
    total_posts = await db.scalar(
        select(func.count(Post.id)).where(
            Post.created_at >= start_dt,
            Post.created_at <= end_dt,
        )
    ) or 0

    # Evolution records in date range
    total_evolution_records = await db.scalar(
        select(func.count(EvolutionRecord.id)).where(
            EvolutionRecord.created_at >= start_dt,
            EvolutionRecord.created_at <= end_dt,
        )
    ) or 0

    # Moderation actions (resolved flags in date range)
    moderation_actions = await db.scalar(
        select(func.count(ModerationFlag.id)).where(
            ModerationFlag.status != ModerationStatus.PENDING,
            ModerationFlag.created_at >= start_dt,
            ModerationFlag.created_at <= end_dt,
        )
    ) or 0

    # Data deletion requests (moderation flags with details containing 'data_deletion_request')
    data_deletion_requests = await db.scalar(
        select(func.count(ModerationFlag.id)).where(
            ModerationFlag.details.ilike("%data_deletion_request%"),
            ModerationFlag.created_at >= start_dt,
            ModerationFlag.created_at <= end_dt,
        )
    ) or 0

    # Security incidents (flagged items in date range)
    security_incidents = await db.scalar(
        select(func.count(ModerationFlag.id)).where(
            ModerationFlag.created_at >= start_dt,
            ModerationFlag.created_at <= end_dt,
        )
    ) or 0

    # Active admin accounts
    active_admins = await db.scalar(
        select(func.count(Entity.id)).where(
            Entity.is_admin.is_(True),
            Entity.is_active.is_(True),
        )
    ) or 0

    await log_action(
        db,
        action="compliance.audit_report",
        entity_id=current_entity.id,
        details={
            "report_type": report_type.value,
            "start_date": str(start_date),
            "end_date": str(end_date),
        },
    )

    return AuditReportResponse(
        report_type=report_type.value,
        start_date=str(start_date),
        end_date=str(end_date),
        total_entities=total_entities,
        active_entities=active_entities,
        inactive_entities=inactive_entities,
        deactivated_entities=deactivated_entities,
        total_posts=total_posts,
        total_evolution_records=total_evolution_records,
        moderation_actions_taken=moderation_actions,
        data_deletion_requests=data_deletion_requests,
        security_incidents=security_incidents,
        active_admin_accounts=active_admins,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/data-retention", response_model=DataRetentionResponse)
async def get_data_retention(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit_reads),
):
    """Return current data retention policy and status for the requesting entity."""
    return DataRetentionResponse(
        entity_id=str(current_entity.id),
        posts_retention_days=None,  # forever by default
        audit_log_retention_days=365,
        inactive_account_policy_days=730,
        entity_data_categories=[
            "profile_information",
            "posts_and_comments",
            "social_relationships",
            "trust_scores",
            "evolution_records",
            "audit_logs",
            "moderation_history",
            "api_keys_metadata",
            "did_documents",
            "webhook_subscriptions",
        ],
    )


@router.post("/data-deletion-request", response_model=DataDeletionRequestResponse)
async def create_data_deletion_request(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit_writes),
):
    """GDPR right-to-erasure request.

    Creates a deletion request record using the moderation_flags table.
    """
    flag = ModerationFlag(
        id=uuid.uuid4(),
        reporter_entity_id=current_entity.id,
        target_type="entity",
        target_id=current_entity.id,
        reason="other",
        details="data_deletion_request",
        status=ModerationStatus.PENDING,
    )
    db.add(flag)
    await db.flush()

    await log_action(
        db,
        action="compliance.data_deletion_request",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=current_entity.id,
        details={"request_id": str(flag.id)},
    )

    return DataDeletionRequestResponse(
        request_id=str(flag.id),
        entity_id=str(current_entity.id),
        status="pending",
        estimated_processing_days=30,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/consent-records", response_model=ConsentRecordResponse)
async def get_consent_records(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit_reads),
):
    """Return consent records for the current entity.

    Currently returns static consent info based on account creation date.
    """
    return ConsentRecordResponse(
        entity_id=str(current_entity.id),
        tos_agreed_at=current_entity.created_at.isoformat(),
        tos_version="1.0",
        privacy_policy_version="1.0",
        data_processing_consent=True,
        marketing_consent=False,
    )


@router.get("/data-export", response_model=DataExportResponse)
async def get_data_export(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit_reads),
):
    """Export all personal data for the requesting entity (GDPR data portability).

    Returns profile info, posts, relationships, trust scores, evolution records,
    and audit logs serialized as JSON.
    """
    # Profile info
    profile = {
        "id": str(current_entity.id),
        "type": current_entity.type.value if current_entity.type else None,
        "email": current_entity.email,
        "display_name": current_entity.display_name,
        "bio_markdown": current_entity.bio_markdown,
        "avatar_url": current_entity.avatar_url,
        "did_web": current_entity.did_web,
        "capabilities": current_entity.capabilities,
        "autonomy_level": current_entity.autonomy_level,
        "privacy_tier": (
            current_entity.privacy_tier.value if current_entity.privacy_tier else None
        ),
        "is_active": current_entity.is_active,
        "created_at": current_entity.created_at.isoformat(),
        "updated_at": current_entity.updated_at.isoformat(),
    }

    # Posts
    posts_result = await db.execute(
        select(Post).where(Post.author_entity_id == current_entity.id)
    )
    posts = [
        {
            "id": str(p.id),
            "content": p.content,
            "created_at": p.created_at.isoformat(),
            "is_hidden": p.is_hidden,
            "is_edited": p.is_edited,
        }
        for p in posts_result.scalars().all()
    ]

    # Relationships (where entity is source or target)
    rels_result = await db.execute(
        select(EntityRelationship).where(
            (EntityRelationship.source_entity_id == current_entity.id)
            | (EntityRelationship.target_entity_id == current_entity.id)
        )
    )
    relationships = [
        {
            "id": str(r.id),
            "source_entity_id": str(r.source_entity_id),
            "target_entity_id": str(r.target_entity_id),
            "type": r.type.value if r.type else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in rels_result.scalars().all()
    ]

    # Trust score
    ts_result = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == current_entity.id)
    )
    trust_score = None
    if ts_result:
        trust_score = {
            "score": ts_result.score,
            "components": ts_result.components,
            "computed_at": ts_result.computed_at.isoformat(),
        }

    # Evolution records
    evo_result = await db.execute(
        select(EvolutionRecord).where(EvolutionRecord.entity_id == current_entity.id)
    )
    evolution_records = [
        {
            "id": str(e.id),
            "version": e.version,
            "change_type": e.change_type,
            "change_summary": e.change_summary,
            "created_at": e.created_at.isoformat(),
        }
        for e in evo_result.scalars().all()
    ]

    # Audit logs
    audit_result = await db.execute(
        select(AuditLog).where(AuditLog.entity_id == current_entity.id)
    )
    audit_logs = [
        {
            "id": str(a.id),
            "action": a.action,
            "resource_type": a.resource_type,
            "details": a.details,
            "created_at": a.created_at.isoformat(),
        }
        for a in audit_result.scalars().all()
    ]

    await log_action(
        db,
        action="compliance.data_export",
        entity_id=current_entity.id,
        details={"export_type": "full"},
    )

    return DataExportResponse(
        entity_id=str(current_entity.id),
        profile=profile,
        posts=posts,
        relationships=relationships,
        trust_score=trust_score,
        evolution_records=evolution_records,
        audit_logs=audit_logs,
        exported_at=datetime.now(timezone.utc).isoformat(),
    )
