"""Organization endpoints -- CRUD, membership, fleet, compliance, enterprise."""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import (
    Entity,
    EntityType,
    Organization,
    OrganizationMembership,
    OrgRole,
    Post,
    TrustScore,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organizations", tags=["organizations"])

# --- Schemas ---


class CreateOrgRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class UpdateOrgRequest(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    settings: dict | None = None
    tier: str | None = Field(None, pattern="^(free|pro|enterprise)$")

    @field_validator("settings")
    @classmethod
    def validate_settings_size(cls, v: dict | None) -> dict | None:
        if v is None:
            return v
        import json

        serialized = json.dumps(v)
        if len(serialized) > 10240:
            raise ValueError("settings must be less than 10KB serialized")
        if len(v) > 50:
            raise ValueError("settings must have at most 50 keys")
        return v


class AddMemberRequest(BaseModel):
    entity_id: uuid.UUID
    role: str = Field(default="member", pattern="^(owner|admin|member)$")


class BulkActionRequest(BaseModel):
    entity_ids: list[uuid.UUID]
    action: str = Field(..., pattern="^(enable|disable)$")

# --- Helpers ---


async def _check_org_role(
    db: AsyncSession,
    org_id: uuid.UUID,
    entity_id: uuid.UUID,
    required_roles: list[OrgRole] | None = None,
) -> OrganizationMembership:
    """Check if entity is a member of org with required role."""
    membership = await db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.entity_id == entity_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    if required_roles and membership.role not in required_roles:
        raise HTTPException(status_code=403, detail="Insufficient role")
    return membership


_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


# --- Endpoints ---

@router.post("", status_code=201)
async def create_organization(
    body: CreateOrgRequest,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_writes),
) -> dict:
    if not _NAME_RE.match(body.name):
        raise HTTPException(
            status_code=422,
            detail="Name must start with alphanumeric",
        )
    existing = await db.scalar(
        select(Organization).where(Organization.name == body.name)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Organization name already taken")
    org = Organization(
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        created_by=entity.id,
    )
    db.add(org)
    await db.flush()
    membership = OrganizationMembership(
        organization_id=org.id,
        entity_id=entity.id,
        role=OrgRole.OWNER,
    )
    db.add(membership)
    await db.flush()
    await db.refresh(org)
    return {
        "id": str(org.id),
        "name": org.name,
        "display_name": org.display_name,
        "description": org.description,
        "tier": org.tier,
        "is_active": org.is_active,
        "created_by": str(org.created_by),
        "created_at": org.created_at.isoformat(),
        "member_count": 1,
    }



@router.get("/{org_id}")
async def get_organization(
    org_id: uuid.UUID,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
) -> dict:
    """Get organization details with member count."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    count_q = (
        select(func.count()).select_from(OrganizationMembership)
        .where(OrganizationMembership.organization_id == org_id)
    )
    member_count = await db.scalar(count_q) or 0
    return {
        "id": str(org.id), "name": org.name, "display_name": org.display_name,
        "description": org.description, "settings": org.settings or {},
        "tier": org.tier, "is_active": org.is_active,
        "created_by": str(org.created_by), "created_at": org.created_at.isoformat(),
        "member_count": member_count,
    }



@router.patch("/{org_id}")
async def update_organization(
    org_id: uuid.UUID,
    body: UpdateOrgRequest,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_writes),
) -> dict:
    """Update organization settings. Only owner/admin."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _check_org_role(db, org_id, entity.id, [OrgRole.OWNER, OrgRole.ADMIN])
    if body.display_name is not None:
        org.display_name = body.display_name
    if body.description is not None:
        org.description = body.description
    if body.settings is not None:
        org.settings = body.settings
    if body.tier is not None:
        org.tier = body.tier
    await db.flush()
    await db.refresh(org)
    count_q = (
        select(func.count()).select_from(OrganizationMembership)
        .where(OrganizationMembership.organization_id == org_id)
    )
    member_count = await db.scalar(count_q) or 0
    return {
        "id": str(org.id), "name": org.name, "display_name": org.display_name,
        "description": org.description, "settings": org.settings or {},
        "tier": org.tier, "is_active": org.is_active,
        "created_by": str(org.created_by), "created_at": org.created_at.isoformat(),
        "member_count": member_count,
    }



@router.post("/{org_id}/members", status_code=201)
async def add_member(
    org_id: uuid.UUID,
    body: AddMemberRequest,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_writes),
) -> dict:
    """Add a member to the organization. Only owner/admin."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _check_org_role(db, org_id, entity.id, [OrgRole.OWNER, OrgRole.ADMIN])
    target = await db.get(Entity, body.entity_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    existing = await db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.entity_id == body.entity_id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Entity is already a member")
    role = OrgRole(body.role)
    membership = OrganizationMembership(
        organization_id=org_id, entity_id=body.entity_id, role=role,
    )
    db.add(membership)
    await db.flush()
    await db.refresh(membership)
    return {
        "id": str(membership.id), "organization_id": str(membership.organization_id),
        "entity_id": str(membership.entity_id), "role": membership.role.value,
        "joined_at": membership.joined_at.isoformat(),
    }



@router.delete("/{org_id}/members/{entity_id}")
async def remove_member(
    org_id: uuid.UUID,
    entity_id: uuid.UUID,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_writes),
) -> dict:
    """Remove a member. Owner cannot be removed."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _check_org_role(db, org_id, entity.id, [OrgRole.OWNER, OrgRole.ADMIN])
    membership = await db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.entity_id == entity_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if membership.role == OrgRole.OWNER:
        raise HTTPException(status_code=400, detail="Cannot remove the organization owner")
    await db.delete(membership)
    await db.flush()
    return {"detail": "Member removed"}



@router.get("/{org_id}/members")
async def list_members(
    org_id: uuid.UUID,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """List all members of an organization."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _check_org_role(db, org_id, entity.id)
    base = (
        select(OrganizationMembership, Entity)
        .join(Entity, OrganizationMembership.entity_id == Entity.id)
        .where(OrganizationMembership.organization_id == org_id)
    )
    count_q = select(func.count()).select_from(
        select(OrganizationMembership)
        .where(OrganizationMembership.organization_id == org_id)
        .subquery()
    )
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0
    result = await db.execute(base.limit(limit).offset(offset))
    rows = result.all()
    members = [
        {
            "id": str(m.id),
            "entity_id": str(m.entity_id),
            "display_name": ent.display_name if ent else "Unknown",
            "role": m.role.value,
            "joined_at": m.joined_at.isoformat(),
        }
        for m, ent in rows
    ]
    return {"members": members, "total": total}



@router.get("/{org_id}/fleet")
async def fleet_dashboard(
    org_id: uuid.UUID,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
) -> dict:
    """Agent fleet dashboard. Only org members."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _check_org_role(db, org_id, entity.id)
    from src.enterprise.fleet import get_fleet_dashboard
    return await get_fleet_dashboard(db, org_id)



@router.post("/{org_id}/fleet/bulk-action")
async def fleet_bulk_action(
    org_id: uuid.UUID,
    body: BulkActionRequest,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_writes),
) -> dict:
    """Bulk enable/disable agents. Only owner/admin."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _check_org_role(db, org_id, entity.id, [OrgRole.OWNER, OrgRole.ADMIN])
    from src.enterprise.fleet import bulk_action
    return await bulk_action(db, org_id, body.entity_ids, body.action)



@router.get("/{org_id}/compliance")
async def compliance_report(
    org_id: uuid.UUID,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
) -> dict:
    """Generate compliance report. Only owner/admin."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _check_org_role(db, org_id, entity.id, [OrgRole.OWNER, OrgRole.ADMIN])
    from src.enterprise.compliance import generate_compliance_report
    return await generate_compliance_report(db, org_id)



@router.get("/{org_id}/stats")
async def org_stats(
    org_id: uuid.UUID,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
) -> dict:
    """Organization analytics. Only org members."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _check_org_role(db, org_id, entity.id)
    # Single subquery for member IDs — reused in all aggregations
    member_sub = (
        select(OrganizationMembership.entity_id)
        .where(OrganizationMembership.organization_id == org_id)
        .scalar_subquery()
    )
    # Batch all counts + avg into one round-trip
    stats_q = select(
        func.count(OrganizationMembership.entity_id).label("member_count"),
    ).where(OrganizationMembership.organization_id == org_id)
    member_count = await db.scalar(stats_q) or 0

    agg_q = select(
        func.count(Entity.id).filter(Entity.type == EntityType.AGENT).label("agent_count"),
        func.coalesce(
            func.avg(TrustScore.score), 0.0,
        ).label("avg_trust"),
        func.count(Post.id).label("post_count"),
    ).select_from(
        Entity
    ).outerjoin(
        TrustScore, TrustScore.entity_id == Entity.id,
    ).outerjoin(
        Post, Post.author_entity_id == Entity.id,
    ).where(Entity.id.in_(member_sub))

    row = (await db.execute(agg_q)).one_or_none()
    agent_count = row.agent_count if row else 0
    avg_trust = round(float(row.avg_trust), 4) if row else 0.0
    post_count = row.post_count if row else 0
    return {
        "member_count": member_count, "agent_count": agent_count,
        "avg_trust": avg_trust, "post_count": post_count,
    }


# --- Audit Export ---


@router.get("/{org_id}/audit-export")
async def export_org_audit_logs(
    org_id: uuid.UUID,
    format: str = Query("json", pattern="^(json|csv)$"),
    days: int = Query(30, ge=1, le=365),
    action_filter: str | None = Query(None),
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
):
    """Export audit logs for the organization (owner/admin only)."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _check_org_role(db, org_id, entity.id, [OrgRole.OWNER, OrgRole.ADMIN])

    from src.enterprise.audit_export import export_audit_logs as do_export

    result = await do_export(
        db, org_id, format=format, days=days, action_filter=action_filter,
    )

    if format == "csv":
        return PlainTextResponse(content=result, media_type="text/csv")
    return {"logs": result, "total": len(result), "period_days": days}


# --- Usage Metering ---


@router.get("/{org_id}/usage")
async def get_usage(
    org_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365),
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
):
    """Get API usage metrics for the organization."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _check_org_role(db, org_id, entity.id, [OrgRole.OWNER, OrgRole.ADMIN])

    from src.enterprise.usage_metering import get_usage_stats

    return await get_usage_stats(db, org_id, days=days)


# --- Org API Keys ---


class CreateOrgApiKeyRequest(BaseModel):
    label: str = Field(default="default", max_length=100)
    scopes: list[str] = Field(default_factory=list)


@router.post("/{org_id}/api-keys", status_code=201)
async def create_org_api_key(
    org_id: uuid.UUID,
    body: CreateOrgApiKeyRequest,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_writes),
):
    """Create an org-scoped API key (owner/admin only)."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _check_org_role(db, org_id, entity.id, [OrgRole.OWNER, OrgRole.ADMIN])

    from src.models import APIKey

    raw_key = f"ag_org_{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    api_key = APIKey(
        entity_id=entity.id,
        key_hash=key_hash,
        label=body.label,
        scopes=body.scopes,
        organization_id=org_id,
    )
    db.add(api_key)
    await db.flush()
    await db.refresh(api_key)

    await log_action(
        db,
        action="org.api_key_create",
        entity_id=entity.id,
        resource_type="api_key",
        resource_id=api_key.id,
        details={"org_id": str(org_id), "label": body.label},
    )

    return {
        "id": str(api_key.id),
        "key": raw_key,
        "label": api_key.label,
        "scopes": api_key.scopes or [],
        "organization_id": str(org_id),
        "created_at": api_key.created_at.isoformat(),
    }


