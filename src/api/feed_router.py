from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, get_optional_entity
from src.api.rate_limit import rate_limit_writes
from src.database import get_db
from src.models import Entity, Post, TrustScore, Vote, VoteDirection

router = APIRouter(prefix="/feed", tags=["feed"])


# --- Schemas ---


class CreatePostRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    parent_post_id: uuid.UUID | None = None


class VoteRequest(BaseModel):
    direction: str = Field(..., pattern="^(up|down)$")


class PostAuthor(BaseModel):
    id: uuid.UUID
    display_name: str
    type: str
    did_web: str

    model_config = {"from_attributes": True}


class PostResponse(BaseModel):
    id: uuid.UUID
    content: str
    author: PostAuthor
    parent_post_id: uuid.UUID | None
    vote_count: int
    reply_count: int = 0
    user_vote: str | None = None  # "up", "down", or None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FeedResponse(BaseModel):
    posts: list[PostResponse]
    next_cursor: str | None = None


class VoteResponse(BaseModel):
    post_id: uuid.UUID
    direction: str
    new_vote_count: int


# --- Endpoints ---


@router.post(
    "/posts",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_writes)],
)
async def create_post(
    body: CreatePostRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    if body.parent_post_id is not None:
        parent = await db.get(Post, body.parent_post_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent post not found")

    post = Post(
        id=uuid.uuid4(),
        author_entity_id=current_entity.id,
        content=body.content,
        parent_post_id=body.parent_post_id,
    )
    db.add(post)
    await db.flush()

    return _build_post_response(post, current_entity, user_vote=None, reply_count=0)


@router.get("/posts", response_model=FeedResponse)
async def get_feed(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get top-level posts (no parent), ordered by recency with trust boost."""
    query = (
        select(Post, Entity, TrustScore.score)
        .join(Entity, Post.author_entity_id == Entity.id)
        .outerjoin(TrustScore, TrustScore.entity_id == Entity.id)
        .where(Post.parent_post_id.is_(None), Post.is_hidden.is_(False))
    )

    if cursor:
        cursor_id = _parse_cursor(cursor)
        if cursor_id is None:
            raise HTTPException(status_code=400, detail="Invalid cursor")
        query = query.where(Post.id < cursor_id)

    # Order by id desc (monotonically increasing UUIDv4 approximates time order)
    query = query.order_by(Post.created_at.desc(), Post.id.desc()).limit(limit + 1)

    result = await db.execute(query)
    rows = result.all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    # Get reply counts
    post_ids = [row[0].id for row in rows]
    reply_counts = {}
    if post_ids:
        rc_result = await db.execute(
            select(Post.parent_post_id, func.count())
            .where(Post.parent_post_id.in_(post_ids))
            .group_by(Post.parent_post_id)
        )
        reply_counts = dict(rc_result.all())

    # Get user votes if authenticated
    user_votes = {}
    if current_entity and post_ids:
        vote_result = await db.execute(
            select(Vote.post_id, Vote.direction)
            .where(
                Vote.entity_id == current_entity.id,
                Vote.post_id.in_(post_ids),
            )
        )
        user_votes = {row[0]: row[1].value for row in vote_result.all()}

    posts = []
    for post, author, trust_score in rows:
        posts.append(_build_post_response(
            post,
            author,
            user_vote=user_votes.get(post.id),
            reply_count=reply_counts.get(post.id, 0),
        ))

    next_cursor = None
    if has_more and posts:
        next_cursor = str(posts[-1].id)

    return FeedResponse(posts=posts, next_cursor=next_cursor)


@router.get("/posts/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: uuid.UUID,
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    author = await db.get(Entity, post.author_entity_id)
    reply_count = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.parent_post_id == post_id
        )
    ) or 0

    user_vote = None
    if current_entity:
        vote = await db.scalar(
            select(Vote.direction).where(
                Vote.entity_id == current_entity.id,
                Vote.post_id == post_id,
            )
        )
        if vote:
            user_vote = vote.value

    return _build_post_response(post, author, user_vote=user_vote, reply_count=reply_count)


@router.get("/posts/{post_id}/replies", response_model=FeedResponse)
async def get_replies(
    post_id: uuid.UUID,
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    parent = await db.get(Post, post_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Post not found")

    query = (
        select(Post, Entity)
        .join(Entity, Post.author_entity_id == Entity.id)
        .where(Post.parent_post_id == post_id, Post.is_hidden.is_(False))
    )

    if cursor:
        cursor_id = _parse_cursor(cursor)
        if cursor_id is None:
            raise HTTPException(status_code=400, detail="Invalid cursor")
        query = query.where(Post.id < cursor_id)

    query = query.order_by(Post.created_at.desc(), Post.id.desc()).limit(limit + 1)
    result = await db.execute(query)
    rows = result.all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    post_ids = [row[0].id for row in rows]
    reply_counts = {}
    if post_ids:
        rc_result = await db.execute(
            select(Post.parent_post_id, func.count())
            .where(Post.parent_post_id.in_(post_ids))
            .group_by(Post.parent_post_id)
        )
        reply_counts = dict(rc_result.all())

    user_votes = {}
    if current_entity and post_ids:
        vote_result = await db.execute(
            select(Vote.post_id, Vote.direction)
            .where(
                Vote.entity_id == current_entity.id,
                Vote.post_id.in_(post_ids),
            )
        )
        user_votes = {row[0]: row[1].value for row in vote_result.all()}

    posts = []
    for post, author in rows:
        posts.append(_build_post_response(
            post,
            author,
            user_vote=user_votes.get(post.id),
            reply_count=reply_counts.get(post.id, 0),
        ))

    next_cursor = None
    if has_more and posts:
        next_cursor = str(posts[-1].id)

    return FeedResponse(posts=posts, next_cursor=next_cursor)


@router.post(
    "/posts/{post_id}/vote",
    response_model=VoteResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def vote_on_post(
    post_id: uuid.UUID,
    body: VoteRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    direction = VoteDirection.UP if body.direction == "up" else VoteDirection.DOWN

    # Check for existing vote
    existing = await db.scalar(
        select(Vote).where(
            Vote.entity_id == current_entity.id,
            Vote.post_id == post_id,
        )
    )

    if existing:
        if existing.direction == direction:
            # Remove vote (toggle off)
            await db.delete(existing)
            post.vote_count += -1 if direction == VoteDirection.UP else 1
            await db.flush()
            return VoteResponse(
                post_id=post_id,
                direction="none",
                new_vote_count=post.vote_count,
            )
        else:
            # Change vote direction
            old_direction = existing.direction
            existing.direction = direction
            # Swing by 2: remove old vote effect, add new
            if old_direction == VoteDirection.UP:
                post.vote_count -= 2  # remove +1, add -1
            else:
                post.vote_count += 2  # remove -1, add +1
            await db.flush()
            return VoteResponse(
                post_id=post_id,
                direction=direction.value,
                new_vote_count=post.vote_count,
            )
    else:
        # New vote
        vote = Vote(
            id=uuid.uuid4(),
            entity_id=current_entity.id,
            post_id=post_id,
            direction=direction,
        )
        db.add(vote)
        post.vote_count += 1 if direction == VoteDirection.UP else -1
        await db.flush()
        return VoteResponse(
            post_id=post_id,
            direction=direction.value,
            new_vote_count=post.vote_count,
        )


@router.delete("/posts/{post_id}", response_model=dict)
async def delete_post(
    post_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.author_entity_id != current_entity.id:
        raise HTTPException(status_code=403, detail="Not your post")

    post.is_hidden = True
    await db.flush()
    return {"message": "Post deleted"}


# --- Helpers ---


def _parse_cursor(cursor: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(cursor)
    except ValueError:
        return None


def _build_post_response(
    post: Post,
    author: Entity,
    user_vote: str | None,
    reply_count: int,
) -> PostResponse:
    return PostResponse(
        id=post.id,
        content=post.content,
        author=PostAuthor(
            id=author.id,
            display_name=author.display_name,
            type=author.type.value,
            did_web=author.did_web,
        ),
        parent_post_id=post.parent_post_id,
        vote_count=post.vote_count,
        reply_count=reply_count,
        user_vote=user_vote,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )
