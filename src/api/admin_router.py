from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import (
    Bookmark,
    CapabilityEndorsement,
    Entity,
    EntityRelationship,
    EntityType,
    EvolutionRecord,
    Listing,
    ModerationFlag,
    ModerationStatus,
    Notification,
    Post,
    Review,
    Submolt,
    Vote,
    WebhookSubscription,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(entity: Entity) -> None:
    if not entity.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")


class PlatformStats(BaseModel):
    total_entities: int
    total_humans: int
    total_agents: int
    total_posts: int
    total_votes: int
    total_follows: int
    total_submolts: int
    total_listings: int
    total_reviews: int
    total_endorsements: int
    total_bookmarks: int
    total_evolution_records: int
    pending_moderation_flags: int
    active_webhooks: int


class EntityListItem(BaseModel):
    id: uuid.UUID
    type: str
    display_name: str
    email: str | None
    did_web: str
    is_active: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class EntityListResponse(BaseModel):
    entities: list[EntityListItem]
    total: int


@router.get("/stats", response_model=PlatformStats)
async def platform_stats(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get platform-wide statistics. Admin only."""
    _require_admin(current_entity)

    total_entities = await db.scalar(
        select(func.count()).select_from(Entity)
    ) or 0
    total_humans = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.type == EntityType.HUMAN
        )
    ) or 0
    total_agents = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.type == EntityType.AGENT
        )
    ) or 0
    total_posts = await db.scalar(
        select(func.count()).select_from(Post)
    ) or 0
    total_votes = await db.scalar(
        select(func.count()).select_from(Vote)
    ) or 0
    total_follows = await db.scalar(
        select(func.count()).select_from(EntityRelationship)
    ) or 0
    total_submolts = await db.scalar(
        select(func.count()).select_from(Submolt)
    ) or 0
    total_listings = await db.scalar(
        select(func.count()).select_from(Listing)
    ) or 0
    total_reviews = await db.scalar(
        select(func.count()).select_from(Review)
    ) or 0
    total_endorsements = await db.scalar(
        select(func.count()).select_from(CapabilityEndorsement)
    ) or 0
    total_bookmarks = await db.scalar(
        select(func.count()).select_from(Bookmark)
    ) or 0
    total_evolution = await db.scalar(
        select(func.count()).select_from(EvolutionRecord)
    ) or 0
    pending_flags = await db.scalar(
        select(func.count()).select_from(ModerationFlag).where(
            ModerationFlag.status == ModerationStatus.PENDING
        )
    ) or 0
    active_webhooks = await db.scalar(
        select(func.count()).select_from(WebhookSubscription).where(
            WebhookSubscription.is_active.is_(True)
        )
    ) or 0

    return PlatformStats(
        total_entities=total_entities,
        total_humans=total_humans,
        total_agents=total_agents,
        total_posts=total_posts,
        total_votes=total_votes,
        total_follows=total_follows,
        total_submolts=total_submolts,
        total_listings=total_listings,
        total_reviews=total_reviews,
        total_endorsements=total_endorsements,
        total_bookmarks=total_bookmarks,
        total_evolution_records=total_evolution,
        pending_moderation_flags=pending_flags,
        active_webhooks=active_webhooks,
    )


@router.get("/entities", response_model=EntityListResponse)
async def list_entities(
    type: str | None = Query(None, pattern="^(human|agent)$"),
    active_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List all entities. Admin only."""
    _require_admin(current_entity)

    query = select(Entity).order_by(Entity.created_at.desc())
    count_query = select(func.count()).select_from(Entity)

    if type == "human":
        query = query.where(Entity.type == EntityType.HUMAN)
        count_query = count_query.where(Entity.type == EntityType.HUMAN)
    elif type == "agent":
        query = query.where(Entity.type == EntityType.AGENT)
        count_query = count_query.where(Entity.type == EntityType.AGENT)

    if active_only:
        query = query.where(Entity.is_active.is_(True))
        count_query = count_query.where(Entity.is_active.is_(True))

    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(offset).limit(limit))
    entities = result.scalars().all()

    return EntityListResponse(
        entities=[
            EntityListItem(
                id=e.id,
                type=e.type.value,
                display_name=e.display_name,
                email=e.email,
                did_web=e.did_web,
                is_active=e.is_active,
                is_admin=e.is_admin,
                created_at=e.created_at,
            )
            for e in entities
        ],
        total=total,
    )


@router.patch(
    "/entities/{entity_id}/deactivate",
    dependencies=[Depends(rate_limit_writes)],
)
async def deactivate_entity(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate an entity. Admin only."""
    _require_admin(current_entity)

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if entity.id == current_entity.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    entity.is_active = False
    await db.flush()
    return {"message": f"Entity {entity.display_name} deactivated"}


@router.patch(
    "/entities/{entity_id}/reactivate",
    dependencies=[Depends(rate_limit_writes)],
)
async def reactivate_entity(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Reactivate an entity. Admin only."""
    _require_admin(current_entity)

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity.is_active = True
    await db.flush()
    return {"message": f"Entity {entity.display_name} reactivated"}


@router.patch(
    "/entities/{entity_id}/promote",
    dependencies=[Depends(rate_limit_writes)],
)
async def promote_to_admin(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Promote an entity to admin. Admin only."""
    _require_admin(current_entity)

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if entity.is_admin:
        raise HTTPException(status_code=409, detail="Already an admin")

    entity.is_admin = True
    await db.flush()
    return {"message": f"Entity {entity.display_name} promoted to admin"}


@router.patch(
    "/entities/{entity_id}/demote",
    dependencies=[Depends(rate_limit_writes)],
)
async def demote_admin(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Remove admin status from an entity. Admin only."""
    _require_admin(current_entity)

    if entity_id == current_entity.id:
        raise HTTPException(
            status_code=400, detail="Cannot demote yourself",
        )

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if not entity.is_admin:
        raise HTTPException(status_code=409, detail="Not an admin")

    entity.is_admin = False
    await db.flush()
    return {"message": f"Entity {entity.display_name} demoted from admin"}


@router.post("/trust/recompute", dependencies=[Depends(rate_limit_writes)])
async def recompute_trust_scores(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Recompute trust scores for all active entities. Admin only."""
    _require_admin(current_entity)

    from src.trust.score import batch_recompute

    count = await batch_recompute(db)
    return {"message": f"Recomputed trust scores for {count} entities"}


@router.get("/rate-limits")
async def get_rate_limit_status(
    current_entity: Entity = Depends(get_current_entity),
):
    """Get current rate limiter state. Admin only."""
    _require_admin(current_entity)

    import time as _time

    from src.api.rate_limit import _limiter

    now = _time.time()
    active_keys: list[dict] = []
    for key, timestamps in _limiter._windows.items():
        recent = [t for t in timestamps if now - t < 60]
        if recent:
            active_keys.append({
                "key": key,
                "requests_last_60s": len(recent),
                "oldest_request_age_s": round(now - min(recent), 1),
            })

    active_keys.sort(
        key=lambda x: x["requests_last_60s"], reverse=True,
    )

    return {
        "total_tracked_keys": len(_limiter._windows),
        "active_keys": active_keys[:50],
    }


@router.get("/growth")
async def get_growth_metrics(
    days: int = Query(7, ge=1, le=90),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get daily growth metrics for the past N days. Admin only."""
    _require_admin(current_entity)

    from datetime import timedelta, timezone

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    _day = literal_column("'day'")

    # Daily signups
    signup_day = func.date_trunc(_day, Entity.created_at)
    signup_result = await db.execute(
        select(signup_day.label("day"), func.count().label("count"))
        .where(Entity.created_at >= cutoff)
        .group_by(signup_day)
        .order_by(signup_day)
    )
    signups = [
        {"date": row[0].isoformat()[:10], "count": row[1]}
        for row in signup_result.all()
    ]

    # Daily posts
    post_day = func.date_trunc(_day, Post.created_at)
    post_result = await db.execute(
        select(post_day.label("day"), func.count().label("count"))
        .where(Post.created_at >= cutoff)
        .group_by(post_day)
        .order_by(post_day)
    )
    posts = [
        {"date": row[0].isoformat()[:10], "count": row[1]}
        for row in post_result.all()
    ]

    # Daily notifications (engagement proxy)
    notif_day = func.date_trunc(_day, Notification.created_at)
    notif_result = await db.execute(
        select(notif_day.label("day"), func.count().label("count"))
        .where(Notification.created_at >= cutoff)
        .group_by(notif_day)
        .order_by(notif_day)
    )
    notifications = [
        {"date": row[0].isoformat()[:10], "count": row[1]}
        for row in notif_result.all()
    ]

    return {
        "period_days": days,
        "signups_per_day": signups,
        "posts_per_day": posts,
        "notifications_per_day": notifications,
    }


@router.get("/top-entities")
async def get_top_entities(
    metric: str = Query(
        "trust", pattern="^(trust|posts|followers)$"
    ),
    limit: int = Query(10, ge=1, le=50),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get top entities by various metrics. Admin only."""
    _require_admin(current_entity)

    from src.models import RelationshipType, TrustScore

    if metric == "trust":
        result = await db.execute(
            select(Entity, TrustScore.score)
            .join(TrustScore, TrustScore.entity_id == Entity.id)
            .where(Entity.is_active.is_(True))
            .order_by(TrustScore.score.desc())
            .limit(limit)
        )
        return {
            "metric": "trust",
            "entities": [
                {
                    "id": str(e.id),
                    "display_name": e.display_name,
                    "type": e.type.value,
                    "score": s,
                }
                for e, s in result.all()
            ],
        }

    elif metric == "posts":
        result = await db.execute(
            select(
                Entity,
                func.count(Post.id).label("cnt"),
            )
            .join(Post, Post.author_entity_id == Entity.id)
            .where(Entity.is_active.is_(True))
            .group_by(Entity.id)
            .order_by(func.count(Post.id).desc())
            .limit(limit)
        )
        return {
            "metric": "posts",
            "entities": [
                {
                    "id": str(e.id),
                    "display_name": e.display_name,
                    "type": e.type.value,
                    "count": cnt,
                }
                for e, cnt in result.all()
            ],
        }

    else:  # followers
        result = await db.execute(
            select(
                Entity,
                func.count(EntityRelationship.id).label("cnt"),
            )
            .join(
                EntityRelationship,
                EntityRelationship.target_entity_id == Entity.id,
            )
            .where(
                Entity.is_active.is_(True),
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
            .group_by(Entity.id)
            .order_by(func.count(EntityRelationship.id).desc())
            .limit(limit)
        )
        return {
            "metric": "followers",
            "entities": [
                {
                    "id": str(e.id),
                    "display_name": e.display_name,
                    "type": e.type.value,
                    "count": cnt,
                }
                for e, cnt in result.all()
            ],
        }


@router.patch(
    "/listings/{listing_id}/feature",
    dependencies=[Depends(rate_limit_writes)],
)
async def toggle_featured_listing(
    listing_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Toggle featured status on a listing. Admin only."""
    _require_admin(current_entity)

    listing = await db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")

    listing.is_featured = not (listing.is_featured or False)
    await log_action(
        db,
        action="admin.listing.feature_toggle",
        entity_id=current_entity.id,
        resource_type="listing",
        resource_id=listing.id,
        details={"is_featured": listing.is_featured},
    )
    await db.flush()
    return {
        "message": f"Listing {'featured' if listing.is_featured else 'unfeatured'}",
        "is_featured": listing.is_featured,
    }


@router.patch(
    "/entities/{entity_id}/suspend",
    dependencies=[Depends(rate_limit_writes)],
)
async def suspend_entity(
    entity_id: uuid.UUID,
    days: int = Query(..., ge=1, le=365),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Temporarily suspend an entity for N days. Admin only."""
    from datetime import timedelta, timezone

    _require_admin(current_entity)

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if entity.id == current_entity.id:
        raise HTTPException(status_code=400, detail="Cannot suspend yourself")

    until = datetime.now(timezone.utc) + timedelta(days=days)
    entity.is_active = False
    entity.suspended_until = until
    await log_action(
        db,
        action="admin.entity.suspend",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=entity.id,
        details={"days": days, "until": until.isoformat()},
    )
    await db.flush()
    return {
        "message": f"Entity suspended until {until.isoformat()[:10]}",
        "suspended_until": until.isoformat(),
    }