@router.get("/{org_id}/api-keys")
async def list_org_api_keys(
    org_id: uuid.UUID,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_reads),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List org-scoped API keys (owner/admin only)."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _check_org_role(db, org_id, entity.id, [OrgRole.OWNER, OrgRole.ADMIN])

    from src.models import APIKey

    base = select(APIKey).where(
        APIKey.organization_id == org_id,
        APIKey.is_active.is_(True),
    )
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar() or 0

    result = await db.execute(
        base.order_by(APIKey.created_at.desc()).limit(limit).offset(offset)
    )
    keys = result.scalars().all()

    return {
        "api_keys": [
            {
                "id": str(k.id),
                "label": k.label,
                "scopes": k.scopes or [],
                "entity_id": str(k.entity_id),
                "created_at": k.created_at.isoformat(),
            }
            for k in keys
        ],
        "total": total,
    }


@router.delete("/{org_id}/api-keys/{key_id}")
async def revoke_org_api_key(
    org_id: uuid.UUID,
    key_id: uuid.UUID,
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit_writes),
):
    """Revoke an org-scoped API key (owner/admin only)."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _check_org_role(db, org_id, entity.id, [OrgRole.OWNER, OrgRole.ADMIN])

    from src.models import APIKey

    key = await db.get(APIKey, key_id)
    if key is None or key.organization_id != org_id:
        raise HTTPException(status_code=404, detail="API key not found")

    key.is_active = False
    key.revoked_at = datetime.now(timezone.utc)
    await db.flush()

    await log_action(
        db,
        action="org.api_key_revoke",
        entity_id=entity.id,
        resource_type="api_key",
        resource_id=key_id,
        details={"org_id": str(org_id)},
    )

    return {"detail": "API key revoked"}
