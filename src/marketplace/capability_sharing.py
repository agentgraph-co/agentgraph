"""Capability sharing -- creates evolution records when capabilities are purchased."""
from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, EntityType, EvolutionRecord, Listing


async def create_capability_listing(
    db: AsyncSession,
    entity_id: uuid.UUID,
    evolution_record_id: uuid.UUID,
    title: str,
    description: str,
    tags: list[str],
    pricing_model: str,
    price_cents: int,
    license_type: str = "commercial",
) -> Listing:
    """Create a marketplace listing linked to an evolution record."""
    # Verify the evolution record exists
    record = await db.get(EvolutionRecord, evolution_record_id)
    if record is None:
        raise ValueError("Evolution record not found")

    # Verify the record belongs to an agent owned by this entity
    agent = await db.get(Entity, record.entity_id)
    if agent is None or agent.operator_id != entity_id:
        raise ValueError("You don't own this agent's evolution record")

    listing = Listing(
        id=uuid.uuid4(),
        entity_id=entity_id,
        title=title,
        description=description,
        category="capability",
        tags=tags,
        pricing_model=pricing_model,
        price_cents=price_cents,
        source_evolution_record_id=evolution_record_id,
    )
    db.add(listing)

    # Set license_type on the source evolution record if not already set
    if record.license_type is None:
        record.license_type = license_type

    return listing


async def adopt_capability(
    db: AsyncSession,
    listing: Listing,
    buyer_agent_id: uuid.UUID,
    buyer_entity_id: uuid.UUID,
) -> EvolutionRecord:
    """Create a fork evolution record on the buyer's agent from a purchased capability."""
    # Verify buyer owns the target agent
    agent = await db.get(Entity, buyer_agent_id)
    if agent is None or agent.type != EntityType.AGENT:
        raise ValueError("Target must be an active agent")
    if agent.operator_id != buyer_entity_id:
        raise ValueError("You don't own this agent")

    # Cannot adopt your own capability
    if listing.entity_id == buyer_entity_id:
        raise ValueError("Cannot adopt your own capability")

    # Get the source evolution record
    source_record = await db.get(EvolutionRecord, listing.source_evolution_record_id)
    if source_record is None:
        raise ValueError("Source evolution record not found")

    # Get latest version of buyer's agent to determine next version
    latest = await db.scalar(
        select(EvolutionRecord)
        .where(EvolutionRecord.entity_id == buyer_agent_id)
        .order_by(EvolutionRecord.created_at.desc())
    )

    # Compute next version
    if latest:
        parts = latest.version.split(".")
        next_version = f"{parts[0]}.{int(parts[1]) + 1}.0"
    else:
        next_version = "1.0.0"

    # Merge capabilities
    existing_caps = list(agent.capabilities or [])
    new_caps = list(source_record.capabilities_snapshot or [])
    merged_caps = sorted(set(existing_caps + new_caps))

    # Compute anchor hash
    anchor_data = {
        "entity_id": str(buyer_agent_id),
        "version": next_version,
        "change_type": "fork",
        "source_listing_id": str(listing.id),
        "forked_from_entity_id": str(source_record.entity_id),
    }
    anchor_hash = hashlib.sha256(
        json.dumps(anchor_data, sort_keys=True).encode()
    ).hexdigest()

    # Determine license type from source record or default
    resolved_license = source_record.license_type or "commercial"

    fork_record = EvolutionRecord(
        id=uuid.uuid4(),
        entity_id=buyer_agent_id,
        version=next_version,
        parent_record_id=latest.id if latest else None,
        forked_from_entity_id=source_record.entity_id,
        change_type="fork",
        change_summary=f"Adopted capability from listing '{listing.title}'",
        capabilities_snapshot=merged_caps,
        extra_metadata={
            "source_listing_id": str(listing.id),
            "source_listing_title": listing.title,
            "adopted_capabilities": new_caps,
        },
        anchor_hash=anchor_hash,
        risk_tier=2,  # Capability change
        approval_status="auto_approved",  # Market purchases are pre-approved
        source_listing_id=listing.id,
        license_type=resolved_license,
    )
    db.add(fork_record)

    # Update agent capabilities
    agent.capabilities = merged_caps

    return fork_record
