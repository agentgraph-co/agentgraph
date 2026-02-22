"""Semantic Kernel registry — import SK agent manifests into AgentGraph.

Handles conversion of Semantic Kernel agent configs into AgentGraph entity
profiles, including security scanning and trust modifier assignment.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bridges.semantic_kernel.adapter import translate_sk_manifest
from src.bridges.semantic_kernel.security import scan_manifest
from src.models import Entity, EntityType, FrameworkSecurityScan


async def import_sk_agent(
    db: AsyncSession,
    manifest: dict,
    operator_entity: Entity,
) -> tuple:
    """Import a Semantic Kernel agent manifest into AgentGraph.

    Creates an entity profile from the manifest, runs security scanning,
    and stores the scan result. Agents from SK start with a trust
    modifier based on scan results (1.0 clean, 0.8 warnings, 0.5 critical).

    Args:
        db: Database session
        manifest: SK agent manifest dict
        operator_entity: The human entity importing this agent

    Returns:
        Tuple of (created Entity, FrameworkSecurityScan)
    """
    translated = translate_sk_manifest(manifest)
    agent_name = translated["name"]
    description = translated["description"]
    capabilities = translated["capabilities"]

    # Generate a unique DID for the imported agent
    agent_id = uuid.uuid4()
    did_web = f"did:web:agentgraph.io:semantic_kernel:{agent_id}"

    # Run security scan
    scan_result = scan_manifest(manifest)

    # Determine trust modifier based on scan result
    if scan_result.severity == "clean":
        trust_modifier = 1.0
    elif scan_result.severity == "warnings":
        trust_modifier = 0.8
    else:  # critical
        trust_modifier = 0.5

    # Create agent entity
    agent = Entity(
        id=agent_id,
        type=EntityType.AGENT,
        display_name=agent_name[:100],
        bio_markdown=description[:5000] if description else "",
        did_web=did_web,
        capabilities=capabilities,
        operator_id=operator_entity.id,
        framework_source="semantic_kernel",
        framework_trust_modifier=trust_modifier,
        is_active=True,
    )
    db.add(agent)

    # Store security scan
    scan_record = FrameworkSecurityScan(
        id=uuid.uuid4(),
        entity_id=agent_id,
        framework="semantic_kernel",
        scan_result=scan_result.severity,
        vulnerabilities=scan_result.to_dict()["vulnerabilities"],
        scanned_at=datetime.now(timezone.utc),
    )
    db.add(scan_record)

    await db.flush()
    await db.refresh(agent)
    return agent, scan_record


async def rescan_entity(
    db: AsyncSession,
    entity: Entity,
    manifest: dict,
) -> FrameworkSecurityScan:
    """Rescan an existing entity with updated manifest.

    If the rescan comes back clean and the entity had a penalty,
    the trust modifier is restored to 1.0.

    Args:
        db: Database session
        entity: The entity to rescan
        manifest: Updated manifest with code to scan

    Returns:
        New FrameworkSecurityScan record
    """
    scan_result = scan_manifest(manifest)

    # Update trust modifier based on new scan
    if scan_result.severity == "clean":
        entity.framework_trust_modifier = 1.0
    elif scan_result.severity == "warnings":
        entity.framework_trust_modifier = 0.8
    else:
        entity.framework_trust_modifier = 0.5

    # Store new scan record
    scan_record = FrameworkSecurityScan(
        id=uuid.uuid4(),
        entity_id=entity.id,
        framework=entity.framework_source or "semantic_kernel",
        scan_result=scan_result.severity,
        vulnerabilities=scan_result.to_dict()["vulnerabilities"],
        scanned_at=datetime.now(timezone.utc),
    )
    db.add(scan_record)
    await db.flush()
    await db.refresh(entity)
    return scan_record


async def get_latest_scan(
    db: AsyncSession,
    entity_id: uuid.UUID,
) -> FrameworkSecurityScan | None:
    """Get the most recent security scan for an entity."""
    result = await db.scalar(
        select(FrameworkSecurityScan)
        .where(FrameworkSecurityScan.entity_id == entity_id)
        .order_by(FrameworkSecurityScan.scanned_at.desc())
        .limit(1)
    )
    return result
