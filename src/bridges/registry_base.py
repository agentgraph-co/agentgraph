"""Shared bridge registry — generic import, rescan, and scan-lookup logic.

All framework-specific registries delegate to these functions, passing
their own ``scan_manifest`` callable and optional ``translate`` callable.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bridges.scanner_base import ScanResult
from src.models import Entity, EntityType, FrameworkSecurityScan


def _trust_modifier(severity: str) -> float:
    if severity == "clean":
        return 1.0
    if severity == "warnings":
        return 0.8
    return 0.5


async def import_agent(
    db: AsyncSession,
    manifest: dict[str, Any],
    operator_entity: Entity,
    *,
    framework: str,
    scan_manifest_fn: Callable[[dict[str, Any]], ScanResult],
    translate_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> tuple[Entity, FrameworkSecurityScan]:
    """Import a framework agent manifest into AgentGraph.

    Args:
        db: Database session.
        manifest: Raw manifest from the framework.
        operator_entity: The human entity performing the import.
        framework: Framework identifier (e.g. ``"openclaw"``).
        scan_manifest_fn: Framework-specific manifest scanner.
        translate_fn: Optional manifest translator (extracts name/desc/caps).

    Returns:
        Tuple of (created Entity, FrameworkSecurityScan).
    """
    if translate_fn is not None:
        translated = translate_fn(manifest)
        agent_name = translated["name"]
        description = translated["description"]
        capabilities = translated["capabilities"]
    else:
        agent_name = manifest.get("name", f"{framework.title()} Agent")
        description = manifest.get("description", "")
        capabilities = manifest.get("capabilities", [])

    agent_id = uuid.uuid4()
    did_web = f"did:web:agentgraph.io:{framework}:{agent_id}"

    scan_result = scan_manifest_fn(manifest)
    trust_mod = _trust_modifier(scan_result.severity)

    agent = Entity(
        id=agent_id,
        type=EntityType.AGENT,
        display_name=agent_name[:100],
        bio_markdown=description[:5000] if description else "",
        did_web=did_web,
        capabilities=capabilities,
        operator_id=operator_entity.id,
        framework_source=framework,
        framework_trust_modifier=trust_mod,
        is_active=True,
    )
    db.add(agent)

    scan_record = FrameworkSecurityScan(
        id=uuid.uuid4(),
        entity_id=agent_id,
        framework=framework,
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
    *,
    framework: str,
    scan_manifest_fn: Callable[[dict[str, Any]], ScanResult],
) -> FrameworkSecurityScan:
    """Rescan an existing entity with an updated manifest.

    Updates the entity's trust modifier and creates a new scan record.
    """
    scan_result = scan_manifest_fn(manifest)
    entity.framework_trust_modifier = _trust_modifier(scan_result.severity)

    scan_record = FrameworkSecurityScan(
        id=uuid.uuid4(),
        entity_id=entity.id,
        framework=entity.framework_source or framework,
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
    return await db.scalar(
        select(FrameworkSecurityScan)
        .where(FrameworkSecurityScan.entity_id == entity_id)
        .order_by(FrameworkSecurityScan.scanned_at.desc())
        .limit(1)
    )
