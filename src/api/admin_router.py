from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deactivation import cascade_deactivate
from src.api.deps import get_current_entity, require_admin
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import (
    AnalyticsEvent,
    AuditLog,
    Bookmark,
    CapabilityEndorsement,
    EmailVerification,
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
    Transaction,
    TransactionStatus,
    Vote,
    WebhookSubscription,
)
from src.utils import like_pattern

router = APIRouter(prefix="/admin", tags=["admin"])


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
    total_transactions: int
    total_revenue_cents: int
    active_entities_30d: int


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


class UnverifiedEntityItem(BaseModel):
    id: uuid.UUID
    email: str | None
    display_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UnverifiedEntitiesResponse(BaseModel):
    entities: list[UnverifiedEntityItem]
    total: int


class EmailStatsResponse(BaseModel):
    unverified_count: int
    registered_last_24h: int
    verified_last_24h: int


@router.get(
    "/stats", response_model=PlatformStats,
    dependencies=[Depends(rate_limit_reads)],
)
async def platform_stats(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get platform-wide statistics. Admin only."""
    require_admin(current_entity)

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

    total_transactions = await db.scalar(
        select(func.count()).select_from(Transaction)
    ) or 0
    total_revenue = await db.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.status == TransactionStatus.COMPLETED,
        )
    ) or 0

    from datetime import timedelta
    from datetime import timezone as _tz

    cutoff_30d = datetime.now(_tz.utc) - timedelta(days=30)
    active_30d = await db.scalar(
        select(func.count(func.distinct(Post.author_entity_id))).where(
            Post.created_at >= cutoff_30d,
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
        total_transactions=total_transactions,
        total_revenue_cents=total_revenue,
        active_entities_30d=active_30d,
    )


@router.get(
    "/entities", response_model=EntityListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_entities(
    type: str | None = Query(None, pattern="^(human|agent)$"),
    q: str | None = Query(None, max_length=200),
    active_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List all entities. Admin only. Use q to search by name or email."""
    require_admin(current_entity)

    from sqlalchemy import or_

    query = select(Entity).order_by(Entity.created_at.desc())
    count_query = select(func.count()).select_from(Entity)

    if type == "human":
        query = query.where(Entity.type == EntityType.HUMAN)
        count_query = count_query.where(Entity.type == EntityType.HUMAN)
    elif type == "agent":
        query = query.where(Entity.type == EntityType.AGENT)
        count_query = count_query.where(Entity.type == EntityType.AGENT)

    if q:
        pattern = like_pattern(q)
        search_filter = or_(
            Entity.display_name.ilike(pattern),
            Entity.email.ilike(pattern),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

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
    require_admin(current_entity)

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if entity.id == current_entity.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    entity.is_active = False
    await db.flush()

    cascade = await cascade_deactivate(
        db, entity_id, performed_by=current_entity.id,
    )

    return {
        "message": f"Entity {entity.display_name} deactivated",
        "cascade": cascade,
    }


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
    require_admin(current_entity)

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity.is_active = True
    await db.flush()
    return {"message": f"Entity {entity.display_name} reactivated"}


@router.post(
    "/entities/{entity_id}/verify-email",
    dependencies=[Depends(rate_limit_writes)],
)
async def admin_verify_email(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Force-verify an entity's email. Admin only (for support cases)."""
    require_admin(current_entity)

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    if entity.email_verified:
        return {"message": f"Entity {entity.display_name} is already email-verified"}

    entity.email_verified = True
    await log_action(
        db,
        action="admin.entity.verify_email",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=entity_id,
    )
    await db.flush()
    return {"message": f"Entity {entity.display_name} email verified"}


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
    require_admin(current_entity)

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
    require_admin(current_entity)

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
    require_admin(current_entity)

    from src.trust.score import batch_recompute

    count = await batch_recompute(db)
    return {"message": f"Recomputed trust scores for {count} entities"}


@router.post("/trust/recompute-all", dependencies=[Depends(rate_limit_writes)])
async def recompute_all_trust_scores(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Trigger batch trust recompute with attestation decay and activity weighting.

    This enhanced recompute applies:
    - Attestation decay: >90 days = 50% weight, >180 days = 25% weight
    - Activity recency: last 30 days = 100%, 30-90 days = 50%, >90 days = 25%

    Returns a summary with entities_processed, scores_changed, avg_score,
    and duration_seconds.

    Admin only.
    """
    require_admin(current_entity)

    from src.jobs.trust_recompute import run_trust_recompute

    summary = await run_trust_recompute(db)
    return summary


class TrustDistributionBucket(BaseModel):
    range: str
    count: int


class TrustEntityTypeAvg(BaseModel):
    entity_type: str
    avg_score: float
    count: int


class TrustStatsResponse(BaseModel):
    distribution: list[TrustDistributionBucket]
    avg_by_type: list[TrustEntityTypeAvg]
    total_with_scores: int


@router.get(
    "/trust/stats",
    response_model=TrustStatsResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def trust_distribution_stats(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Trust score distribution stats. Admin only.

    Returns:
    - distribution: count by score range (0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0)
    - avg_by_type: average score per entity type (human vs agent)
    - total_with_scores: total entities that have trust scores
    """
    require_admin(current_entity)

    from src.models import EntityType, TrustScore

    # Distribution buckets
    buckets = [
        ("0.0-0.2", 0.0, 0.2),
        ("0.2-0.4", 0.2, 0.4),
        ("0.4-0.6", 0.4, 0.6),
        ("0.6-0.8", 0.6, 0.8),
        ("0.8-1.0", 0.8, 1.01),  # include 1.0
    ]

    distribution = []
    for label, lo, hi in buckets:
        count = await db.scalar(
            select(func.count()).select_from(TrustScore).where(
                TrustScore.score >= lo,
                TrustScore.score < hi,
            )
        ) or 0
        distribution.append(TrustDistributionBucket(range=label, count=count))

    # Average by entity type
    avg_by_type = []
    for etype in [EntityType.HUMAN, EntityType.AGENT]:
        row = await db.execute(
            select(
                func.avg(TrustScore.score),
                func.count(TrustScore.id),
            )
            .join(Entity, TrustScore.entity_id == Entity.id)
            .where(Entity.type == etype)
        )
        avg_val, cnt = row.one()
        avg_by_type.append(TrustEntityTypeAvg(
            entity_type=etype.value,
            avg_score=round(float(avg_val), 4) if avg_val else 0.0,
            count=cnt or 0,
        ))

    total_with_scores = await db.scalar(
        select(func.count()).select_from(TrustScore)
    ) or 0

    return TrustStatsResponse(
        distribution=distribution,
        avg_by_type=avg_by_type,
        total_with_scores=total_with_scores,
    )


@router.get("/rate-limits", dependencies=[Depends(rate_limit_reads)])
async def get_rate_limit_status(
    current_entity: Entity = Depends(get_current_entity),
):
    """Get current rate limiter state. Admin only."""
    require_admin(current_entity)

    import time as _time

    from src.api.rate_limit import _limiter

    now = _time.time()
    active_keys: list[dict] = []

    # Try Redis first for accurate cross-worker data
    try:
        from src.redis_client import get_redis

        r = get_redis()
        keys = []
        async for rk in r.scan_iter(match="rl:*", count=100):
            keys.append(rk)
            if len(keys) >= 200:
                break
        for rk in keys:
            await r.zremrangebyscore(rk, 0, now - 60)
            count = await r.zcard(rk)
            if count > 0:
                oldest = await r.zrange(rk, 0, 0, withscores=True)
                age = round(now - oldest[0][1], 1) if oldest else 0
                active_keys.append({
                    "key": rk.replace("rl:", "", 1) if isinstance(rk, str) else rk,
                    "requests_last_60s": count,
                    "oldest_request_age_s": age,
                })
    except Exception:
        # Fallback to in-memory data
        for key, timestamps in _limiter._fallback.items():
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
        "total_tracked_keys": len(active_keys),
        "active_keys": active_keys[:50],
    }


@router.get("/growth", dependencies=[Depends(rate_limit_reads)])
async def get_growth_metrics(
    days: int = Query(7, ge=1, le=90),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get daily growth metrics for the past N days. Admin only."""
    require_admin(current_entity)

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


@router.get("/top-entities", dependencies=[Depends(rate_limit_reads)])
async def get_top_entities(
    metric: str = Query(
        "trust", pattern="^(trust|posts|followers)$"
    ),
    limit: int = Query(10, ge=1, le=50),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get top entities by various metrics. Admin only."""
    require_admin(current_entity)

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
    require_admin(current_entity)

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

    require_admin(current_entity)

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

    cascade = await cascade_deactivate(
        db, entity.id, performed_by=current_entity.id,
    )

    return {
        "message": f"Entity suspended until {until.isoformat()[:10]}",
        "suspended_until": until.isoformat(),
        "cascade": cascade,
    }


@router.post("/cleanup/token-blacklist", dependencies=[Depends(rate_limit_writes)])
async def cleanup_token_blacklist(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Remove expired entries from the token blacklist. Admin only."""
    require_admin(current_entity)

    from src.api.auth_service import cleanup_expired_blacklist

    removed = await cleanup_expired_blacklist(db)
    return {"message": f"Removed {removed} expired blacklist entries", "removed": removed}


@router.patch(
    "/posts/{post_id}/hide",
    dependencies=[Depends(rate_limit_writes)],
)
async def admin_hide_post(
    post_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Hide a post (soft delete). Admin only."""
    require_admin(current_entity)

    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.is_hidden:
        return {"message": "Post is already hidden"}

    post.is_hidden = True
    await log_action(
        db,
        action="admin.post.hide",
        entity_id=current_entity.id,
        resource_type="post",
        resource_id=post.id,
    )
    await db.flush()
    return {"message": "Post hidden"}


@router.get("/audit-logs", dependencies=[Depends(rate_limit_reads)])
async def query_audit_logs(
    action: str | None = Query(None, description="Filter by action prefix"),
    entity_id: uuid.UUID | None = Query(None),
    resource_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Query audit logs with filters. Admin only."""
    require_admin(current_entity)

    base = select(AuditLog)
    count_base = select(func.count()).select_from(AuditLog)

    if action:
        base = base.where(AuditLog.action.startswith(action))
        count_base = count_base.where(AuditLog.action.startswith(action))
    if entity_id:
        base = base.where(AuditLog.entity_id == entity_id)
        count_base = count_base.where(AuditLog.entity_id == entity_id)
    if resource_type:
        base = base.where(AuditLog.resource_type == resource_type)
        count_base = count_base.where(AuditLog.resource_type == resource_type)

    total = await db.scalar(count_base) or 0

    result = await db.execute(
        base.order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    logs = result.scalars().all()

    return {
        "logs": [
            {
                "id": str(log.id),
                "entity_id": str(log.entity_id) if log.entity_id else None,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": str(log.resource_id) if log.resource_id else None,
                "details": log.details or {},
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# --- Email Verification Management ---


@router.get(
    "/email-verifications",
    response_model=UnverifiedEntitiesResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_unverified_entities(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List active entities with unverified emails. Admin only.

    Returns paginated list of entities where email_verified=False and is_active=True.
    Useful for identifying users who may need a verification email resend.
    """
    require_admin(current_entity)

    base_filter = (
        Entity.email_verified.is_(False),
        Entity.is_active.is_(True),
    )

    total = await db.scalar(
        select(func.count()).select_from(Entity).where(*base_filter)
    ) or 0

    result = await db.execute(
        select(Entity)
        .where(*base_filter)
        .order_by(Entity.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    entities = result.scalars().all()

    return UnverifiedEntitiesResponse(
        entities=[
            UnverifiedEntityItem(
                id=e.id,
                email=e.email,
                display_name=e.display_name,
                created_at=e.created_at,
            )
            for e in entities
        ],
        total=total,
    )


@router.post(
    "/email-verifications/{entity_id}/resend",
    dependencies=[Depends(rate_limit_writes)],
)
async def resend_verification_email(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Resend verification email to an entity. Admin only.

    Creates a new verification token (invalidating any previous ones)
    and sends a verification email to the entity's address.
    """
    require_admin(current_entity)

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if not entity.is_active:
        raise HTTPException(status_code=400, detail="Entity is deactivated")
    if entity.email_verified:
        raise HTTPException(status_code=409, detail="Entity email is already verified")
    if not entity.email:
        raise HTTPException(status_code=400, detail="Entity has no email address")

    from src.api.auth_service import create_verification_token
    from src.email import send_verification_email

    token = await create_verification_token(db, entity.id)
    sent = await send_verification_email(entity.email, token)

    await log_action(
        db,
        action="admin.email_verification.resend",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=entity.id,
        details={"email_sent": sent},
    )
    await db.flush()

    if not sent:
        raise HTTPException(
            status_code=502,
            detail="Verification token created but email delivery failed",
        )

    return {"message": f"Verification email resent to {entity.email}"}


@router.get(
    "/email-stats",
    response_model=EmailStatsResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def email_verification_stats(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Quick email verification health overview. Admin only.

    Returns:
    - unverified_count: active entities with email_verified=False
    - registered_last_24h: entities created in the last 24 hours
    - verified_last_24h: entities that verified their email in the last 24 hours
    """
    require_admin(current_entity)

    from datetime import timedelta
    from datetime import timezone as _tz

    now = datetime.now(_tz.utc)
    cutoff_24h = now - timedelta(hours=24)

    unverified_count = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.email_verified.is_(False),
            Entity.is_active.is_(True),
        )
    ) or 0

    registered_last_24h = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.created_at >= cutoff_24h,
        )
    ) or 0

    # Entities verified in last 24h: look for used verification tokens consumed recently
    verified_last_24h = await db.scalar(
        select(func.count(func.distinct(EmailVerification.entity_id)))
        .where(
            EmailVerification.is_used.is_(True),
            EmailVerification.created_at >= cutoff_24h,
        )
    ) or 0

    return EmailStatsResponse(
        unverified_count=unverified_count,
        registered_last_24h=registered_last_24h,
        verified_last_24h=verified_last_24h,
    )


# ---------------------------------------------------------------------------
# TestFlight Waitlist
# ---------------------------------------------------------------------------


class WaitlistEntry(BaseModel):
    email: str
    submitted_at: str
    page: str
    session_id: str


class WaitlistResponse(BaseModel):
    entries: list[WaitlistEntry]
    total: int


@router.get(
    "/waitlist",
    response_model=WaitlistResponse,
)
async def get_waitlist(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List all iOS TestFlight waitlist signups."""
    require_admin(current_entity)
    result = await db.execute(
        select(AnalyticsEvent)
        .where(AnalyticsEvent.event_type == "ios_waitlist")
        .order_by(AnalyticsEvent.created_at.desc())
    )
    events = result.scalars().all()

    entries = []
    for ev in events:
        meta = ev.extra_metadata or {}
        email = meta.get("email", "")
        if email:
            entries.append(
                WaitlistEntry(
                    email=email,
                    submitted_at=ev.created_at.isoformat() if ev.created_at else "",
                    page=ev.page or "",
                    session_id=ev.session_id or "",
                )
            )

    return WaitlistResponse(entries=entries, total=len(entries))
