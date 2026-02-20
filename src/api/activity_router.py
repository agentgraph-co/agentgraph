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
    CapabilityEndorsement,
    Entity,
    EntityRelationship,
    Post,
    RelationshipType,
    Review,
    Vote,
)

router = APIRouter(prefix="/activity", tags=["activity"])


class ActivityItem(BaseModel):
    type: str  # "post", "reply", "vote", "follow", "endorsement", "review"
    entity_id: str
    entity_name: str
    target_id: str | None = None
    summary: str
    created_at: datetime


class ActivityResponse(BaseModel):
    activities: list[ActivityItem]
    count: int
    next_cursor: str | None = None


@router.get(
    "/{entity_id}", response_model=ActivityResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_activity(
    entity_id: uuid.UUID,
    limit: int = Query(30, ge=1, le=100),
    before: str | None = Query(None, description="ISO timestamp cursor"),
    db: AsyncSession = Depends(get_db),
):
    """Get the public activity timeline for an entity."""
    entity = await db.get(Entity, entity_id)
    if entity is None or not entity.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    before_dt: datetime | None = None
    if before:
        try:
            # Python 3.9 fromisoformat doesn't handle 'Z' suffix
            before_dt = datetime.fromisoformat(before.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid cursor format")

    # Build all 5 queries upfront
    posts_q = select(Post).where(
        Post.author_entity_id == entity_id,
        Post.is_hidden.is_(False),
    )
    votes_q = select(Vote).where(Vote.entity_id == entity_id)
    follows_q = (
        select(EntityRelationship, Entity)
        .join(Entity, EntityRelationship.target_entity_id == Entity.id)
        .where(
            EntityRelationship.source_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
        )
    )
    endorse_q = (
        select(CapabilityEndorsement, Entity)
        .join(Entity, CapabilityEndorsement.agent_entity_id == Entity.id)
        .where(
            CapabilityEndorsement.endorser_entity_id == entity_id,
            Entity.is_active.is_(True),
        )
    )
    review_q = (
        select(Review, Entity)
        .join(Entity, Review.target_entity_id == Entity.id)
        .where(
            Review.reviewer_entity_id == entity_id,
            Entity.is_active.is_(True),
        )
    )

    if before_dt:
        posts_q = posts_q.where(Post.created_at < before_dt)
        votes_q = votes_q.where(Vote.created_at < before_dt)
        follows_q = follows_q.where(EntityRelationship.created_at < before_dt)
        endorse_q = endorse_q.where(CapabilityEndorsement.created_at < before_dt)
        review_q = review_q.where(Review.created_at < before_dt)

    # Execute queries sequentially (AsyncSession is single-connection)
    posts_result = await db.execute(
        posts_q.order_by(Post.created_at.desc()).limit(limit)
    )
    votes_result = await db.execute(
        votes_q.order_by(Vote.created_at.desc()).limit(limit)
    )
    follows_result = await db.execute(
        follows_q.order_by(EntityRelationship.created_at.desc()).limit(limit)
    )
    endorse_result = await db.execute(
        endorse_q.order_by(CapabilityEndorsement.created_at.desc()).limit(limit)
    )
    review_result = await db.execute(
        review_q.order_by(Review.created_at.desc()).limit(limit)
    )

    activities: list[ActivityItem] = []
    eid = str(entity_id)
    name = entity.display_name

    for post in posts_result.scalars().all():
        if post.parent_post_id:
            activities.append(ActivityItem(
                type="reply", entity_id=eid, entity_name=name,
                target_id=str(post.parent_post_id),
                summary=post.content[:100], created_at=post.created_at,
            ))
        else:
            activities.append(ActivityItem(
                type="post", entity_id=eid, entity_name=name,
                target_id=str(post.id),
                summary=post.content[:100], created_at=post.created_at,
            ))

    for vote in votes_result.scalars().all():
        activities.append(ActivityItem(
            type="vote", entity_id=eid, entity_name=name,
            target_id=str(vote.post_id),
            summary=f"{vote.direction.value}voted a post",
            created_at=vote.created_at,
        ))

    for rel, target in follows_result.all():
        activities.append(ActivityItem(
            type="follow", entity_id=eid, entity_name=name,
            target_id=str(target.id),
            summary=f"Followed {target.display_name}",
            created_at=rel.created_at,
        ))

    for endorsement, agent in endorse_result.all():
        activities.append(ActivityItem(
            type="endorsement", entity_id=eid, entity_name=name,
            target_id=str(agent.id),
            summary=f"Endorsed {agent.display_name}'s '{endorsement.capability}'",
            created_at=endorsement.created_at,
        ))

    for review, target in review_result.all():
        activities.append(ActivityItem(
            type="review", entity_id=eid, entity_name=name,
            target_id=str(target.id),
            summary=f"Reviewed {target.display_name} ({review.rating}/5)",
            created_at=review.created_at,
        ))

    # Sort all by time, take top N
    activities.sort(key=lambda a: a.created_at, reverse=True)
    activities = activities[:limit]

    next_cursor = None
    if len(activities) == limit:
        ts = activities[-1].created_at
        # Use Z suffix for URL-safe cursor (no + encoding issues)
        iso = ts.isoformat()
        if iso.endswith("+00:00"):
            iso = iso[:-6] + "Z"
        next_cursor = iso

    return ActivityResponse(
        activities=activities,
        count=len(activities),
        next_cursor=next_cursor,
    )
