from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, require_admin
from src.database import get_db
from src.jobs.expire_provisional import expire_provisional_agents
from src.models import Entity

router = APIRouter(prefix="/admin/jobs", tags=["admin"])


@router.post("/expire-provisional")
async def trigger_expire_provisional(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger the provisional agent expiration job (admin only)."""
    require_admin(current_entity)
    summary = await expire_provisional_agents(db)
    await db.commit()
    return summary
