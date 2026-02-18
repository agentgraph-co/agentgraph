"""Entity activity timeline endpoints.

Shows a chronological view of an entity's public actions:
posts, replies, votes, follows, profile updates.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rate_limit import rate_limit_reads
from src.database import get_db
from src.models import (
    Entity,
    EntityRelationship,
    Post,
    RelationshipType,
    Vote,
)

router = APIRouter(prefix="/activity", tags=["activity"])


class ActivityItem(BaseModel):
    type: str  # "post", "reply", "vote", "follow"
    entity_id: str
    entity_name: str
    target_id: str | None = None
    summary: str
    created_at: datetime


class ActivityResponse(BaseModel):
    activities: list[ActivityItem]
    count: int


@router.get(
    "/{entity_id}", response_model=ActivityResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_activity(
    entity_id: uuid.UUID,
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get the public activity timeline for an entity."""
    entity = await db.get(Entity, entity_id)
    if entity is None or not entity.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    activities: list[ActivityItem] = []

    # Posts
    posts_result = await db.execute(
        select(Post)
        .where(
            Post.author_entity_id == entity_id,
            Post.is_hidden.is_(False),
        )
        .order_by(Post.created_at.desc())
        .limit(limit)
    )
    for post in posts_result.scalars().all():
        if post.parent_post_id:
            activities.append(ActivityItem(
                type="reply",
                entity_id=str(entity_id),
                entity_name=entity.display_name,
                target_id=str(post.parent_post_id),
                summary=post.content[:100],
                created_at=post.created_at,
            ))
        else:
            activities.append(ActivityItem(
                type="post",
                entity_id=str(entity_id),
                entity_name=entity.display_name,
                target_id=str(post.id),
                summary=post.content[:100],
                created_at=post.created_at,
            ))

    # Votes
    votes_result = await db.execute(
        select(Vote)
        .where(Vote.entity_id == entity_id)
        .order_by(Vote.created_at.desc())
        .limit(limit)
    )
    for vote in votes_result.scalars().all():
        activities.append(ActivityItem(
            type="vote",
            entity_id=str(entity_id),
            entity_name=entity.display_name,
            target_id=str(vote.post_id),
            summary=f"{vote.direction.value}voted a post",
            created_at=vote.created_at,
        ))

    # Follows
    follows_result = await db.execute(
        select(EntityRelationship, Entity)
        .join(Entity, EntityRelationship.target_entity_id == Entity.id)
        .where(
            EntityRelationship.source_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
        .order_by(EntityRelationship.created_at.desc())
        .limit(limit)
    )
    for rel, target in follows_result.all():
        activities.append(ActivityItem(
            type="follow",
            entity_id=str(entity_id),
            entity_name=entity.display_name,
            target_id=str(target.id),
            summary=f"Followed {target.display_name}",
            created_at=rel.created_at,
        ))

    # Sort all by time, take top N
    activities.sort(key=lambda a: a.created_at, reverse=True)
    activities = activities[:limit]

    return ActivityResponse(
        activities=activities,
        count=len(activities),
    )
