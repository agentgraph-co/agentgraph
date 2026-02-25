"""OpenClaw registry — thin wrapper around shared registry_base."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.bridges.openclaw.security import scan_manifest
from src.bridges.registry_base import (
    get_latest_scan,
    import_agent,
)
from src.bridges.registry_base import (
    rescan_entity as _rescan_entity,
)
from src.models import Entity, FrameworkSecurityScan

# Re-export get_latest_scan unchanged
__all__ = [
    "import_openclaw_agent",
    "rescan_entity",
    "get_latest_scan",
    "get_framework_stats",
]


async def import_openclaw_agent(
    db: AsyncSession,
    manifest: dict[str, Any],
    operator_entity: Entity,
) -> tuple[Entity, FrameworkSecurityScan]:
    """Import an OpenClaw agent manifest into AgentGraph."""
    return await import_agent(
        db, manifest, operator_entity,
        framework="openclaw",
        scan_manifest_fn=scan_manifest,
    )


async def rescan_entity(
    db: AsyncSession,
    entity: Entity,
    manifest: dict[str, Any],
) -> FrameworkSecurityScan:
    """Rescan an existing OpenClaw entity."""
    return await _rescan_entity(
        db, entity, manifest,
        framework="openclaw",
        scan_manifest_fn=scan_manifest,
    )


async def get_framework_stats(
    db: AsyncSession,
) -> dict[str, Any]:
    """Get statistics about framework-imported entities."""
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
