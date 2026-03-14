"""Developer Hub API — public framework info and platform stats."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from sqlalchemy import func, select

from src.api.developer_hub_data import FRAMEWORKS
from src.database import async_session
from src.models import Entity, EntityType

router = APIRouter(prefix="/developer-hub", tags=["developer-hub"])


@router.get("/stats")
async def get_developer_hub_stats() -> dict:
    """Public stats: per-framework agent counts, totals."""
    async with async_session() as db:
        # Count agents per framework
        result = await db.execute(
            select(
                Entity.framework_source,
                func.count(),
            )
            .where(
                Entity.type == EntityType.AGENT,
                Entity.is_active.is_(True),
            )
            .group_by(Entity.framework_source)
        )
        framework_counts: dict[str, int] = {}
        total_agents = 0
        for framework, count in result.all():
            key = framework or "native"
            framework_counts[key] = framework_counts.get(key, 0) + count
            total_agents += count

        # Total security scans
        try:
            from src.models import FrameworkSecurityScan

            scan_count = await db.scalar(
                select(func.count()).select_from(FrameworkSecurityScan)
            ) or 0
        except Exception:
            scan_count = 0

    return {
        "total_agents": total_agents,
        "total_frameworks": len(FRAMEWORKS),
        "total_scans": scan_count,
        "framework_counts": framework_counts,
    }


@router.get("/frameworks")
async def get_developer_hub_frameworks() -> list[dict]:
    """Public framework list with details and code snippets."""
    return [asdict(f) for f in FRAMEWORKS]
