"""OpenClaw registry — import OpenClaw agent manifests into AgentGraph.

Handles conversion of OpenClaw agent manifests into AgentGraph entity
profiles, including security scanning and trust modifier assignment.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bridges.openclaw.security import scan_manifest
from src.models import Entity, EntityType, FrameworkSecurityScan


async def import_openclaw_agent(
    db: AsyncSession,
    manifest: dict[str, Any],
    operator_entity: Entity,
) -> tuple[Entity, FrameworkSecurityScan]:
    """Import an OpenClaw agent manifest into AgentGraph.

    Creates an entity profile from the manifest, runs security scanning,
    and stores the scan result. Agents from OpenClaw start with a 0.8x
    trust modifier (penalty) which can be removed after a clean rescan.

    Args:
        db: Database session
        manifest: OpenClaw agent manifest dict with keys:
            - name (str): Agent display name
            - description (str): Agent bio/description
            - capabilities (list[str]): Agent capabilities
            - skills (list[dict]): Skills with code to scan
            - version (str, optional): Agent version
        operator_entity: The human entity importing this agent

    Returns:
        Tuple of (created Entity, FrameworkSecurityScan)
    """
    agent_name = manifest.get("name", "OpenClaw Agent")
    description = manifest.get("description", "")
    capabilities = manifest.get("capabilities", [])

    # Generate a unique DID for the imported agent
    agent_id = uuid.uuid4()
    did_web = f"did:web:agentgraph.io:openclaw:{agent_id}"

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
        framework_source="openclaw",
        framework_trust_modifier=trust_modifier,
        is_active=True,
    )
    db.add(agent)

    # Store security scan
    scan_record = FrameworkSecurityScan(
        id=uuid.uuid4(),
        entity_id=agent_id,
        framework="openclaw",
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
    manifest: dict[str, Any],
) -> FrameworkSecurityScan:
    """Rescan an existing entity with updated manifest.

    If the rescan comes back clean and the entity had a penalty,
    the trust modifier is restored to 1.0.

    Args:
        db: Database session
        entity: The entity to rescan
        manifest: Updated manifest with skills to scan

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
        framework=entity.framework_source or "openclaw",
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


async def get_framework_stats(
    db: AsyncSession,
) -> dict[str, Any]:
    """Get statistics about framework-imported entities."""
    from sqlalchemy import func

    # Count entities per framework
    result = await db.execute(
        select(
            Entity.framework_source,
            func.count(Entity.id),
        )
        .where(
            Entity.is_active.is_(True),
            Entity.framework_source.isnot(None),
        )
        .group_by(Entity.framework_source)
    )
    framework_counts = {row[0]: row[1] for row in result.fetchall()}

    # Count scans by result
    scan_result = await db.execute(
        select(
            FrameworkSecurityScan.scan_result,
            func.count(FrameworkSecurityScan.id),
        )
        .group_by(FrameworkSecurityScan.scan_result)
    )
    scan_counts = {row[0]: row[1] for row in scan_result.fetchall()}

    supported_frameworks = ["mcp", "openclaw", "langchain"]

    return {
        "supported_frameworks": supported_frameworks,
        "entity_counts": framework_counts,
        "scan_results": scan_counts,
    }
