from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_writes
from src.database import get_db
from src.models import (
    Entity,
    EntityBlock,
    EntityRelationship,
    Post,
    RelationshipType,
    SubmoltMembership,
    TrustScore,
)

router = APIRouter(prefix="/social", tags=["social"])


class FollowResponse(BaseModel):
    message: str


class EntitySummary(BaseModel):
    id: uuid.UUID
    type: str
    display_name: str
    did_web: str

    model_config = {"from_attributes": True}


class FollowListResponse(BaseModel):
    entities: list[EntitySummary]
    count: int
    total: int = 0


@router.post(
    "/follow/{target_id}",
    response_model=FollowResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def follow_entity(
    target_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    if current_entity.id == target_id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")

    target = await db.get(Entity, target_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Check if blocked
    is_blocked = await db.scalar(
        select(EntityBlock).where(
            EntityBlock.blocker_id == target_id,
            EntityBlock.blocked_id == current_entity.id,
        )
    )
    if is_blocked:
        raise HTTPException(
            status_code=403, detail="Cannot follow this entity"
        )

    # Check if already following
    existing = await db.scalar(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id == current_entity.id,
            EntityRelationship.target_entity_id == target_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Already following")

    rel = EntityRelationship(
        id=uuid.uuid4(),
        source_entity_id=current_entity.id,
        target_entity_id=target_id,
        type=RelationshipType.FOLLOW,
    )
    db.add(rel)
    await db.flush()

    # Notify the target
    from src.api.notification_router import create_notification

    await create_notification(
        db,
        entity_id=target_id,
        kind="follow",
        title="New follower",
        body=f"{current_entity.display_name} started following you",
        reference_id=str(current_entity.id),
    )

    return FollowResponse(message=f"Now following {target.display_name}")


@router.delete("/follow/{target_id}", response_model=FollowResponse)
async def unfollow_entity(
    target_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.scalar(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id == current_entity.id,
            EntityRelationship.target_entity_id == target_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="Not following this entity")

    await db.delete(existing)
    await db.flush()
    return FollowResponse(message="Unfollowed")


class BulkFollowRequest(BaseModel):
    entity_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=50)


@router.post(
    "/bulk-follow",
    dependencies=[Depends(rate_limit_writes)],
)
async def bulk_follow(
    body: BulkFollowRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Follow multiple entities at once. Returns per-item results."""
    # Pre-load blocks against current entity
    blocks_result = await db.execute(
        select(EntityBlock.blocker_id).where(
            EntityBlock.blocked_id == current_entity.id,
            EntityBlock.blocker_id.in_(body.entity_ids),
        )
    )
    blocker_ids = {row[0] for row in blocks_result.all()}

    # Pre-load existing follows
    existing_result = await db.execute(
        select(EntityRelationship.target_entity_id).where(
            EntityRelationship.source_entity_id == current_entity.id,
            EntityRelationship.target_entity_id.in_(body.entity_ids),
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    already_following = {row[0] for row in existing_result.all()}

    results = []
    followed = 0
    for target_id in body.entity_ids:
        if target_id == current_entity.id:
            results.append({"id": str(target_id), "status": "skipped", "reason": "self"})
            continue
        if target_id in blocker_ids:
            results.append({"id": str(target_id), "status": "blocked"})
            continue
        if target_id in already_following:
            results.append({"id": str(target_id), "status": "already_following"})
            continue

        target = await db.get(Entity, target_id)
        if target is None or not target.is_active:
            results.append({"id": str(target_id), "status": "not_found"})
            continue

        rel = EntityRelationship(
            id=uuid.uuid4(),
            source_entity_id=current_entity.id,
            target_entity_id=target_id,
            type=RelationshipType.FOLLOW,
        )
        db.add(rel)
        followed += 1
        results.append({"id": str(target_id), "status": "followed"})

    await db.flush()
    return {"followed": followed, "results": results}


@router.post(
    "/bulk-unfollow",
    dependencies=[Depends(rate_limit_writes)],
)
async def bulk_unfollow(
    body: BulkFollowRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Unfollow multiple entities at once. Returns per-item results."""
    existing_result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id == current_entity.id,
            EntityRelationship.target_entity_id.in_(body.entity_ids),
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    existing_map = {
        rel.target_entity_id: rel
        for rel in existing_result.scalars().all()
    }

    results = []
    unfollowed = 0
    for target_id in body.entity_ids:
        rel = existing_map.get(target_id)
        if rel is None:
            results.append({"id": str(target_id), "status": "not_following"})
            continue
        await db.delete(rel)
        unfollowed += 1
        results.append({"id": str(target_id), "status": "unfollowed"})

    await db.flush()
    return {"unfollowed": unfollowed, "results": results}


@router.get("/following/{entity_id}", response_model=FollowListResponse)
async def get_following(
    entity_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get entities that this entity follows."""
    base_filter = [
        EntityRelationship.source_entity_id == entity_id,
        EntityRelationship.type == RelationshipType.FOLLOW,
    ]
    total = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(*base_filter)
    ) or 0

    result = await db.execute(
        select(Entity)
        .join(
            EntityRelationship,
            EntityRelationship.target_entity_id == Entity.id,
        )
        .where(
            *base_filter,
            Entity.is_active.is_(True),
        )
        .order_by(EntityRelationship.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    entities = result.scalars().all()
    return FollowListResponse(
        entities=[
            EntitySummary(
                id=e.id,
                type=e.type.value,
                display_name=e.display_name,
                did_web=e.did_web,
            )
            for e in entities
        ],
        count=len(entities),
        total=total,
    )


@router.get("/followers/{entity_id}", response_model=FollowListResponse)
async def get_followers(
    entity_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get entities that follow this entity."""
    base_filter = [
        EntityRelationship.target_entity_id == entity_id,
        EntityRelationship.type == RelationshipType.FOLLOW,
    ]
    total = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(*base_filter)
    ) or 0

    result = await db.execute(
        select(Entity)
        .join(
            EntityRelationship,
            EntityRelationship.source_entity_id == Entity.id,
        )
        .where(
            *base_filter,
            Entity.is_active.is_(True),
        )
        .order_by(EntityRelationship.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    entities = result.scalars().all()
    return FollowListResponse(
        entities=[
            EntitySummary(
                id=e.id,
                type=e.type.value,
                display_name=e.display_name,
                did_web=e.did_web,
            )
            for e in entities
        ],
        count=len(entities),
        total=total,
    )


@router.get("/stats/{entity_id}")
async def get_social_stats(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    following_count = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(
            EntityRelationship.source_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    ) or 0

    followers_count = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(
            EntityRelationship.target_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    ) or 0

    return {
        "entity_id": str(entity_id),
        "following_count": following_count,
        "followers_count": followers_count,
    }


# --- Blocking ---


@router.post("/block/{target_id}")
async def block_entity(
    target_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Block an entity. Also removes any follow relationship."""
    if current_entity.id == target_id:
        raise HTTPException(
            status_code=400, detail="Cannot block yourself"
        )

    target = await db.get(Entity, target_id)
    if target is None:
        raise HTTPException(
            status_code=404, detail="Entity not found"
        )

    existing = await db.scalar(
        select(EntityBlock).where(
            EntityBlock.blocker_id == current_entity.id,
            EntityBlock.blocked_id == target_id,
        )
    )
    if existing:
        raise HTTPException(
            status_code=409, detail="Already blocked"
        )

    block = EntityBlock(
        id=uuid.uuid4(),
        blocker_id=current_entity.id,
        blocked_id=target_id,
    )
    db.add(block)

    # Remove follow if exists
    follow = await db.scalar(
        select(EntityRelationship).where(
            EntityRelationship.source_entity_id == current_entity.id,
            EntityRelationship.target_entity_id == target_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    if follow:
        await db.delete(follow)

    await db.flush()
    return {"message": f"Blocked {target.display_name}"}


@router.delete("/block/{target_id}")
async def unblock_entity(
    target_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Unblock an entity."""
    existing = await db.scalar(
        select(EntityBlock).where(
            EntityBlock.blocker_id == current_entity.id,
            EntityBlock.blocked_id == target_id,
        )
    )
    if not existing:
        raise HTTPException(
            status_code=404, detail="Not blocked"
        )

    await db.delete(existing)
    await db.flush()
    return {"message": "Unblocked"}


@router.get("/blocked")
async def list_blocked(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List entities blocked by the current user."""
    total = await db.scalar(
        select(func.count()).select_from(EntityBlock).where(
            EntityBlock.blocker_id == current_entity.id,
        )
    ) or 0

    result = await db.execute(
        select(EntityBlock, Entity)
        .join(Entity, EntityBlock.blocked_id == Entity.id)
        .where(EntityBlock.blocker_id == current_entity.id)
        .order_by(EntityBlock.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = result.all()

    return {
        "blocked": [
            {
                "entity_id": str(block.blocked_id),
                "display_name": entity.display_name,
                "type": entity.type.value,
                "blocked_at": block.created_at.isoformat(),
            }
            for block, entity in rows
        ],
        "count": len(rows),
        "total": total,
    }


# --- Suggested Follows ---


@router.get("/suggested")
async def get_suggested_follows(
    limit: int = 10,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Suggest entities to follow based on trust score and activity.

    Excludes already-followed entities, blocked entities, and self.
    """
    # Get already followed IDs
    following = await db.execute(
        select(EntityRelationship.target_entity_id).where(
            EntityRelationship.source_entity_id == current_entity.id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    followed_ids = {row[0] for row in following.all()}
    followed_ids.add(current_entity.id)

    # Get blocked IDs
    blocked = await db.execute(
        select(EntityBlock.blocked_id).where(
            EntityBlock.blocker_id == current_entity.id,
        )
    )
    blocked_ids = {row[0] for row in blocked.all()}
    exclude_ids = followed_ids | blocked_ids

    # Find top entities by trust score that aren't followed
    query = (
        select(Entity, TrustScore.score)
        .outerjoin(TrustScore, TrustScore.entity_id == Entity.id)
        .where(
            Entity.is_active.is_(True),
            Entity.id.notin_(exclude_ids) if exclude_ids else True,
        )
        .order_by(
            func.coalesce(TrustScore.score, 0).desc(),
            Entity.created_at.desc(),
        )
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    return {
        "suggestions": [
            {
                "id": str(entity.id),
                "type": entity.type.value,
                "display_name": entity.display_name,
                "did_web": entity.did_web,
                "bio_markdown": entity.bio_markdown or "",
                "trust_score": score,
            }
            for entity, score in rows
        ],
    }


# --- Pin/Unpin Posts ---


@router.post("/pin/{post_id}")
async def pin_post(
    post_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Pin a post in its submolt. Requires submolt moderator/owner role."""
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.submolt_id is None:
        raise HTTPException(
            status_code=400,
            detail="Only submolt posts can be pinned",
        )

    # Check submolt role
    membership = await db.scalar(
        select(SubmoltMembership).where(
            SubmoltMembership.submolt_id == post.submolt_id,
            SubmoltMembership.entity_id == current_entity.id,
        )
    )
    if not membership or membership.role not in ("owner", "moderator"):
        raise HTTPException(
            status_code=403,
            detail="Must be a submolt moderator or owner to pin posts",
        )

    post.is_pinned = not post.is_pinned
    await db.flush()
    return {
        "post_id": str(post_id),
        "is_pinned": post.is_pinned,
    }
