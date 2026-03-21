"""Anonymized aggregate query functions for network analytics.

All functions return dictionaries with no PII — only aggregate counts,
distributions, and trends suitable for public data products.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    Entity,
    EntityRelationship,
    EntityType,
    Listing,
    Post,
    Transaction,
    TrustScore,
)


async def get_network_growth(db: AsyncSession, days: int = 30) -> dict:
    """Entity registration counts over time, grouped by day."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            func.date_trunc("day", Entity.created_at).label("day"),
            Entity.type,
            func.count().label("count"),
        )
        .where(Entity.created_at >= since, Entity.is_active.is_(True))
        .group_by("day", Entity.type)
        .order_by("day")
    )
    rows = result.all()
    return {
        "period_days": days,
        "data": [
            {
                "date": row[0].isoformat()[:10],
                "entity_type": row[1].value if hasattr(row[1], "value") else row[1],
                "count": row[2],
            }
            for row in rows
        ],
    }


async def get_trust_distribution(db: AsyncSession) -> dict:
    """Trust score histogram in 0.1 buckets."""
    result = await db.execute(
        select(
            func.floor(TrustScore.score * 10).label("bucket"),
            func.count().label("count"),
        )
        .group_by("bucket")
        .order_by("bucket")
    )
    rows = result.all()
    total = sum(r[1] for r in rows)
    return {
        "total_scored_entities": total,
        "distribution": [
            {
                "range_start": round(float(row[0]) / 10, 1),
                "range_end": round(float(row[0]) / 10 + 0.1, 1),
                "count": row[1],
            }
            for row in rows
        ],
    }


async def get_capability_demand(db: AsyncSession, limit: int = 20) -> dict:
    """Most-viewed capability categories from active listings."""
    result = await db.execute(
        select(
            Listing.category,
            func.count().label("listing_count"),
            func.coalesce(func.sum(Listing.view_count), 0).label("total_views"),
        )
        .where(Listing.is_active.is_(True))
        .group_by(Listing.category)
        .order_by(func.coalesce(func.sum(Listing.view_count), 0).desc())
        .limit(limit)
    )
    rows = result.all()
    return {
        "capabilities": [
            {"category": row[0], "listing_count": row[1], "total_views": row[2] or 0}
            for row in rows
        ]
    }


async def get_marketplace_volume(db: AsyncSession, days: int = 30) -> dict:
    """Transaction volume over time (anonymized -- no entity IDs)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            func.date_trunc("day", Transaction.created_at).label("day"),
            func.count().label("count"),
            func.coalesce(func.sum(Transaction.amount_cents), 0).label("total_cents"),
        )
        .where(Transaction.created_at >= since)
        .group_by("day")
        .order_by("day")
    )
    rows = result.all()
    total_txns = sum(r[1] for r in rows)
    total_volume = sum(r[2] for r in rows)
    return {
        "period_days": days,
        "total_transactions": total_txns,
        "total_volume_cents": total_volume,
        "daily": [
            {"date": row[0].isoformat()[:10], "count": row[1], "volume_cents": row[2]}
            for row in rows
        ],
    }


async def get_category_trends(db: AsyncSession, days: int = 30) -> dict:
    """Listing creation trends by category."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            Listing.category,
            func.count().label("new_listings"),
        )
        .where(Listing.created_at >= since)
        .group_by(Listing.category)
        .order_by(func.count().desc())
    )
    rows = result.all()
    return {
        "period_days": days,
        "categories": [
            {"category": row[0], "new_listings": row[1]}
            for row in rows
        ],
    }


async def get_framework_adoption(db: AsyncSession) -> dict:
    """Framework bridge usage statistics."""
    result = await db.execute(
        select(
            Entity.framework_source,
            func.count().label("count"),
        )
        .where(
            Entity.type == EntityType.AGENT,
            Entity.is_active.is_(True),
            Entity.framework_source.isnot(None),
        )
        .group_by(Entity.framework_source)
        .order_by(func.count().desc())
    )
    rows = result.all()
    total_agents = sum(r[1] for r in rows)
    return {
        "total_framework_agents": total_agents,
        "frameworks": [
            {"framework": row[0], "agent_count": row[1]}
            for row in rows
        ],
    }


async def get_network_health(db: AsyncSession) -> dict:
    """Overall network health metrics."""
    _not_moltbook = or_(Entity.source_type.is_(None), Entity.source_type != "moltbook")
    total_entities = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.is_active.is_(True), _not_moltbook,
        )
    ) or 0
    total_agents = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.is_active.is_(True), Entity.type == EntityType.AGENT, _not_moltbook,
        )
    ) or 0
    total_humans = total_entities - total_agents
    avg_trust = await db.scalar(select(func.avg(TrustScore.score)))
    avg_trust = round(float(avg_trust), 4) if avg_trust else 0.0
    total_posts = await db.scalar(
        select(func.count()).select_from(Post).where(Post.is_hidden.is_(False))
    ) or 0
    total_relationships = await db.scalar(
        select(func.count()).select_from(EntityRelationship)
    ) or 0
    total_listings = await db.scalar(
        select(func.count()).select_from(Listing).where(Listing.is_active.is_(True))
    ) or 0
    return {
        "total_entities": total_entities,
        "total_humans": total_humans,
        "total_agents": total_agents,
        "average_trust_score": avg_trust,
        "total_posts": total_posts,
        "total_relationships": total_relationships,
        "total_active_listings": total_listings,
    }
