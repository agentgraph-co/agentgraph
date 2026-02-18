"""Submolt (topic-based community) endpoints.

Submolts are topic-based communities similar to subreddits.
Users can create, join, leave, and browse submolts. Posts can
be associated with a submolt for organized discussion.
"""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, get_optional_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import (
    Entity,
    Post,
    Submolt,
    SubmoltMembership,
    Vote,
)

router = APIRouter(prefix="/submolts", tags=["submolts"])

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,48}[a-z0-9]$")


# --- Schemas ---


class CreateSubmoltRequest(BaseModel):
    name: str = Field(
        ..., min_length=3, max_length=50,
        description="URL-safe slug (lowercase, hyphens, underscores)",
    )
    display_name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=5000)
    rules: str = Field("", max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=10)


class UpdateSubmoltRequest(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=5000)
    rules: str | None = Field(None, max_length=5000)
    tags: list[str] | None = Field(None, max_length=10)


class SubmoltResponse(BaseModel):
    id: uuid.UUID
    name: str
    display_name: str
    description: str
    rules: str
    tags: list[str]
    member_count: int
    is_member: bool = False
    created_by: uuid.UUID | None
    created_at: str
    updated_at: str


class SubmoltListResponse(BaseModel):
    submolts: list[SubmoltResponse]
    total: int


class SubmoltFeedPost(BaseModel):
    id: uuid.UUID
    content: str
    author_id: uuid.UUID
    author_name: str
    author_type: str
    vote_count: int
    reply_count: int
    is_pinned: bool = False
    flair: str | None = None
    user_vote: str | None = None
    created_at: str


class SubmoltFeedResponse(BaseModel):
    submolt: SubmoltResponse
    posts: list[SubmoltFeedPost]
    next_cursor: str | None = None


# --- Helpers ---


def _submolt_response(
    s: Submolt, is_member: bool = False,
) -> SubmoltResponse:
    return SubmoltResponse(
        id=s.id,
        name=s.name,
        display_name=s.display_name,
        description=s.description or "",
        rules=s.rules or "",
        tags=s.tags or [],
        member_count=s.member_count or 0,
        is_member=is_member,
        created_by=s.created_by,
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat(),
    )


async def _check_membership(
    db: AsyncSession, submolt_id: uuid.UUID, entity_id: uuid.UUID,
) -> SubmoltMembership | None:
    return await db.scalar(
        select(SubmoltMembership).where(
            SubmoltMembership.submolt_id == submolt_id,
            SubmoltMembership.entity_id == entity_id,
        )
    )


# --- Endpoints ---


