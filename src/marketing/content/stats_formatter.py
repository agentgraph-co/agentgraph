"""Pulls live DB stats and formats them for social posts."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_weekly_stats(db: AsyncSession) -> dict:
    """Pull platform stats for the last 7 days."""
    from src.models import Entity, EntityType, Listing, Post

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # Total counts
    total_entities_q = await db.execute(
        select(func.count()).select_from(Entity).where(Entity.is_active.is_(True)),
    )
    total_entities = total_entities_q.scalar() or 0

    total_agents_q = await db.execute(
        select(func.count()).select_from(Entity).where(
            Entity.is_active.is_(True), Entity.type == EntityType.AGENT,
        ),
    )
    total_agents = total_agents_q.scalar() or 0

    total_humans = total_entities - total_agents

    # New this week
    new_agents_q = await db.execute(
        select(func.count()).select_from(Entity).where(
            Entity.type == EntityType.AGENT, Entity.created_at >= week_ago,
        ),
    )
    new_agents = new_agents_q.scalar() or 0

    new_humans_q = await db.execute(
        select(func.count()).select_from(Entity).where(
            Entity.type == EntityType.HUMAN, Entity.created_at >= week_ago,
        ),
    )
    new_humans = new_humans_q.scalar() or 0

    # Posts this week
    posts_q = await db.execute(
        select(func.count()).select_from(Post).where(Post.created_at >= week_ago),
    )
    posts_this_week = posts_q.scalar() or 0

    total_posts_q = await db.execute(select(func.count()).select_from(Post))
    total_posts = total_posts_q.scalar() or 0

    # Listings
    new_listings_q = await db.execute(
        select(func.count()).select_from(Listing).where(Listing.created_at >= week_ago),
    )
    new_listings = new_listings_q.scalar() or 0

    total_listings_q = await db.execute(select(func.count()).select_from(Listing))
    total_listings = total_listings_q.scalar() or 0

    # Date range string
    date_range = f"{week_ago.strftime('%b %d')} - {now.strftime('%b %d, %Y')}"

    return {
        "new_agents": new_agents,
        "new_humans": new_humans,
        "total_entities": total_entities,
        "total_agents": total_agents,
        "total_humans": total_humans,
        "posts_this_week": posts_this_week,
        "total_posts": total_posts,
        "new_listings": new_listings,
        "total_listings": total_listings,
        "trust_updates": total_entities,  # Trust recompute touches all
        "date_range": date_range,
        "top_agent": "TBD",
        "trending_topic": "agent identity",
    }
