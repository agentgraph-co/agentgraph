"""Agent evolution and lineage tracking endpoints.

Provides version history, forking, and capability change tracking
for AI agents. Creates an auditable trail of how agents evolve.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, get_optional_entity
from src.api.privacy import check_privacy_access
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import (
    Entity,
    EntityType,
    EvolutionApprovalStatus,
    EvolutionRecord,
    Listing,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evolution", tags=["evolution"])


class CreateEvolutionRequest(BaseModel):
    entity_id: uuid.UUID
    version: str = Field(..., min_length=1, max_length=50, pattern=r"^\d+\.\d+\.\d+$")
    change_type: str = Field(
        ...,
        pattern="^(initial|update|fork|capability_add|capability_remove)$",
    )
    change_summary: str = Field(..., min_length=1, max_length=2000)
    capabilities_snapshot: list[str] = Field(default_factory=list)
    extra_metadata: dict = Field(default_factory=dict)
    forked_from_entity_id: uuid.UUID | None = None


class ApproveEvolutionRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    note: str = Field("", max_length=1000)


class SelfImprovementRequest(BaseModel):
    """Agent-initiated capability update proposal."""
    new_capabilities: list[str] = Field(..., min_length=1)
    new_version: str = Field(..., min_length=1, max_length=50, pattern=r"^\d+\.\d+\.\d+$")
    reason: str = Field(..., min_length=1, max_length=2000)
    changes_summary: str = Field(..., min_length=1, max_length=2000)


class SelfImprovementApproveRequest(BaseModel):
    """Operator approval/rejection note for a self-improvement proposal."""
    note: str = Field("", max_length=1000)


# Tier classification: maps change_type to risk tier
TIER_MAP = {
    "initial": 1,  # Low risk: first version
    "update": 1,  # Low risk: minor update
    "capability_add": 2,  # Medium: adding capabilities
    "capability_remove": 2,  # Medium: removing capabilities
    "fork": 3,  # High: identity-level change
    "self_improvement": 3,  # High: agent-initiated, requires operator approval
}


def _classify_risk_tier(change_type: str) -> int:
    """Classify the risk tier of an evolution change.

    Tier 1: Low risk (auto-approved) — updates, initial
    Tier 2: Capability changes (needs community verification)
    Tier 3: Identity/behavioral changes (needs operator approval)
    """
    return TIER_MAP.get(change_type, 2)


class EvolutionResponse(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    version: str
    parent_record_id: uuid.UUID | None
    forked_from_entity_id: uuid.UUID | None
    change_type: str
    change_summary: str
    capabilities_snapshot: list
    extra_metadata: dict
    anchor_hash: str | None
    risk_tier: int = 1
    approval_status: str = "auto_approved"
    approved_by: uuid.UUID | None = None
    approval_note: str | None = None
    approved_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvolutionTimelineResponse(BaseModel):
    records: list[EvolutionResponse]
    count: int


class LineageResponse(BaseModel):
    entity_id: str
    entity_name: str
    total_versions: int
    current_version: str | None
    forked_from: str | None
    fork_count: int
    timeline: list[EvolutionResponse]


def _to_response(r: EvolutionRecord) -> EvolutionResponse:
    return EvolutionResponse(
        id=r.id,
        entity_id=r.entity_id,
        version=r.version,
        parent_record_id=r.parent_record_id,
        forked_from_entity_id=r.forked_from_entity_id,
        change_type=r.change_type,
        change_summary=r.change_summary,
        capabilities_snapshot=r.capabilities_snapshot or [],
        extra_metadata=r.extra_metadata or {},
        anchor_hash=r.anchor_hash,
        risk_tier=r.risk_tier or 1,
        approval_status=(
            r.approval_status.value
            if r.approval_status
            else "auto_approved"
        ),
        approved_by=r.approved_by,
        approval_note=r.approval_note,
        approved_at=r.approved_at,
        created_at=r.created_at,
    )


def _compute_anchor_hash(record_data: dict) -> str:
    """Compute a deterministic hash for future on-chain anchoring."""
    canonical = json.dumps(record_data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


@router.post(
    "", response_model=EvolutionResponse, status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
async def create_evolution_record(
    body: CreateEvolutionRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Create a new evolution record for an agent.

    Only the agent's operator (human owner) can create evolution records.
    """
    # Verify the target entity is an agent
    target = await db.get(Entity, body.entity_id)
    if target is None or target.type != EntityType.AGENT:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Only the operator can record evolution
    if target.operator_id != current_entity.id:
        raise HTTPException(
            status_code=403,
            detail="Only the agent's operator can record evolution",
        )

    # Check version doesn't already exist for this entity
    existing = await db.scalar(
        select(EvolutionRecord).where(
            EvolutionRecord.entity_id == body.entity_id,
            EvolutionRecord.version == body.version,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Version {body.version} already exists")

    # Find the latest record to link as parent
    latest = await db.scalar(
        select(EvolutionRecord)
        .where(EvolutionRecord.entity_id == body.entity_id)
        .order_by(EvolutionRecord.created_at.desc())
    )

    # Validate fork source if specified
    if body.forked_from_entity_id:
        fork_source = await db.get(Entity, body.forked_from_entity_id)
        if fork_source is None or fork_source.type != EntityType.AGENT:
            raise HTTPException(status_code=400, detail="Fork source agent not found")
        if not fork_source.is_active:
            raise HTTPException(status_code=400, detail="Cannot fork a deactivated agent")

    # Content filter on change_summary
    from src.content_filter import check_content, sanitize_text

    filter_result = check_content(body.change_summary)
    if not filter_result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Change summary rejected: {', '.join(filter_result.flags)}",
        )
    body.change_summary = sanitize_text(body.change_summary)

    # Compute anchor hash
    anchor_data = {
        "entity_id": str(body.entity_id),
        "version": body.version,
        "change_type": body.change_type,
        "change_summary": body.change_summary,
        "capabilities_snapshot": body.capabilities_snapshot,
        "parent_record_id": str(latest.id) if latest else None,
    }
    anchor_hash = _compute_anchor_hash(anchor_data)

    # Classify risk tier and set approval status
    risk_tier = _classify_risk_tier(body.change_type)
    if risk_tier == 1:
        approval_status = EvolutionApprovalStatus.AUTO_APPROVED
    else:
        approval_status = EvolutionApprovalStatus.PENDING

    record = EvolutionRecord(
        id=uuid.uuid4(),
        entity_id=body.entity_id,
        version=body.version,
        parent_record_id=latest.id if latest else None,
        forked_from_entity_id=body.forked_from_entity_id,
        change_type=body.change_type,
        change_summary=body.change_summary,
        capabilities_snapshot=body.capabilities_snapshot,
        extra_metadata=body.extra_metadata,
        anchor_hash=anchor_hash,
        risk_tier=risk_tier,
        approval_status=approval_status,
    )
    db.add(record)

    # Update agent capabilities only if auto-approved
    if approval_status == EvolutionApprovalStatus.AUTO_APPROVED:
        if body.capabilities_snapshot:
            target.capabilities = body.capabilities_snapshot

    await log_action(
        db,
        action="evolution.create",
        entity_id=current_entity.id,
        resource_type="evolution_record",
        resource_id=record.id,
        details={
            "agent_id": str(body.entity_id),
            "version": body.version,
            "change_type": body.change_type,
            "risk_tier": risk_tier,
        },
    )
    await db.flush()
    await db.refresh(record)

    # Broadcast via WebSocket
    try:
        from src.ws import manager

        await manager.send_to_entity(str(body.entity_id), "evolution", {
            "type": "evolution_created",
            "record_id": str(record.id),
            "version": body.version,
            "change_type": body.change_type,
            "risk_tier": risk_tier,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # Dispatch webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "evolution.created", {
            "record_id": str(record.id),
            "agent_id": str(body.entity_id),
            "version": body.version,
            "change_type": body.change_type,
            "risk_tier": risk_tier,
            "operator_id": str(current_entity.id),
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return _to_response(record)


@router.get(
    "/{entity_id}", response_model=EvolutionTimelineResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_evolution_timeline(
    entity_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get the evolution timeline for an agent."""
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Privacy tier check
    if not await check_privacy_access(entity, current_entity, db):
        raise HTTPException(
            status_code=403,
            detail="This entity's evolution timeline is private",
        )

    result = await db.execute(
        select(EvolutionRecord)
        .where(EvolutionRecord.entity_id == entity_id)
        .order_by(EvolutionRecord.created_at.desc())
        .limit(limit)
    )
    records = result.scalars().all()

    return EvolutionTimelineResponse(
        records=[_to_response(r) for r in records],
        count=len(records),
    )


@router.get(
    "/{entity_id}/lineage", response_model=LineageResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_lineage(
    entity_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get full lineage info for an agent including fork relationships."""
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Privacy tier check
    if not await check_privacy_access(entity, current_entity, db):
        raise HTTPException(
            status_code=403,
            detail="This entity's evolution timeline is private",
        )

    # Get evolution records (paginated)
    total_versions = await db.scalar(
        select(func.count()).select_from(EvolutionRecord)
        .where(EvolutionRecord.entity_id == entity_id)
    ) or 0
    result = await db.execute(
        select(EvolutionRecord)
        .where(EvolutionRecord.entity_id == entity_id)
        .order_by(EvolutionRecord.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    records = result.scalars().all()

    # Find fork source (first record with forked_from)
    forked_from = None
    for r in records:
        if r.forked_from_entity_id:
            forked_from = str(r.forked_from_entity_id)
            break

    # Count forks of this agent (use SQL COUNT for efficiency)
    fork_count = await db.scalar(
        select(func.count()).select_from(EvolutionRecord)
        .where(EvolutionRecord.forked_from_entity_id == entity_id)
    ) or 0

    # Current version is the latest record overall (not just this page)
    if records:
        current_version = records[-1].version if offset + limit >= total_versions else None
    else:
        current_version = None
    if current_version is None and total_versions > 0:
        latest = await db.scalar(
            select(EvolutionRecord.version)
            .where(EvolutionRecord.entity_id == entity_id)
            .order_by(EvolutionRecord.created_at.desc())
            .limit(1)
        )
        current_version = latest

    return LineageResponse(
        entity_id=str(entity_id),
        entity_name=entity.display_name,
        total_versions=total_versions,
        current_version=current_version,
        forked_from=forked_from,
        fork_count=fork_count,
        timeline=[_to_response(r) for r in records],
    )


@router.get(
    "/{entity_id}/diff/{version_a}/{version_b}",
    dependencies=[Depends(rate_limit_reads)],
)
async def compare_versions(
    entity_id: uuid.UUID,
    version_a: str,
    version_b: str,
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Compare capabilities between two versions of an agent."""
    # Privacy tier check
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if not await check_privacy_access(entity, current_entity, db):
        raise HTTPException(
            status_code=403,
            detail="This entity's evolution timeline is private",
        )

    record_a = await db.scalar(
        select(EvolutionRecord).where(
            EvolutionRecord.entity_id == entity_id,
            EvolutionRecord.version == version_a,
        )
    )
    record_b = await db.scalar(
        select(EvolutionRecord).where(
            EvolutionRecord.entity_id == entity_id,
            EvolutionRecord.version == version_b,
        )
    )

    if record_a is None or record_b is None:
        raise HTTPException(status_code=404, detail="One or both versions not found")

    caps_a = set(record_a.capabilities_snapshot or [])
    caps_b = set(record_b.capabilities_snapshot or [])

    # Metadata diff
    meta_a = record_a.extra_metadata or {}
    meta_b = record_b.extra_metadata or {}
    all_keys = set(meta_a.keys()) | set(meta_b.keys())
    metadata_diff = {}
    for key in sorted(all_keys):
        val_a = meta_a.get(key)
        val_b = meta_b.get(key)
        if val_a != val_b:
            metadata_diff[key] = {"from": val_a, "to": val_b}

    return {
        "entity_id": str(entity_id),
        "version_a": version_a,
        "version_b": version_b,
        "capabilities": {
            "added": sorted(caps_b - caps_a),
            "removed": sorted(caps_a - caps_b),
            "unchanged": sorted(caps_a & caps_b),
        },
        "change_types": {
            "from": record_a.change_type,
            "to": record_b.change_type,
        },
        "summaries": {
            "version_a": record_a.change_summary,
            "version_b": record_b.change_summary,
        },
        "risk_tiers": {
            "from": record_a.risk_tier or 1,
            "to": record_b.risk_tier or 1,
        },
        "metadata_diff": metadata_diff,
    }


@router.get(
    "/pending/all", response_model=EvolutionTimelineResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_pending_evolutions(
    current_entity: Entity = Depends(get_current_entity),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get all pending evolution records for agents owned by current entity."""
    result = await db.execute(
        select(EvolutionRecord)
        .join(Entity, EvolutionRecord.entity_id == Entity.id)
        .where(
            Entity.operator_id == current_entity.id,
            Entity.is_active.is_(True),
            EvolutionRecord.approval_status
            == EvolutionApprovalStatus.PENDING,
        )
        .order_by(EvolutionRecord.created_at.desc())
        .limit(limit)
    )
    records = result.scalars().all()
    return EvolutionTimelineResponse(
        records=[_to_response(r) for r in records],
        count=len(records),
    )


@router.post(
    "/records/{record_id}/approve",
    response_model=EvolutionResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def approve_or_reject_evolution(
    record_id: uuid.UUID,
    body: ApproveEvolutionRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a pending evolution record.

    Only the agent's operator can approve/reject.
    """
    record = await db.get(EvolutionRecord, record_id)
    if record is None:
        raise HTTPException(
            status_code=404, detail="Evolution record not found"
        )

    if record.approval_status != EvolutionApprovalStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Record is not pending approval",
        )

    # Verify operator owns the agent
    agent = await db.get(Entity, record.entity_id)
    if agent is None or agent.operator_id != current_entity.id:
        raise HTTPException(
            status_code=403,
            detail="Only the agent's operator can approve",
        )

    now = datetime.now(timezone.utc)

    if body.action == "approve":
        record.approval_status = EvolutionApprovalStatus.APPROVED
        record.approved_by = current_entity.id
        record.approval_note = body.note or None
        record.approved_at = now

        # Now apply the capability changes
        if record.capabilities_snapshot:
            agent.capabilities = record.capabilities_snapshot
    else:
        record.approval_status = EvolutionApprovalStatus.REJECTED
        record.approved_by = current_entity.id
        record.approval_note = body.note or None
        record.approved_at = now

    await log_action(
        db,
        action=f"evolution.{body.action}",
        entity_id=current_entity.id,
        resource_type="evolution_record",
        resource_id=record.id,
        details={
            "agent_id": str(record.entity_id),
            "version": record.version,
            "risk_tier": record.risk_tier,
        },
    )
    await db.flush()
    await db.refresh(record)
    return _to_response(record)


@router.get(
    "/{entity_id}/purchasable",
    response_model=EvolutionTimelineResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_purchasable_evolutions(
    entity_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List evolution records available for sale (linked to active listings)."""
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    base_filter = (
        select(EvolutionRecord)
        .join(
            Listing,
            EvolutionRecord.id == Listing.source_evolution_record_id,
        )
        .where(
            EvolutionRecord.entity_id == entity_id,
            Listing.is_active.is_(True),
            Listing.category == "capability",
        )
    )
    total = await db.scalar(
        select(func.count()).select_from(base_filter.subquery())
    ) or 0
    result = await db.execute(
        base_filter
        .order_by(EvolutionRecord.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    records = result.scalars().all()

    return EvolutionTimelineResponse(
        records=[_to_response(r) for r in records],
        count=total,
    )


@router.get(
    "/{entity_id}/adopted",
    response_model=EvolutionTimelineResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_adopted_capabilities(
    entity_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List capabilities adopted from others (forked via marketplace)."""
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Only the agent's operator can view adopted capabilities
    if entity.type == EntityType.AGENT:
        if entity.operator_id != current_entity.id:
            raise HTTPException(
                status_code=403,
                detail="Only the agent's operator can view adopted capabilities",
            )
    elif entity_id != current_entity.id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to view adopted capabilities",
        )

    total = await db.scalar(
        select(func.count()).select_from(EvolutionRecord)
        .where(
            EvolutionRecord.entity_id == entity_id,
            EvolutionRecord.source_listing_id.isnot(None),
        )
    ) or 0
    result = await db.execute(
        select(EvolutionRecord)
        .where(
            EvolutionRecord.entity_id == entity_id,
            EvolutionRecord.source_listing_id.isnot(None),
        )
        .order_by(EvolutionRecord.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    records = result.scalars().all()

    return EvolutionTimelineResponse(
        records=[_to_response(r) for r in records],
        count=total,
    )


# --- Agent self-improvement flow ---


@router.post(
    "/{entity_id}/self-improve",
    response_model=EvolutionResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
async def propose_self_improvement(
    entity_id: uuid.UUID,
    body: SelfImprovementRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Agent-initiated capability update proposal.

    The agent authenticates via API key and proposes new capabilities
    and a version bump. The proposal creates an EvolutionRecord with
    status='pending' that must be approved by the operator before
    changes are applied.
    """
    # The authenticated entity must be the agent itself
    if current_entity.id != entity_id:
        raise HTTPException(
            status_code=403,
            detail="Agents can only propose self-improvements for themselves",
        )

    # Must be an agent (not a human)
    if current_entity.type != EntityType.AGENT:
        raise HTTPException(
            status_code=403,
            detail="Only agents can propose self-improvements",
        )

    if not current_entity.is_active:
        raise HTTPException(status_code=403, detail="Agent is deactivated")

    # Check version doesn't already exist
    existing = await db.scalar(
        select(EvolutionRecord).where(
            EvolutionRecord.entity_id == entity_id,
            EvolutionRecord.version == body.new_version,
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Version {body.new_version} already exists",
        )

    # Find the latest record to link as parent
    latest = await db.scalar(
        select(EvolutionRecord)
        .where(EvolutionRecord.entity_id == entity_id)
        .order_by(EvolutionRecord.created_at.desc())
    )

    # Content filter on reason and changes_summary
    from src.content_filter import check_content, sanitize_text

    fields_to_check = [("reason", body.reason), ("changes_summary", body.changes_summary)]
    for field_name, field_value in fields_to_check:
        filter_result = check_content(field_value)
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"{field_name} rejected: {', '.join(filter_result.flags)}",
            )
    body.reason = sanitize_text(body.reason)
    body.changes_summary = sanitize_text(body.changes_summary)

    # Compute anchor hash
    anchor_data = {
        "entity_id": str(entity_id),
        "version": body.new_version,
        "change_type": "self_improvement",
        "change_summary": body.changes_summary,
        "capabilities_snapshot": body.new_capabilities,
        "parent_record_id": str(latest.id) if latest else None,
    }
    anchor_hash = _compute_anchor_hash(anchor_data)

    record = EvolutionRecord(
        id=uuid.uuid4(),
        entity_id=entity_id,
        version=body.new_version,
        parent_record_id=latest.id if latest else None,
        change_type="self_improvement",
        change_summary=body.changes_summary,
        capabilities_snapshot=body.new_capabilities,
        extra_metadata={
            "reason": body.reason,
            "proposed_by": "agent",
        },
        anchor_hash=anchor_hash,
        risk_tier=3,  # Self-improvement always requires operator approval
        approval_status=EvolutionApprovalStatus.PENDING,
    )
    db.add(record)

    await log_action(
        db,
        action="evolution.self_improve_proposed",
        entity_id=current_entity.id,
        resource_type="evolution_record",
        resource_id=record.id,
        details={
            "agent_id": str(entity_id),
            "version": body.new_version,
            "new_capabilities": body.new_capabilities,
        },
    )
    await db.flush()
    await db.refresh(record)

    # Notify operator via WebSocket
    if current_entity.operator_id:
        try:
            from src.ws import manager

            await manager.send_to_entity(str(current_entity.operator_id), "evolution", {
                "type": "self_improvement_proposed",
                "record_id": str(record.id),
                "agent_id": str(entity_id),
                "version": body.new_version,
                "reason": body.reason,
            })
        except Exception:
            logger.warning("Best-effort side effect failed", exc_info=True)

    # Dispatch webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "evolution.self_improvement_proposed", {
            "record_id": str(record.id),
            "agent_id": str(entity_id),
            "version": body.new_version,
            "new_capabilities": body.new_capabilities,
            "reason": body.reason,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return _to_response(record)


@router.post(
    "/{entity_id}/approve/{record_id}",
    response_model=EvolutionResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def approve_self_improvement(
    entity_id: uuid.UUID,
    record_id: uuid.UUID,
    body: SelfImprovementApproveRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Operator approves a self-improvement proposal.

    Updates the agent's capabilities and creates the new version.
    Only the agent's operator can approve.
    """
    # Load the agent
    agent = await db.get(Entity, entity_id)
    if agent is None or agent.type != EntityType.AGENT:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Only the operator can approve
    if agent.operator_id != current_entity.id:
        raise HTTPException(
            status_code=403,
            detail="Only the agent's operator can approve self-improvements",
        )

    # Load the evolution record
    record = await db.get(EvolutionRecord, record_id)
    if record is None or record.entity_id != entity_id:
        raise HTTPException(
            status_code=404, detail="Evolution record not found for this agent"
        )

    if record.change_type != "self_improvement":
        raise HTTPException(
            status_code=400,
            detail="Record is not a self-improvement proposal",
        )

    if record.approval_status != EvolutionApprovalStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Record is not pending approval",
        )

    now = datetime.now(timezone.utc)
    record.approval_status = EvolutionApprovalStatus.APPROVED
    record.approved_by = current_entity.id
    record.approval_note = body.note or None
    record.approved_at = now

    # Apply the capability changes to the agent
    if record.capabilities_snapshot:
        agent.capabilities = record.capabilities_snapshot

    await log_action(
        db,
        action="evolution.self_improve_approved",
        entity_id=current_entity.id,
        resource_type="evolution_record",
        resource_id=record.id,
        details={
            "agent_id": str(entity_id),
            "version": record.version,
            "new_capabilities": record.capabilities_snapshot,
        },
    )
    await db.flush()
    await db.refresh(record)

    # Notify agent via WebSocket
    try:
        from src.ws import manager

        await manager.send_to_entity(str(entity_id), "evolution", {
            "type": "self_improvement_approved",
            "record_id": str(record.id),
            "version": record.version,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return _to_response(record)


@router.post(
    "/{entity_id}/reject/{record_id}",
    response_model=EvolutionResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def reject_self_improvement(
    entity_id: uuid.UUID,
    record_id: uuid.UUID,
    body: SelfImprovementApproveRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Operator rejects a self-improvement proposal.

    The agent's capabilities remain unchanged.
    Only the agent's operator can reject.
    """
    # Load the agent
    agent = await db.get(Entity, entity_id)
    if agent is None or agent.type != EntityType.AGENT:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Only the operator can reject
    if agent.operator_id != current_entity.id:
        raise HTTPException(
            status_code=403,
            detail="Only the agent's operator can reject self-improvements",
        )

    # Load the evolution record
    record = await db.get(EvolutionRecord, record_id)
    if record is None or record.entity_id != entity_id:
        raise HTTPException(
            status_code=404, detail="Evolution record not found for this agent"
        )

    if record.change_type != "self_improvement":
        raise HTTPException(
            status_code=400,
            detail="Record is not a self-improvement proposal",
        )

    if record.approval_status != EvolutionApprovalStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Record is not pending approval",
        )

    now = datetime.now(timezone.utc)
    record.approval_status = EvolutionApprovalStatus.REJECTED
    record.approved_by = current_entity.id
    record.approval_note = body.note or None
    record.approved_at = now

    await log_action(
        db,
        action="evolution.self_improve_rejected",
        entity_id=current_entity.id,
        resource_type="evolution_record",
        resource_id=record.id,
        details={
            "agent_id": str(entity_id),
            "version": record.version,
        },
    )
    await db.flush()
    await db.refresh(record)

    # Notify agent via WebSocket
    try:
        from src.ws import manager

        await manager.send_to_entity(str(entity_id), "evolution", {
            "type": "self_improvement_rejected",
            "record_id": str(record.id),
            "version": record.version,
            "note": body.note,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return _to_response(record)
