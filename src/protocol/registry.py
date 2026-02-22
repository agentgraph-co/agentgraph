"""AIP agent capability registry operations.

Manages the registration, discovery, and search of agent capabilities
within the AgentGraph protocol layer.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AgentCapabilityRegistry, Entity, TrustScore


async def register_capability(
    db: AsyncSession,
    entity_id: uuid.UUID,
    name: str,
    version: str = "1.0.0",
    description: str = "",
    input_schema: dict | None = None,
    output_schema: dict | None = None,
) -> AgentCapabilityRegistry:
    """Register a capability for an entity. Raises ValueError on duplicate."""
    # Check for existing active capability with same name
    existing = await db.execute(
        select(AgentCapabilityRegistry).where(
            AgentCapabilityRegistry.entity_id == entity_id,
            AgentCapabilityRegistry.capability_name == name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"Capability '{name}' already registered for this entity")

    cap = AgentCapabilityRegistry(
        id=uuid.uuid4(),
        entity_id=entity_id,
        capability_name=name,
        version=version,
        description=description,
        input_schema=input_schema or {},
        output_schema=output_schema or {},
    )
    db.add(cap)
    await db.flush()
    return cap


async def unregister_capability(
    db: AsyncSession,
    entity_id: uuid.UUID,
    capability_id: uuid.UUID,
) -> bool:
    """Unregister (deactivate) a capability. Returns True if found."""
    result = await db.execute(
        select(AgentCapabilityRegistry).where(
            AgentCapabilityRegistry.id == capability_id,
            AgentCapabilityRegistry.entity_id == entity_id,
        )
    )
    cap = result.scalar_one_or_none()
    if cap is None:
        return False
    cap.is_active = False
    await db.flush()
    return True


async def list_capabilities(
    db: AsyncSession,
    entity_id: uuid.UUID,
) -> list[AgentCapabilityRegistry]:
    """List all active capabilities for an entity."""
    result = await db.execute(
        select(AgentCapabilityRegistry).where(
            AgentCapabilityRegistry.entity_id == entity_id,
            AgentCapabilityRegistry.is_active.is_(True),
        ).order_by(AgentCapabilityRegistry.capability_name)
    )
    return list(result.scalars().all())


async def search_capabilities(
    db: AsyncSession,
    capability_name: str | None = None,
    min_trust: float | None = None,
    framework: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search for agents by capability, trust score, or framework.

    Returns a list of dicts with entity info and their capabilities.
    """
    # Build base query joining capabilities with entities and trust scores
    query = (
        select(
            AgentCapabilityRegistry,
            Entity.id.label("eid"),
            Entity.display_name,
            Entity.type,
            Entity.framework_source,
            TrustScore.score,
        )
        .join(Entity, AgentCapabilityRegistry.entity_id == Entity.id)
        .outerjoin(TrustScore, TrustScore.entity_id == Entity.id)
        .where(
            AgentCapabilityRegistry.is_active.is_(True),
            Entity.is_active.is_(True),
        )
    )

    if capability_name:
        query = query.where(
            AgentCapabilityRegistry.capability_name.ilike(f"%{capability_name}%")
        )
    if min_trust is not None:
        query = query.where(TrustScore.score >= min_trust)
    if framework:
        query = query.where(Entity.framework_source == framework)

    query = query.order_by(TrustScore.score.desc().nullslast()).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    # Group by entity
    seen: dict[str, dict] = {}
    for row in rows:
        cap = row[0]
        eid = str(row.eid)
        if eid not in seen:
            seen[eid] = {
                "entity_id": eid,
                "display_name": row.display_name,
                "entity_type": row.type.value if row.type else None,
                "framework_source": row.framework_source,
                "trust_score": row.score,
                "capabilities": [],
            }
        seen[eid]["capabilities"].append({
            "id": str(cap.id),
            "name": cap.capability_name,
            "version": cap.version,
            "description": cap.description,
        })

    return list(seen.values())
