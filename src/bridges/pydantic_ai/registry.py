"""Pydantic AI registry — thin wrapper around shared registry_base."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.bridges.pydantic_ai.adapter import translate_pydantic_ai_manifest
from src.bridges.pydantic_ai.security import scan_manifest
from src.bridges.registry_base import (
    get_latest_scan,
    import_agent,
)
from src.bridges.registry_base import (
    rescan_entity as _rescan_entity,
)
from src.models import Entity, FrameworkSecurityScan

__all__ = ["import_pydantic_ai_agent", "rescan_entity", "get_latest_scan"]


async def import_pydantic_ai_agent(
    db: AsyncSession,
    manifest: dict[str, Any],
    operator_entity: Entity,
) -> tuple[Entity, FrameworkSecurityScan]:
    """Import a Pydantic AI agent manifest into AgentGraph."""
    return await import_agent(
        db, manifest, operator_entity,
        framework="pydantic_ai",
        scan_manifest_fn=scan_manifest,
        translate_fn=translate_pydantic_ai_manifest,
    )


async def rescan_entity(
    db: AsyncSession,
    entity: Entity,
    manifest: dict[str, Any],
) -> FrameworkSecurityScan:
    """Rescan an existing Pydantic AI entity."""
    return await _rescan_entity(
        db, entity, manifest,
        framework="pydantic_ai",
        scan_manifest_fn=scan_manifest,
    )
