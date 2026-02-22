"""SLA tier enforcement — rate limit multipliers by organization tier."""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Organization, OrganizationMembership

logger = logging.getLogger(__name__)

# Rate limit multipliers by organization tier.
# Entities not in any org get the default (1x).
TIER_MULTIPLIERS: dict[str, int] = {
    "free": 1,
    "pro": 3,
    "enterprise": 10,
}


async def get_org_tier_for_entity(
    db: AsyncSession, entity_id: UUID,
) -> str | None:
    """Look up the organization tier for an entity.

    Returns the tier string ("free", "pro", "enterprise") or None if the
    entity is not a member of any organization.
    """
    result = await db.execute(
        select(Organization.tier)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Organization.id,
        )
        .where(
            OrganizationMembership.entity_id == entity_id,
            Organization.is_active.is_(True),
        )
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None


async def get_rate_limit_multiplier(
    db: AsyncSession, entity_id: UUID,
) -> int:
    """Get the rate limit multiplier for an entity based on their org tier.

    Returns:
        int: 1 (free/default), 3 (pro), or 10 (enterprise)
    """
    tier = await get_org_tier_for_entity(db, entity_id)
    if tier is None:
        return 1
    return TIER_MULTIPLIERS.get(tier, 1)
