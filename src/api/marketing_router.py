"""Admin marketing dashboard and draft management API."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, get_db, require_admin
from src.models import Entity

router = APIRouter(prefix="/admin/marketing", tags=["admin"])


# --- Response models ---

class MarketingDashboardResponse(BaseModel):
    platform_stats: list[dict]
    topic_stats: list[dict]
    type_stats: list[dict]
    engagement: dict
    cost: dict
    recent_posts: list[dict]
    pending_drafts: int
    campaigns: list[dict]


class DraftResponse(BaseModel):
    id: uuid.UUID
    platform: str
    content: str
    topic: str | None
    post_type: str
    status: str
    llm_model: str | None
    created_at: str

    model_config = {"from_attributes": True}


class DraftActionRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|edit_approve)$")
    content: str | None = None  # Required for edit_approve
    reason: str | None = None   # Optional for reject


class WeeklyDigestResponse(BaseModel):
    week_start: str
    week_end: str
    platforms: list[dict]
    total_posts: int
    cost_breakdown: list[dict]
    total_cost_usd: float
    top_posts: list[dict]


# --- Endpoints ---

@router.get("/dashboard", response_model=MarketingDashboardResponse)
async def get_marketing_dashboard(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> MarketingDashboardResponse:
    """Get marketing dashboard data — posts, engagement, costs, campaigns."""
    require_admin(current_entity)
    from src.marketing.dashboard import get_dashboard_data

    data = await get_dashboard_data(db)
    return MarketingDashboardResponse(**data)


@router.get("/drafts", response_model=list[DraftResponse])
async def get_pending_drafts(
    platform: str | None = None,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> list[DraftResponse]:
    """Get drafts awaiting human review."""
    require_admin(current_entity)
    from src.marketing.draft_queue import get_pending_drafts as _get_drafts

    drafts = await _get_drafts(db, platform=platform)
    return [
        DraftResponse(
            id=d.id,
            platform=d.platform,
            content=d.content,
            topic=d.topic,
            post_type=d.post_type,
            status=d.status,
            llm_model=d.llm_model,
            created_at=d.created_at.isoformat(),
        )
        for d in drafts
    ]


@router.post("/drafts/{post_id}", response_model=DraftResponse)
async def action_draft(
    post_id: uuid.UUID,
    req: DraftActionRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> DraftResponse:
    """Approve, reject, or edit+approve a draft."""
    require_admin(current_entity)
    from src.marketing.draft_queue import (
        approve_draft,
        edit_and_approve,
        reject_draft,
    )

    post = None
    if req.action == "approve":
        post = await approve_draft(db, post_id)
    elif req.action == "reject":
        post = await reject_draft(db, post_id, reason=req.reason or "")
    elif req.action == "edit_approve":
        if not req.content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="content required for edit_approve",
            )
        post = await edit_and_approve(db, post_id, req.content)

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft not found or not in human_review status",
        )

    await db.commit()
    return DraftResponse(
        id=post.id,
        platform=post.platform,
        content=post.content,
        topic=post.topic,
        post_type=post.post_type,
        status=post.status,
        llm_model=post.llm_model,
        created_at=post.created_at.isoformat(),
    )


@router.get("/digest", response_model=WeeklyDigestResponse)
async def get_weekly_digest(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> WeeklyDigestResponse:
    """Get current weekly marketing digest data."""
    require_admin(current_entity)
    from src.marketing.digest import generate_weekly_digest

    data = await generate_weekly_digest(db)
    return WeeklyDigestResponse(**data)


@router.post("/digest/send")
async def send_digest_email(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually send the weekly digest email to admin."""
    require_admin(current_entity)
    from src.marketing.digest import send_weekly_digest_email

    sent = await send_weekly_digest_email(db)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send digest email",
        )
    return {"status": "sent", "to": current_entity.email}


@router.post("/trigger", response_model=None)
async def trigger_marketing_tick(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually trigger a marketing tick (for testing)."""
    require_admin(current_entity)
    from src.marketing.orchestrator import run_marketing_tick

    results = await run_marketing_tick(db)
    await db.commit()
    return results


@router.get("/health")
async def marketing_health(
    current_entity: Entity = Depends(get_current_entity),
) -> dict:
    """Check health of all configured platform adapters."""
    require_admin(current_entity)
    from src.marketing.adapters.bluesky import BlueskyAdapter
    from src.marketing.adapters.devto import DevtoAdapter
    from src.marketing.adapters.discord_bot import DiscordAdapter
    from src.marketing.adapters.hackernews import HackerNewsAdapter
    from src.marketing.adapters.hashnode import HashnodeAdapter
    from src.marketing.adapters.huggingface import HuggingFaceAdapter
    from src.marketing.adapters.linkedin import LinkedInAdapter
    from src.marketing.adapters.reddit import RedditAdapter
    from src.marketing.adapters.telegram_bot import TelegramAdapter
    from src.marketing.adapters.twitter import TwitterAdapter
    from src.marketing.config import marketing_settings
    from src.marketing.llm.cost_tracker import (
        get_daily_spend,
        get_monthly_spend,
    )
    from src.marketing.llm.ollama_client import is_available as ollama_available

    adapters = {
        "twitter": TwitterAdapter(),
        "reddit": RedditAdapter(),
        "bluesky": BlueskyAdapter(),
        "discord": DiscordAdapter(),
        "linkedin": LinkedInAdapter(),
        "telegram": TelegramAdapter(),
        "devto": DevtoAdapter(),
        "hashnode": HashnodeAdapter(),
        "huggingface": HuggingFaceAdapter(),
        "hackernews": HackerNewsAdapter(),
    }

    health: dict = {
        "marketing_enabled": marketing_settings.marketing_enabled,
        "ollama_available": await ollama_available(),
        "anthropic_configured": bool(marketing_settings.anthropic_api_key),
        "daily_spend_usd": round(await get_daily_spend(), 4),
        "monthly_spend_usd": round(await get_monthly_spend(), 4),
        "adapters": {},
    }

    for name, adapter in adapters.items():
        configured = await adapter.is_configured()
        health["adapters"][name] = {
            "configured": configured,
            "healthy": (
                await adapter.health_check() if configured else False
            ),
        }

    return health