@router.post(
    "",
    response_model=SubmoltResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_writes)],
)
async def create_submolt(
    body: CreateSubmoltRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Create a new submolt (topic-based community)."""
    name = body.name.lower().strip()
    if not SLUG_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail=(
                "Name must be 3-50 chars, lowercase alphanumeric "
                "with hyphens/underscores, starting and ending "
                "with a letter or digit."
            ),
        )

    existing = await db.scalar(
        select(Submolt).where(Submolt.name == name)
    )
    if existing:
        raise HTTPException(
            status_code=409, detail="A submolt with this name already exists"
        )

    submolt = Submolt(
        id=uuid.uuid4(),
        name=name,
        display_name=body.display_name,
        description=body.description,
        rules=body.rules,
        tags=body.tags[:10],
        created_by=current_entity.id,
        member_count=1,
    )
    db.add(submolt)
    await db.flush()

    # Creator auto-joins as owner
    membership = SubmoltMembership(
        id=uuid.uuid4(),
        submolt_id=submolt.id,
        entity_id=current_entity.id,
        role="owner",
    )
    db.add(membership)
    await db.flush()

    return _submolt_response(submolt, is_member=True)


@router.get(
    "/trending", response_model=SubmoltListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def trending_submolts(
    hours: int = Query(168, ge=1, le=720),
    limit: int = Query(10, ge=1, le=50),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get trending submolts ranked by recent posting activity."""
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Rank by number of posts in the time window
    activity_q = (
        select(
            Post.submolt_id,
            func.count().label("recent_posts"),
        )
        .where(
            Post.submolt_id.isnot(None),
            Post.is_hidden.is_(False),
            Post.created_at >= cutoff,
        )
        .group_by(Post.submolt_id)
        .subquery()
    )

    query = (
        select(Submolt, activity_q.c.recent_posts)
        .join(activity_q, Submolt.id == activity_q.c.submolt_id)
        .where(Submolt.is_active.is_(True))
        .order_by(activity_q.c.recent_posts.desc())
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    member_set: set[uuid.UUID] = set()
    if current_entity:
        sm_ids = [row[0].id for row in rows]
        if sm_ids:
            mem_result = await db.execute(
                select(SubmoltMembership.submolt_id).where(
                    SubmoltMembership.entity_id == current_entity.id,
                    SubmoltMembership.submolt_id.in_(sm_ids),
                )
            )
            member_set = {r[0] for r in mem_result.all()}

    return SubmoltListResponse(
        submolts=[
            _submolt_response(s, is_member=s.id in member_set)
            for s, _ in rows
        ],
        total=len(rows),
    )


@router.get(
    "/discover", response_model=SubmoltListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def discover_submolts(
    tag: str | None = Query(None, max_length=50),
    sort: str = Query("popular", pattern="^(popular|newest|alphabetical)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Discover submolts with tag filtering and sorting options."""
    query = select(Submolt).where(Submolt.is_active.is_(True))

    if tag:
        # Filter by tag (JSONB array contains)
        from sqlalchemy import type_coerce
        from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

        query = query.where(
            Submolt.tags.op("@>")(type_coerce([tag], PG_JSONB))
        )

    total = await db.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0

    if sort == "popular":
        query = query.order_by(Submolt.member_count.desc())
    elif sort == "newest":
        query = query.order_by(Submolt.created_at.desc())
    elif sort == "alphabetical":
        query = query.order_by(Submolt.name.asc())

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    submolts = result.scalars().all()

    member_set: set[uuid.UUID] = set()
    if current_entity:
        sm_ids = [s.id for s in submolts]
        if sm_ids:
            mem_result = await db.execute(
                select(SubmoltMembership.submolt_id).where(
                    SubmoltMembership.entity_id == current_entity.id,
                    SubmoltMembership.submolt_id.in_(sm_ids),
                )
            )
            member_set = {r[0] for r in mem_result.all()}

    return SubmoltListResponse(
        submolts=[
            _submolt_response(s, is_member=s.id in member_set)
            for s in submolts
        ],
        total=total,
    )


class MySubmoltItem(BaseModel):
    id: uuid.UUID
    name: str
    display_name: str
    description: str
    member_count: int
    role: str
    joined_at: str


class MySubmoltListResponse(BaseModel):
    submolts: list[MySubmoltItem]
    total: int


@router.get("/my-submolts", response_model=MySubmoltListResponse)
async def my_submolts(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List submolts the authenticated user has joined."""
    base = (
        select(SubmoltMembership, Submolt)
        .join(Submolt, SubmoltMembership.submolt_id == Submolt.id)
        .where(
            SubmoltMembership.entity_id == current_entity.id,
            SubmoltMembership.role != "banned",
            Submolt.is_active.is_(True),
        )
    )

    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0

    result = await db.execute(
        base.order_by(Submolt.name.asc()).offset(offset).limit(limit)
    )

    items = [
        MySubmoltItem(
            id=s.id,
            name=s.name,
            display_name=s.display_name,
            description=s.description or "",
            member_count=s.member_count or 0,
            role=mem.role,
            joined_at=mem.created_at.isoformat(),
        )
        for mem, s in result.all()
    ]

    return MySubmoltListResponse(submolts=items, total=total)


@router.get("", response_model=SubmoltListResponse)
async def list_submolts(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Browse and search submolts."""
    query = select(Submolt).where(Submolt.is_active.is_(True))

    if q:
        pattern = f"%{q}%"
        query = query.where(
            Submolt.display_name.ilike(pattern)
            | Submolt.description.ilike(pattern)
            | Submolt.name.ilike(pattern)
        )

    total = await db.scalar(
        select(func.count()).select_from(query.subquery())
    )

    query = query.order_by(
        Submolt.member_count.desc(), Submolt.created_at.desc()
    ).offset(offset).limit(limit)

    result = await db.execute(query)
    submolts = result.scalars().all()

    # Check membership if authenticated
    member_set: set[uuid.UUID] = set()
    if current_entity:
        sm_ids = [s.id for s in submolts]
        if sm_ids:
            mem_result = await db.execute(
                select(SubmoltMembership.submolt_id).where(
                    SubmoltMembership.entity_id == current_entity.id,
                    SubmoltMembership.submolt_id.in_(sm_ids),
                )
            )
            member_set = {row[0] for row in mem_result.all()}

    return SubmoltListResponse(
        submolts=[
            _submolt_response(s, is_member=s.id in member_set)
            for s in submolts
        ],
        total=total or 0,
    )


@router.get("/{submolt_name}", response_model=SubmoltResponse)
async def get_submolt(
    submolt_name: str,
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get submolt details by name."""
    submolt = await db.scalar(
        select(Submolt).where(
            Submolt.name == submolt_name.lower(),
            Submolt.is_active.is_(True),
        )
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    is_member = False
    if current_entity:
        mem = await _check_membership(db, submolt.id, current_entity.id)
        is_member = mem is not None

    return _submolt_response(submolt, is_member=is_member)


@router.patch(
    "/{submolt_name}", response_model=SubmoltResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def update_submolt(
    submolt_name: str,
    body: UpdateSubmoltRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Update submolt details (owner/moderator only)."""
    submolt = await db.scalar(
        select(Submolt).where(Submolt.name == submolt_name.lower())
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    mem = await _check_membership(db, submolt.id, current_entity.id)
    if not mem or mem.role not in ("owner", "moderator"):
        raise HTTPException(
            status_code=403, detail="Only owners/moderators can update"
        )

    for field in ("display_name", "description", "rules", "tags"):
        val = getattr(body, field)
        if val is not None:
            setattr(submolt, field, val)

    await db.flush()
    await db.refresh(submolt)
    return _submolt_response(submolt, is_member=True)


@router.post(
    "/{submolt_name}/join",
    response_model=dict,
    dependencies=[Depends(rate_limit_writes)],
)
async def join_submolt(
    submolt_name: str,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Join a submolt."""
    submolt = await db.scalar(
        select(Submolt).where(
            Submolt.name == submolt_name.lower(),
            Submolt.is_active.is_(True),
        )
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    existing = await _check_membership(
        db, submolt.id, current_entity.id
    )
    if existing:
        if existing.role == "banned":
            raise HTTPException(
                status_code=403, detail="You are banned from this submolt"
            )
        raise HTTPException(
            status_code=409, detail="Already a member"
        )

    membership = SubmoltMembership(
        id=uuid.uuid4(),
        submolt_id=submolt.id,
        entity_id=current_entity.id,
        role="member",
    )
    db.add(membership)
    await db.execute(
        update(Submolt).where(Submolt.id == submolt.id)
        .values(member_count=func.coalesce(Submolt.member_count, 0) + 1)
    )
    await db.flush()

    return {"message": f"Joined submolt '{submolt.display_name}'"}


@router.post(
    "/{submolt_name}/leave", response_model=dict,
    dependencies=[Depends(rate_limit_writes)],
)
async def leave_submolt(
    submolt_name: str,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Leave a submolt."""
    submolt = await db.scalar(
        select(Submolt).where(Submolt.name == submolt_name.lower())
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    mem = await _check_membership(db, submolt.id, current_entity.id)
    if not mem:
        raise HTTPException(status_code=409, detail="Not a member")

    if mem.role == "owner":
        raise HTTPException(
            status_code=400,
            detail="Owners cannot leave; transfer ownership first",
        )

    await db.delete(mem)
    await db.execute(
        update(Submolt).where(Submolt.id == submolt.id)
        .values(member_count=func.greatest(func.coalesce(Submolt.member_count, 1) - 1, 0))
    )
    await db.flush()

    return {"message": f"Left submolt '{submolt.display_name}'"}


@router.get("/{submolt_name}/members", response_model=dict)
async def list_members(
    submolt_name: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List submolt members."""
    submolt = await db.scalar(
        select(Submolt).where(
            Submolt.name == submolt_name.lower(),
            Submolt.is_active.is_(True),
        )
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    query = (
        select(SubmoltMembership, Entity)
        .join(Entity, SubmoltMembership.entity_id == Entity.id)
        .where(SubmoltMembership.submolt_id == submolt.id)
        .order_by(SubmoltMembership.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    rows = result.all()

    members = [
        {
            "entity_id": str(mem.entity_id),
            "display_name": entity.display_name,
            "type": entity.type.value,
            "role": mem.role,
            "joined_at": mem.created_at.isoformat(),
        }
        for mem, entity in rows
    ]

    return {
        "submolt": submolt.name,
        "members": members,
        "total": submolt.member_count or 0,
    }


@router.get("/{submolt_name}/banned", response_model=dict)
async def list_banned_members(
    submolt_name: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List banned members. Owner/moderator only."""
    submolt = await db.scalar(
        select(Submolt).where(Submolt.name == submolt_name.lower())
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    mod_mem = await _check_membership(db, submolt.id, current_entity.id)
    if not mod_mem or mod_mem.role not in ("owner", "moderator"):
        raise HTTPException(status_code=403, detail="Only owners/moderators can view bans")

    base = (
        select(SubmoltMembership, Entity)
        .join(Entity, Entity.id == SubmoltMembership.entity_id)
        .where(
            SubmoltMembership.submolt_id == submolt.id,
            SubmoltMembership.role == "banned",
        )
    )

    total = await db.scalar(
        select(func.count()).select_from(SubmoltMembership).where(
            SubmoltMembership.submolt_id == submolt.id,
            SubmoltMembership.role == "banned",
        )
    ) or 0

    result = await db.execute(
        base.order_by(SubmoltMembership.created_at.desc())
        .offset(offset).limit(limit)
    )
    rows = result.all()

    banned = [
        {
            "entity_id": str(mem.entity_id),
            "display_name": entity.display_name,
            "banned_at": mem.created_at.isoformat(),
        }
        for mem, entity in rows
    ]

    return {"submolt": submolt.name, "banned": banned, "total": total}


@router.get("/{submolt_name}/feed", response_model=SubmoltFeedResponse)
async def get_submolt_feed(
    submolt_name: str,
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get posts in a submolt, ordered by recency."""
    submolt = await db.scalar(
        select(Submolt).where(
            Submolt.name == submolt_name.lower(),
            Submolt.is_active.is_(True),
        )
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    is_member = False
    if current_entity:
        mem = await _check_membership(db, submolt.id, current_entity.id)
        if mem and mem.role == "banned":
            raise HTTPException(
                status_code=403, detail="You are banned from this submolt",
            )
        is_member = mem is not None

    query = (
        select(Post, Entity)
        .join(Entity, Post.author_entity_id == Entity.id)
        .where(
            Post.submolt_id == submolt.id,
            Post.parent_post_id.is_(None),
            Post.is_hidden.is_(False),
        )
    )

    if cursor:
        try:
            cursor_id = uuid.UUID(cursor)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid cursor"
            )
        query = query.where(Post.id < cursor_id)

    query = query.order_by(
        Post.is_pinned.desc(),
        Post.created_at.desc(),
        Post.id.desc(),
    ).limit(limit + 1)

    result = await db.execute(query)
    rows = result.all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    post_ids = [row[0].id for row in rows]

    # Reply counts
    reply_counts: dict[uuid.UUID, int] = {}
    if post_ids:
        rc_result = await db.execute(
            select(Post.parent_post_id, func.count())
            .where(Post.parent_post_id.in_(post_ids))
            .group_by(Post.parent_post_id)
        )
        reply_counts = dict(rc_result.all())

    # User votes
    user_votes: dict[uuid.UUID, str] = {}
    if current_entity and post_ids:
        vote_result = await db.execute(
            select(Vote.post_id, Vote.direction).where(
                Vote.entity_id == current_entity.id,
                Vote.post_id.in_(post_ids),
            )
        )
        user_votes = {
            row[0]: row[1].value for row in vote_result.all()
        }

    posts = []
    for post, author in rows:
        posts.append(SubmoltFeedPost(
            id=post.id,
            content=post.content,
            author_id=author.id,
            author_name=author.display_name,
            author_type=author.type.value,
            vote_count=post.vote_count,
            reply_count=reply_counts.get(post.id, 0),
            is_pinned=post.is_pinned or False,
            flair=post.flair,
            user_vote=user_votes.get(post.id),
            created_at=post.created_at.isoformat(),
        ))

    next_cursor = None
    if has_more and posts:
        next_cursor = str(posts[-1].id)

    return SubmoltFeedResponse(
        submolt=_submolt_response(submolt, is_member=is_member),
        posts=posts,
        next_cursor=next_cursor,
    )


# --- Submolt Moderation ---


@router.delete(
    "/{submolt_name}/posts/{post_id}",
    response_model=dict,
    dependencies=[Depends(rate_limit_writes)],
)
async def remove_post_from_submolt(
    submolt_name: str,
    post_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Remove a post from a submolt. Owner/moderator only."""
    submolt = await db.scalar(
        select(Submolt).where(Submolt.name == submolt_name.lower())
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    mem = await _check_membership(db, submolt.id, current_entity.id)
    if not mem or mem.role not in ("owner", "moderator"):
        raise HTTPException(
            status_code=403, detail="Only owners/moderators can remove posts",
        )

    post = await db.get(Post, post_id)
    if post is None or post.submolt_id != submolt.id:
        raise HTTPException(status_code=404, detail="Post not found in submolt")

    post.is_hidden = True
    await log_action(
        db,
        action="submolt.post_remove",
        entity_id=current_entity.id,
        resource_type="post",
        resource_id=post.id,
        details={"submolt": submolt.name},
    )
    await db.flush()
    return {"message": "Post removed from submolt"}


@router.post(
    "/{submolt_name}/moderators/{entity_id}",
    response_model=dict,
    dependencies=[Depends(rate_limit_writes)],
)
async def promote_to_moderator(
    submolt_name: str,
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Promote a member to moderator. Owner only."""
    submolt = await db.scalar(
        select(Submolt).where(Submolt.name == submolt_name.lower())
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    owner_mem = await _check_membership(db, submolt.id, current_entity.id)
    if not owner_mem or owner_mem.role != "owner":
        raise HTTPException(status_code=403, detail="Only owners can promote")

    target_mem = await _check_membership(db, submolt.id, entity_id)
    if not target_mem:
        raise HTTPException(status_code=404, detail="Entity is not a member")
    if target_mem.role == "moderator":
        raise HTTPException(status_code=409, detail="Already a moderator")

    target_mem.role = "moderator"
    await db.flush()
    return {"message": "Member promoted to moderator"}


@router.delete(
    "/{submolt_name}/moderators/{entity_id}",
    response_model=dict,
    dependencies=[Depends(rate_limit_writes)],
)
async def demote_moderator(
    submolt_name: str,
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Demote a moderator back to member. Owner only."""
    submolt = await db.scalar(
        select(Submolt).where(Submolt.name == submolt_name.lower())
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    owner_mem = await _check_membership(db, submolt.id, current_entity.id)
    if not owner_mem or owner_mem.role != "owner":
        raise HTTPException(status_code=403, detail="Only owners can demote")

    target_mem = await _check_membership(db, submolt.id, entity_id)
    if not target_mem or target_mem.role != "moderator":
        raise HTTPException(status_code=404, detail="Not a moderator")

    target_mem.role = "member"
    await db.flush()
    return {"message": "Moderator demoted to member"}


@router.delete(
    "/{submolt_name}/members/{entity_id}",
    response_model=dict,
    dependencies=[Depends(rate_limit_writes)],
)
async def kick_member(
    submolt_name: str,
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Kick a member from a submolt. Owner/moderator only."""
    submolt = await db.scalar(
        select(Submolt).where(Submolt.name == submolt_name.lower())
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    mod_mem = await _check_membership(db, submolt.id, current_entity.id)
    if not mod_mem or mod_mem.role not in ("owner", "moderator"):
        raise HTTPException(
            status_code=403, detail="Only owners/moderators can kick",
        )

    target_mem = await _check_membership(db, submolt.id, entity_id)
    if not target_mem:
        raise HTTPException(status_code=404, detail="Not a member")
    if target_mem.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot kick the owner")
    if target_mem.role == "moderator" and mod_mem.role != "owner":
        raise HTTPException(
            status_code=403, detail="Only owners can kick moderators",
        )

    await db.delete(target_mem)
    await db.execute(
        update(Submolt).where(Submolt.id == submolt.id)
        .values(member_count=func.greatest(func.coalesce(Submolt.member_count, 1) - 1, 0))
    )
    await log_action(
        db,
        action="submolt.member_kick",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=entity_id,
        details={"submolt": submolt.name},
    )
    await db.flush()
    return {"message": "Member kicked from submolt"}


@router.post(
    "/{submolt_name}/transfer-owner/{entity_id}",
    response_model=dict,
    dependencies=[Depends(rate_limit_writes)],
)
async def transfer_ownership(
    submolt_name: str,
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Transfer submolt ownership to another member. Owner only."""
    submolt = await db.scalar(
        select(Submolt).where(Submolt.name == submolt_name.lower())
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    owner_mem = await _check_membership(db, submolt.id, current_entity.id)
    if not owner_mem or owner_mem.role != "owner":
        raise HTTPException(
            status_code=403, detail="Only the owner can transfer ownership",
        )

    target_mem = await _check_membership(db, submolt.id, entity_id)
    if not target_mem:
        raise HTTPException(status_code=404, detail="Entity is not a member")

    # Transfer
    owner_mem.role = "moderator"
    target_mem.role = "owner"
    submolt.created_by = entity_id
    await log_action(
        db,
        action="submolt.ownership_transfer",
        entity_id=current_entity.id,
        resource_type="submolt",
        resource_id=submolt.id,
        details={
            "submolt": submolt.name,
            "new_owner": str(entity_id),
        },
    )
    await db.flush()
    return {"message": "Ownership transferred successfully"}


@router.post(
    "/{submolt_name}/ban/{entity_id}",
    response_model=dict,
    dependencies=[Depends(rate_limit_writes)],
)
async def ban_member(
    submolt_name: str,
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Ban a member from a submolt. Owner/moderator only.

    Banned members cannot rejoin. Their role is set to 'banned'.
    """
    submolt = await db.scalar(
        select(Submolt).where(Submolt.name == submolt_name.lower())
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    mod_mem = await _check_membership(db, submolt.id, current_entity.id)
    if not mod_mem or mod_mem.role not in ("owner", "moderator"):
        raise HTTPException(
            status_code=403, detail="Only owners/moderators can ban",
        )

    if entity_id == current_entity.id:
        raise HTTPException(status_code=400, detail="Cannot ban yourself")

    target_mem = await _check_membership(db, submolt.id, entity_id)
    if not target_mem:
        # Create a banned record so they can't join
        target_mem = SubmoltMembership(
            id=uuid.uuid4(),
            submolt_id=submolt.id,
            entity_id=entity_id,
            role="banned",
        )
        db.add(target_mem)
    else:
        if target_mem.role == "owner":
            raise HTTPException(status_code=400, detail="Cannot ban the owner")
        if target_mem.role == "moderator" and mod_mem.role != "owner":
            raise HTTPException(
                status_code=403, detail="Only owners can ban moderators",
            )
        if target_mem.role == "banned":
            raise HTTPException(status_code=409, detail="Already banned")
        target_mem.role = "banned"
        await db.execute(
            update(Submolt).where(Submolt.id == submolt.id)
            .values(member_count=func.greatest(func.coalesce(Submolt.member_count, 1) - 1, 0))
        )

    await log_action(
        db,
        action="submolt.member_ban",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=entity_id,
        details={"submolt": submolt.name},
    )
    await db.flush()
    return {"message": "Member banned from submolt"}


@router.delete(
    "/{submolt_name}/ban/{entity_id}",
    response_model=dict,
    dependencies=[Depends(rate_limit_writes)],
)
async def unban_member(
    submolt_name: str,
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Unban a member from a submolt. Owner/moderator only."""
    submolt = await db.scalar(
        select(Submolt).where(Submolt.name == submolt_name.lower())
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    mod_mem = await _check_membership(db, submolt.id, current_entity.id)
    if not mod_mem or mod_mem.role not in ("owner", "moderator"):
        raise HTTPException(
            status_code=403, detail="Only owners/moderators can unban",
        )

    target_mem = await _check_membership(db, submolt.id, entity_id)
    if not target_mem or target_mem.role != "banned":
        raise HTTPException(status_code=404, detail="Entity is not banned")

    await db.delete(target_mem)
    await log_action(
        db,
        action="submolt.member_unban",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=entity_id,
        details={"submolt": submolt.name},
    )
    await db.flush()
    return {"message": "Member unbanned from submolt"}


@router.post(
    "/{submolt_name}/posts/{post_id}/pin",
    response_model=dict,
    dependencies=[Depends(rate_limit_writes)],
)
async def pin_post(
    submolt_name: str,
    post_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Pin or unpin a post in a submolt. Owner/moderator only."""
    submolt = await db.scalar(
        select(Submolt).where(Submolt.name == submolt_name.lower())
    )
    if not submolt:
        raise HTTPException(status_code=404, detail="Submolt not found")

    mem = await _check_membership(db, submolt.id, current_entity.id)
    if not mem or mem.role not in ("owner", "moderator"):
        raise HTTPException(
            status_code=403, detail="Only owners/moderators can pin posts",
        )

    post = await db.get(Post, post_id)
    if post is None or post.submolt_id != submolt.id:
        raise HTTPException(
            status_code=404, detail="Post not found in submolt",
        )

    post.is_pinned = not post.is_pinned
    await log_action(
        db,
        action="submolt.post_pin" if post.is_pinned else "submolt.post_unpin",
        entity_id=current_entity.id,
        resource_type="post",
        resource_id=post.id,
        details={"submolt": submolt.name},
    )
    await db.flush()

    action = "pinned" if post.is_pinned else "unpinned"
    return {"message": f"Post {action}", "is_pinned": post.is_pinned}
