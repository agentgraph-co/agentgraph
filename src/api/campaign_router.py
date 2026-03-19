"""Admin campaign planning and management API."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, get_db, require_admin
from src.models import Entity

router = APIRouter(
    prefix="/admin/marketing/campaigns",
    tags=["admin"],
)


# --- Request / response models ---

class ApproveRequest(BaseModel):
    approved_post_indices: list[int] | None = None


class RejectRequest(BaseModel):
    feedback: str


# --- Endpoints ---

@router.get("/proposed")
async def list_proposed_campaigns(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get all pending campaign proposals."""
    require_admin(current_entity)
    from src.marketing.campaign_planner import (
        get_proposed_campaigns,
    )

    return await get_proposed_campaigns(db)


@router.post("/generate")
async def generate_campaign(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger weekly campaign plan generation via Opus."""
    require_admin(current_entity)
    from src.marketing.campaign_planner import (
        generate_weekly_plan,
        send_campaign_proposal_email,
    )

    plan = await generate_weekly_plan(db)
    if plan.get("error"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=plan["error"],
        )

    # Send proposal email (fire-and-forget OK)
    cid = uuid.UUID(plan["campaign_id"])
    await send_campaign_proposal_email(db, plan, cid)
    await db.commit()
    return plan


@router.post("/{campaign_id}/approve")
async def approve_campaign(
    campaign_id: uuid.UUID,
    req: ApproveRequest | None = None,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Approve a proposed campaign (optionally a subset)."""
    require_admin(current_entity)
    from src.marketing.campaign_planner import (
        approve_campaign_plan,
    )

    indices = req.approved_post_indices if req else None
    result = await approve_campaign_plan(
        db, campaign_id, indices,
    )
    if result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"],
        )
    await db.commit()
    return result


@router.post("/{campaign_id}/reject")
async def reject_campaign(
    campaign_id: uuid.UUID,
    req: RejectRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reject a proposed campaign with feedback."""
    require_admin(current_entity)
    from src.marketing.campaign_planner import (
        reject_campaign_plan,
    )

    result = await reject_campaign_plan(
        db, campaign_id, req.feedback,
    )
    if result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"],
        )
    await db.commit()
    return result


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get campaign details with associated posts."""
    require_admin(current_entity)
    from src.marketing.campaign_planner import (
        get_campaign_detail,
    )

    detail = await get_campaign_detail(db, campaign_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )
    return detail
