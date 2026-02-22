"""Organization endpoints -- CRUD, membership, fleet, compliance."""
from __future__ import annotations

import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
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
) -> dict:
    """List all members of an organization."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    await _check_org_role(db, org_id, entity.id)
    q = select(OrganizationMembership).where(
        OrganizationMembership.organization_id == org_id
    )
    result = await db.execute(q)
    memberships = result.scalars().all()
    members = []
    for m in memberships:
        ent = await db.get(Entity, m.entity_id)
        members.append({
            "id": str(m.id), "entity_id": str(m.entity_id),
            "display_name": ent.display_name if ent else "Unknown",
            "role": m.role.value, "joined_at": m.joined_at.isoformat(),
        })
    return {"members": members, "total": len(members)}



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
    member_count_q = (
        select(func.count()).select_from(OrganizationMembership)
        .where(OrganizationMembership.organization_id == org_id)
    )
    member_count = await db.scalar(member_count_q) or 0
    member_ids_q = (
        select(OrganizationMembership.entity_id)
        .where(OrganizationMembership.organization_id == org_id)
    )
    member_ids_result = await db.execute(member_ids_q)
    member_ids = [row[0] for row in member_ids_result.fetchall()]
    agent_count = 0
    avg_trust = 0.0
    post_count = 0
    if member_ids:
        agent_count_q = (
            select(func.count()).select_from(Entity)
            .where(Entity.id.in_(member_ids), Entity.type == EntityType.AGENT)
        )
        agent_count = await db.scalar(agent_count_q) or 0
        trust_q = select(func.avg(TrustScore.score)).where(
            TrustScore.entity_id.in_(member_ids)
        )
        avg_trust_raw = await db.scalar(trust_q)
        avg_trust = round(float(avg_trust_raw), 4) if avg_trust_raw else 0.0
        post_count_q = (
            select(func.count()).select_from(Post)
            .where(Post.author_entity_id.in_(member_ids))
        )
        post_count = await db.scalar(post_count_q) or 0
    return {
        "member_count": member_count, "agent_count": agent_count,
        "avg_trust": avg_trust, "post_count": post_count,
    }
