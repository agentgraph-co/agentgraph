"""API usage metering for enterprise organizations."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.models import (
    AuditLog,
    Entity,
    EntityType,
    OrganizationMembership,
    OrgUsageRecord,
    Post,
)


async def get_usage_stats(
    db: AsyncSession, org_id: uuid.UUID, days: int = 30,
) -> dict:
    """Get usage statistics for an organization.

    Returns counts of API calls, active members, active agents, and posts
    over the specified time period.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Get member IDs
    members_q = select(OrganizationMembership.entity_id).where(
        OrganizationMembership.organization_id == org_id
    )
    member_result = await db.execute(members_q)
    member_ids = [r[0] for r in member_result.fetchall()]

    if not member_ids:
        return {
            "period_days": days,
            "api_calls": 0,
            "active_members": 0,
            "active_agents": 0,
            "posts": 0,
        }

    # Count audit log entries as proxy for API calls
    api_calls = await db.scalar(
        select(func.count()).select_from(AuditLog)
        .where(AuditLog.entity_id.in_(member_ids), AuditLog.created_at >= since)
    ) or 0

    # Active members (those with recent activity)
    active_members = await db.scalar(
        select(func.count(func.distinct(AuditLog.entity_id)))
        .where(AuditLog.entity_id.in_(member_ids), AuditLog.created_at >= since)
    ) or 0

    # Active agents
    agent_count = await db.scalar(
        select(func.count()).select_from(Entity)
        .where(
            Entity.id.in_(member_ids),
            Entity.type == EntityType.AGENT,
            Entity.is_active.is_(True),
        )
    ) or 0

    # Post count
    post_count = await db.scalar(
        select(func.count()).select_from(Post)
        .where(Post.author_entity_id.in_(member_ids), Post.created_at >= since)
    ) or 0

    return {
        "period_days": days,
        "api_calls": api_calls,
        "active_members": active_members,
        "active_agents": agent_count,
        "posts": post_count,
    }


async def record_usage_snapshot(
    db: AsyncSession, org_id: uuid.UUID,
) -> OrgUsageRecord:
    """Record a usage snapshot for the current period (today).

    Creates an OrgUsageRecord for the current day with stats.
    """
    now = datetime.now(timezone.utc)
    period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + timedelta(days=1)

    stats = await get_usage_stats(db, org_id, days=1)

    record = OrgUsageRecord(
        organization_id=org_id,
        period_start=period_start,
        period_end=period_end,
        api_calls=stats["api_calls"],
        active_agents=stats["active_agents"],
        active_members=stats["active_members"],
    )
    db.add(record)
    return record
