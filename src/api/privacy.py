"""Privacy tier access control helpers.

Provides reusable functions for checking entity privacy tier access
across all API endpoints (feed, evolution, trust, graph, etc.).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, EntityRelationship, PrivacyTier, RelationshipType


async def check_privacy_access(
    target_entity: Entity,
    requester_entity: Entity | None,
    db: AsyncSession,
) -> bool:
    """Check if requester can access target based on privacy tier.

    Returns True if access is granted, False otherwise.

    Rules:
    - PUBLIC: anyone can access
    - VERIFIED: only verified (email_verified) users or self
    - PRIVATE: only followers or self
    """
    if target_entity.privacy_tier == PrivacyTier.PUBLIC:
        return True
    if requester_entity is None:
        return False
    if requester_entity.id == target_entity.id:
        return True  # own data always visible
    if target_entity.privacy_tier == PrivacyTier.VERIFIED:
        return bool(requester_entity.email_verified)
    if target_entity.privacy_tier == PrivacyTier.PRIVATE:
        return await is_following(db, requester_entity.id, target_entity.id)
    return True


async def is_following(
    db: AsyncSession,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
) -> bool:
    """Check if source_id follows target_id."""
    result = await db.execute(
        select(EntityRelationship.id).where(
            EntityRelationship.source_entity_id == source_id,
            EntityRelationship.target_entity_id == target_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    return result.scalar_one_or_none() is not None
