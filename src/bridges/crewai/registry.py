"""CrewAI registry — thin wrapper around shared registry_base."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.bridges.crewai.adapter import translate_crewai_manifest
from src.bridges.crewai.security import scan_manifest
from src.bridges.registry_base import (
    get_latest_scan,
    import_agent,
)
from src.bridges.registry_base import (
    rescan_entity as _rescan_entity,
)
from src.models import Entity, FrameworkSecurityScan

__all__ = ["import_crewai_agent", "rescan_entity", "get_latest_scan"]


async def import_crewai_agent(
    db: AsyncSession,
    manifest: dict[str, Any],
    operator_entity: Entity,
) -> tuple[Entity, FrameworkSecurityScan]:
    """Import a CrewAI manifest into AgentGraph."""
    return await import_agent(
        db, manifest, operator_entity,
        framework="crewai",
        scan_manifest_fn=scan_manifest,
        translate_fn=translate_crewai_manifest,
    )


async def rescan_entity(
    db: AsyncSession,
    entity: Entity,
    manifest: dict[str, Any],
) -> FrameworkSecurityScan:
    """Rescan an existing CrewAI entity."""
    return await _rescan_entity(
        db, entity, manifest,
        framework="crewai",
        scan_manifest_fn=scan_manifest,
    )
