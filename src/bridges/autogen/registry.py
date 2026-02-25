"""AutoGen registry — thin wrapper around shared registry_base."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.bridges.autogen.adapter import translate_autogen_manifest
from src.bridges.autogen.security import scan_manifest
from src.bridges.registry_base import (
    get_latest_scan,
    import_agent,
)
from src.bridges.registry_base import (
    rescan_entity as _rescan_entity,
)
from src.models import Entity, FrameworkSecurityScan

__all__ = ["import_autogen_agent", "rescan_entity", "get_latest_scan"]


async def import_autogen_agent(
    db: AsyncSession,
    manifest: dict[str, Any],
    operator_entity: Entity,
) -> tuple[Entity, FrameworkSecurityScan]:
    """Import an AutoGen agent manifest into AgentGraph."""
    return await import_agent(
        db, manifest, operator_entity,
        framework="autogen",
        scan_manifest_fn=scan_manifest,
        translate_fn=translate_autogen_manifest,
    )


async def rescan_entity(
    db: AsyncSession,
    entity: Entity,
    manifest: dict[str, Any],
) -> FrameworkSecurityScan:
    """Rescan an existing AutoGen entity."""
    return await _rescan_entity(
        db, entity, manifest,
        framework="autogen",
        scan_manifest_fn=scan_manifest,
    )
