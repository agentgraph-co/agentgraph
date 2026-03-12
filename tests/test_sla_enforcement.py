"""Tests for SLA tier enforcement (rate limit multipliers by org tier)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.enterprise.sla import TIER_MULTIPLIERS, get_org_tier_for_entity, get_rate_limit_multiplier
from src.models import (
    Entity,
    EntityType,
    Organization,
    OrganizationMembership,
    OrgRole,
)


async def _make_entity(db: AsyncSession, name: str) -> Entity:
    """Create and flush a minimal entity."""
    eid = uuid.uuid4()
    entity = Entity(
        id=eid,
        type=EntityType.HUMAN,
        display_name=name,
        did_web=f"did:web:agentgraph.co:users:{eid}",
    )
    db.add(entity)
    await db.flush()
    return entity


async def _make_org(
    db: AsyncSession, name: str, creator: Entity, tier: str = "free",
) -> Organization:
    """Create an org, add creator as owner, and return the org."""
    org = Organization(
        name=name,
        display_name=f"Org {name}",
        created_by=creator.id,
        tier=tier,
    )
    db.add(org)
    await db.flush()
    membership = OrganizationMembership(
        organization_id=org.id,
        entity_id=creator.id,
        role=OrgRole.OWNER,
    )
    db.add(membership)
    await db.flush()
    return org


# --- Tests ---


@pytest.mark.asyncio
async def test_multiplier_free_tier(db):
    entity = await _make_entity(db, "FreeTierUser")
    await _make_org(db, "free-org-sla", entity, tier="free")
    mult = await get_rate_limit_multiplier(db, entity.id)
    assert mult == 1


@pytest.mark.asyncio
async def test_multiplier_pro_tier(db):
    entity = await _make_entity(db, "ProTierUser")
    await _make_org(db, "pro-org-sla", entity, tier="pro")
    mult = await get_rate_limit_multiplier(db, entity.id)
    assert mult == 3


@pytest.mark.asyncio
async def test_multiplier_enterprise_tier(db):
    entity = await _make_entity(db, "EntTierUser")
    await _make_org(db, "ent-org-sla", entity, tier="enterprise")
    mult = await get_rate_limit_multiplier(db, entity.id)
    assert mult == 10


@pytest.mark.asyncio
async def test_multiplier_no_org_returns_default(db):
    entity = await _make_entity(db, "NoOrgUser")
    mult = await get_rate_limit_multiplier(db, entity.id)
    assert mult == 1


@pytest.mark.asyncio
async def test_get_org_tier_returns_none_for_no_org(db):
    entity = await _make_entity(db, "TierlessUser")
    tier = await get_org_tier_for_entity(db, entity.id)
    assert tier is None


@pytest.mark.asyncio
async def test_tier_multipliers_map_complete():
    """Verify the tier multipliers map has expected entries."""
    assert TIER_MULTIPLIERS["free"] == 1
    assert TIER_MULTIPLIERS["pro"] == 3
    assert TIER_MULTIPLIERS["enterprise"] == 10
