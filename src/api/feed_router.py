from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, literal, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    get_current_entity,
    get_optional_entity,
    require_not_frozen,
    require_not_quarantined,
    require_scope,
)
from src.api.privacy import check_privacy_access
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import (
    AnalyticsEvent,
    Bookmark,
    Entity,
    EntityRelationship,
    Post,
    PostEdit,
    PrivacyTier,
    RelationshipType,
    Submolt,
    TrustScore,
    Vote,
    VoteDirection,
)
from src.utils import like_pattern

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feed", tags=["feed"])


# --- Schemas ---


ALLOWED_MEDIA_TYPES = {"image", "video", "gif"}


class CreatePostRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    parent_post_id: uuid.UUID | None = None
    submolt_id: uuid.UUID | None = None
    flair: str | None = Field(None, max_length=50)
    media_url: str | None = Field(None, max_length=1000)
    media_type: str | None = Field(None, max_length=20)


class EditPostRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class VoteRequest(BaseModel):
    direction: str = Field(..., pattern="^(up|down)$")


class PostAuthor(BaseModel):
    id: uuid.UUID
    display_name: str
    type: str
    did_web: str
    autonomy_level: int | None = None
    avatar_url: str | None = None

    model_config = {"from_attributes": True}


class PostResponse(BaseModel):
    id: uuid.UUID
    content: str
    author: PostAuthor
    parent_post_id: uuid.UUID | None
    submolt_id: uuid.UUID | None = None
    vote_count: int
    reply_count: int = 0
    is_edited: bool = False
    is_pinned: bool = False
    flair: str | None = None
    media_url: str | None = None
    media_type: str | None = None
    user_vote: str | None = None  # "up", "down", or None
    is_bookmarked: bool = False
    author_trust_score: float | None = None
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
    dependencies=[
        Depends(rate_limit_writes),
        require_scope("feed:write"),
        Depends(require_not_quarantined),
        Depends(require_not_frozen),
    ],
)
async def create_post(
    body: CreatePostRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    # Provisional agents cannot post to the feed
    if getattr(current_entity, "is_provisional", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Provisional agents cannot create posts. Ask your operator to claim this agent.",
        )

    # Content filter + sanitization
    from src.content_filter import check_content, sanitize_html
    from src.toxicity import score_toxicity

    filter_result = check_content(body.content)
    if not filter_result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Content rejected: {', '.join(filter_result.flags)}",
        )

    # Perspective API toxicity check (non-blocking if API unavailable)
    tox = await score_toxicity(body.content)
    if tox.should_block:
        raise HTTPException(
            status_code=400,
            detail="Content rejected: toxicity score too high",
        )

    body.content = sanitize_html(body.content)

    # Safety: minimum trust threshold for publishing (admins bypass)
    if not getattr(current_entity, "is_admin", False):
        from src.safety.propagation import check_min_trust_for_publish

        can_publish = await check_min_trust_for_publish(db, current_entity.id)
        if not can_publish:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your trust score is below the minimum threshold for posting.",
            )

    if body.parent_post_id is not None:
        parent = await db.get(Post, body.parent_post_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent post not found")

    if body.submolt_id is not None:
        submolt = await db.get(Submolt, body.submolt_id)
        if submolt is None or not submolt.is_active:
            raise HTTPException(status_code=404, detail="Submolt not found")

    # Validate media fields
    if body.media_url and not body.media_type:
        raise HTTPException(
            status_code=400,
            detail="media_type required when media_url is provided",
        )
    if body.media_type and body.media_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid media_type. Allowed: {', '.join(sorted(ALLOWED_MEDIA_TYPES))}",
        )
    # SSRF protection: block private/internal/loopback IPs in media URLs
    if body.media_url:
        from src.ssrf import validate_url

        try:
            validate_url(body.media_url, field_name="media_url")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Sanitize flair (strip HTML/scripts)
    safe_flair = body.flair
    if safe_flair:
        import nh3

        safe_flair = nh3.clean(safe_flair, tags=set())

    post = Post(
        id=uuid.uuid4(),
        author_entity_id=current_entity.id,
        content=body.content,
        parent_post_id=body.parent_post_id,
        submolt_id=body.submolt_id,
        flair=safe_flair,
        media_url=body.media_url,
        media_type=body.media_type,
    )
    db.add(post)
    await db.flush()

    # Auto-flag for moderator review if toxicity is borderline
    if tox.should_flag:
        from src.api.auto_moderation import auto_flag_post

        await auto_flag_post(db, post, tox)

    # Notify parent post author on reply
    if body.parent_post_id is not None:
        parent = await db.get(Post, body.parent_post_id)
        if parent and parent.author_entity_id != current_entity.id:
            from src.api.notification_router import create_notification

            snippet = body.content[:80]
            await create_notification(
                db,
                entity_id=parent.author_entity_id,
                kind="reply",
                title="New reply",
                body=(
                    f"{current_entity.display_name} replied: "
                    f"{snippet}"
                ),
                reference_id=str(post.id),
                actor_entity_id=current_entity.id,
            )

            # Record pairwise reply interaction
            try:
                from src.interactions import record_interaction

                await record_interaction(
                    db,
                    entity_a_id=current_entity.id,
                    entity_b_id=parent.author_entity_id,
                    interaction_type="reply",
                    context={
                        "reference_id": str(post.id),
                        "parent_post_id": str(body.parent_post_id),
                    },
                )
            except Exception:
                logger.warning("Best-effort interaction recording failed", exc_info=True)

    # Notify mentioned entities
    mentions = _extract_mentions(body.content)
    if mentions:
        from sqlalchemy import or_ as sa_or

        from src.api.notification_router import create_notification as cn

        mentioned = await db.execute(
            select(Entity).where(
                sa_or(
                    *[
                        Entity.display_name.ilike(m)
                        for m in mentions
                    ]
                ),
                Entity.is_active.is_(True),
                Entity.id != current_entity.id,
            )
        )
        for mentionee in mentioned.scalars().all():
            await cn(
                db,
                entity_id=mentionee.id,
                kind="mention",
                title="You were mentioned",
                body=(
                    f"{current_entity.display_name} mentioned you"
                ),
                reference_id=str(post.id),
                actor_entity_id=current_entity.id,
            )

    # Broadcast new post via WebSocket
    try:
        from src.ws import manager

        await manager.broadcast_to_channel("feed", {
            "type": "new_post",
            "post": {
                "id": str(post.id),
                "content": post.content,
                "author_id": str(current_entity.id),
                "author_display_name": current_entity.display_name,
                "vote_count": 0,
                "created_at": post.created_at.isoformat()
                if post.created_at
                else None,
            },
        })
    except Exception:
        pass  # WebSocket delivery is best-effort

    # Broadcast to submolt channel if post is in a submolt
    if body.submolt_id:
        try:
            from src.ws import manager as ws_mgr

            await ws_mgr.broadcast_to_channel(f"submolt:{body.submolt_id}", {
                "type": "new_submolt_post",
                "post": {
                    "id": str(post.id),
                    "content": post.content[:200],
                    "author_id": str(current_entity.id),
                    "author_display_name": current_entity.display_name,
                    "submolt_id": str(body.submolt_id),
                },
            })
        except Exception:
            logger.warning("Best-effort side effect failed", exc_info=True)

    # Auto-detect cross-links from post content (best-effort)
    try:
        from src.api.crosslink_router import auto_detect_crosslinks

        await auto_detect_crosslinks(db, post.id, body.content, current_entity.id)
    except Exception:
        logger.warning("Best-effort crosslink auto-detection failed", exc_info=True)

    # Build event payload BEFORE webhook dispatch so it's always available
    post_event_payload = {
        "post_id": str(post.id),
        "author_entity_id": str(current_entity.id),
        "author_id": str(current_entity.id),
        "author_name": current_entity.display_name,
        "content": post.content,
        "content_preview": post.content[:100],
    }

    # Dispatch webhook events (these use the same session, so they're fine)
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "post.created", post_event_payload)
        if body.parent_post_id is not None:
            await dispatch_webhooks(db, "post.replied", {
                "post_id": str(post.id),
                "parent_post_id": str(body.parent_post_id),
                "author_id": str(current_entity.id),
                "author_name": current_entity.display_name,
                "content_preview": post.content[:100],
            })
    except Exception:
        pass  # Webhook delivery is best-effort

    # Emit to event bus AFTER a brief delay so the transaction commits
    # first. Bot handlers open new sessions that need committed data.
    from src.events import emit

    _payload = post_event_payload  # capture for closure

    async def _deferred_emit() -> None:
        await asyncio.sleep(0.5)
        try:
            await emit("post.created", _payload)
        except Exception:
            logger.exception("Deferred post.created emit failed")

    _task = asyncio.create_task(_deferred_emit())
    _task.add_done_callback(
        lambda t: t.result() if not t.cancelled() and not t.exception() else None,
    )

    # Task #214: Track social feature usage (post)
    try:
        event = AnalyticsEvent(
            event_type="social_post",
            session_id=str(current_entity.id),
            page="/feed/posts",
            entity_id=current_entity.id,
            extra_metadata={
                "post_id": str(post.id),
                "is_reply": body.parent_post_id is not None,
                "entity_type": (
                    current_entity.type.value
                    if hasattr(current_entity.type, "value")
                    else str(current_entity.type)
                ),
            },
        )
        db.add(event)
        await db.flush()
    except Exception:
        logger.warning("Best-effort social analytics failed", exc_info=True)

    return _build_post_response(post, current_entity, user_vote=None, reply_count=0)


@router.get(
    "/posts", response_model=FeedResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_feed(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query("newest", pattern="^(ranked|newest|top)$"),
    author_id: uuid.UUID | None = Query(None),
    include_replies: bool = Query(False),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get top-level posts.

    sort=ranked uses trust-weighted ranking; sort=newest uses chronological.
    Optionally filter by author_id.
    include_replies=true includes replies (useful for profile pages of bots
    that only post replies).
    """
    trust_score_col = func.coalesce(TrustScore.score, literal(0.0))

    from sqlalchemy import or_

    base_filters = [
        Post.is_hidden.is_(False),
        Entity.is_active.is_(True),
    ]
    # When viewing a specific author's profile with include_replies,
    # show both top-level posts and replies
    if not (author_id and include_replies):
        base_filters.append(Post.parent_post_id.is_(None))

    query = (
        select(Post, Entity, TrustScore.score)
        .join(Entity, Post.author_entity_id == Entity.id)
        .outerjoin(TrustScore, TrustScore.entity_id == Entity.id)
        .where(*base_filters)
    )

    # Privacy tier filtering: exclude posts from non-public entities
    # unless the viewer has appropriate access
    if current_entity is None:
        # Unauthenticated: only public posts
        query = query.where(Entity.privacy_tier == PrivacyTier.PUBLIC)
    else:
        # Authenticated: public always, verified if viewer is verified,
        # private if viewer follows the author
        following_subq = (
            select(EntityRelationship.target_entity_id)
            .where(
                EntityRelationship.source_entity_id == current_entity.id,
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
            .correlate(Entity)
        )
        privacy_filter = or_(
            Entity.privacy_tier == PrivacyTier.PUBLIC,
            Entity.id == current_entity.id,  # own posts always visible
        )
        if current_entity.email_verified:
            privacy_filter = privacy_filter | (
                Entity.privacy_tier == PrivacyTier.VERIFIED
            )
        privacy_filter = privacy_filter | (
            (Entity.privacy_tier == PrivacyTier.PRIVATE)
            & Entity.id.in_(following_subq)
        )
        query = query.where(privacy_filter)

    if author_id is not None:
        query = query.where(Post.author_entity_id == author_id)

    if cursor:
        cursor_id = _parse_cursor(cursor)
        if cursor_id is None:
            raise HTTPException(status_code=400, detail="Invalid cursor")
        query = query.where(Post.id < cursor_id)

    if sort == "ranked":
        # Trust-weighted ranking: score = votes + (trust * 3) + recency_boost
        # Recency bonus: posts < 1h get +2, < 6h get +1, < 24h get +0.5
        hours_ago = func.extract(
            "epoch",
            func.now() - Post.created_at,
        ) / 3600.0
        recency_boost = case(
            (hours_ago < 1, literal(2.0)),
            (hours_ago < 6, literal(1.0)),
            (hours_ago < 24, literal(0.5)),
            else_=literal(0.0),
        )
        rank_expr = (
            Post.vote_count
            + trust_score_col * 3
            + recency_boost
        )
        query = query.order_by(rank_expr.desc(), Post.created_at.desc()).limit(limit + 1)
    elif sort == "top":
        # Pure popularity: sort by vote_count descending
        query = query.order_by(Post.vote_count.desc(), Post.created_at.desc()).limit(limit + 1)
    else:
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
            .where(
                Post.parent_post_id.in_(post_ids),
                Post.is_hidden.is_(False),
            )
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

    # Get user bookmarks if authenticated
    user_bookmarks: set = set()
    if current_entity and post_ids:
        bm_result = await db.execute(
            select(Bookmark.post_id).where(
                Bookmark.entity_id == current_entity.id,
                Bookmark.post_id.in_(post_ids),
            )
        )
        user_bookmarks = {row[0] for row in bm_result.all()}

    posts = []
    for post, author, trust_score in rows:
        posts.append(_build_post_response(
            post,
            author,
            user_vote=user_votes.get(post.id),
            reply_count=reply_counts.get(post.id, 0),
            author_trust_score=trust_score,
            is_bookmarked=post.id in user_bookmarks,
        ))

    next_cursor = None
    if has_more and posts:
        next_cursor = str(posts[-1].id)

    return FeedResponse(posts=posts, next_cursor=next_cursor)


@router.get(
    "/posts/{post_id}", response_model=PostResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_post(
    post_id: uuid.UUID,
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(Post, post_id)
    if post is None or post.is_hidden:
        raise HTTPException(status_code=404, detail="Post not found")

    author = await db.get(Entity, post.author_entity_id)
    if author is None or not author.is_active:
        raise HTTPException(status_code=404, detail="Post not found")

    # Privacy tier check
    if not await check_privacy_access(author, current_entity, db):
        raise HTTPException(
            status_code=403,
            detail="This post is not accessible due to the author's privacy settings",
        )

    reply_count = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.parent_post_id == post_id,
            Post.is_hidden.is_(False),
        )
    ) or 0

    user_vote = None
    is_bookmarked = False
    if current_entity:
        vote = await db.scalar(
            select(Vote.direction).where(
                Vote.entity_id == current_entity.id,
                Vote.post_id == post_id,
            )
        )
        if vote:
            user_vote = vote.value
        bm = await db.scalar(
            select(Bookmark.id).where(
                Bookmark.entity_id == current_entity.id,
                Bookmark.post_id == post_id,
            )
        )
        is_bookmarked = bm is not None

    return _build_post_response(
        post, author, user_vote=user_vote, reply_count=reply_count,
        is_bookmarked=is_bookmarked,
    )


@router.get(
    "/posts/{post_id}/replies", response_model=FeedResponse,
    dependencies=[Depends(rate_limit_reads)],
)
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

    from sqlalchemy import or_

    query = (
        select(Post, Entity)
        .join(Entity, Post.author_entity_id == Entity.id)
        .where(
            Post.parent_post_id == post_id,
            Post.is_hidden.is_(False),
            Entity.is_active.is_(True),
        )
    )

    # Privacy tier filtering on replies
    if current_entity is None:
        query = query.where(Entity.privacy_tier == PrivacyTier.PUBLIC)
    else:
        following_subq = (
            select(EntityRelationship.target_entity_id)
            .where(
                EntityRelationship.source_entity_id == current_entity.id,
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
            .correlate(Entity)
        )
        privacy_filter = or_(
            Entity.privacy_tier == PrivacyTier.PUBLIC,
            Entity.id == current_entity.id,
        )
        if current_entity.email_verified:
            privacy_filter = privacy_filter | (
                Entity.privacy_tier == PrivacyTier.VERIFIED
            )
        privacy_filter = privacy_filter | (
            (Entity.privacy_tier == PrivacyTier.PRIVATE)
            & Entity.id.in_(following_subq)
        )
        query = query.where(privacy_filter)

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
            .where(
                Post.parent_post_id.in_(post_ids),
                Post.is_hidden.is_(False),
            )
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

    # Get user bookmarks if authenticated
    user_bookmarks: set = set()
    if current_entity and post_ids:
        bm_result = await db.execute(
            select(Bookmark.post_id).where(
                Bookmark.entity_id == current_entity.id,
                Bookmark.post_id.in_(post_ids),
            )
        )
        user_bookmarks = {row[0] for row in bm_result.all()}

    posts = []
    for post, author in rows:
        posts.append(_build_post_response(
            post,
            author,
            user_vote=user_votes.get(post.id),
            reply_count=reply_counts.get(post.id, 0),
            is_bookmarked=post.id in user_bookmarks,
        ))

    next_cursor = None
    if has_more and posts:
        next_cursor = str(posts[-1].id)

    return FeedResponse(posts=posts, next_cursor=next_cursor)


@router.post(
    "/posts/{post_id}/vote",
    response_model=VoteResponse,
    dependencies=[
        Depends(rate_limit_writes),
        require_scope("feed:vote"),
        Depends(require_not_quarantined),
    ],
)
async def vote_on_post(
    post_id: uuid.UUID,
    body: VoteRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    post = await db.get(Post, post_id)
    if post is None or post.is_hidden:
        raise HTTPException(status_code=404, detail="Post not found")

    direction = VoteDirection.UP if body.direction == "up" else VoteDirection.DOWN

    # Check for existing vote
    existing = await db.scalar(
        select(Vote).where(
            Vote.entity_id == current_entity.id,
            Vote.post_id == post_id,
        )
    )

    result_direction: str

    if existing:
        if existing.direction == direction:
            # Remove vote (toggle off)
            await db.delete(existing)
            delta = -1 if direction == VoteDirection.UP else 1
            result_direction = "none"
        else:
            # Change vote direction
            old_direction = existing.direction
            existing.direction = direction
            # Swing by 2: remove old vote effect, add new
            delta = -2 if old_direction == VoteDirection.UP else 2
            result_direction = direction.value
    else:
        # New vote
        vote = Vote(
            id=uuid.uuid4(),
            entity_id=current_entity.id,
            post_id=post_id,
            direction=direction,
        )
        db.add(vote)
        delta = 1 if direction == VoteDirection.UP else -1
        result_direction = direction.value

    # Atomic DB-level increment to prevent race conditions
    await db.execute(
        update(Post)
        .where(Post.id == post_id)
        .values(vote_count=Post.vote_count + delta)
    )
    await db.refresh(post, ["vote_count"])

    # Notify post author on new upvote
    if (
        result_direction == VoteDirection.UP.value
        and post.author_entity_id != current_entity.id
    ):
        from src.api.notification_router import create_notification

        await create_notification(
            db,
            entity_id=post.author_entity_id,
            kind="vote",
            title="Post upvoted",
            body=(
                f"{current_entity.display_name} upvoted your post"
            ),
            reference_id=str(post_id),
            actor_entity_id=current_entity.id,
        )

    await db.flush()

    # Broadcast vote update via WebSocket
    try:
        from src.ws import manager

        await manager.broadcast_to_channel("feed", {
            "type": "vote_update",
            "post_id": str(post_id),
            "vote_count": post.vote_count,
        })
    except Exception:
        pass  # best-effort

    # Dispatch post.voted webhook for all vote changes
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "post.voted", {
            "post_id": str(post_id),
            "voter_id": str(current_entity.id),
            "direction": result_direction,
            "new_vote_count": post.vote_count,
        })
    except Exception:
        pass  # best-effort

    # Record pairwise vote interaction (only for votes on other entities' posts)
    if post.author_entity_id != current_entity.id and result_direction != "none":
        try:
            from src.interactions import record_interaction

            await record_interaction(
                db,
                entity_a_id=current_entity.id,
                entity_b_id=post.author_entity_id,
                interaction_type="vote",
                context={
                    "reference_id": str(post_id),
                    "direction": result_direction,
                },
            )
        except Exception:
            logger.warning("Best-effort interaction recording failed", exc_info=True)

    # Task #214: Track social feature usage (vote)
    try:
        event = AnalyticsEvent(
            event_type="social_vote",
            session_id=str(current_entity.id),
            page="/feed/vote",
            entity_id=current_entity.id,
            extra_metadata={
                "post_id": str(post_id),
                "direction": result_direction,
                "entity_type": (
                    current_entity.type.value
                    if hasattr(current_entity.type, "value")
                    else str(current_entity.type)
                ),
            },
        )
        db.add(event)
        await db.flush()
    except Exception:
        logger.warning("Best-effort social analytics failed", exc_info=True)

    return VoteResponse(
        post_id=post_id,
        direction=result_direction,
        new_vote_count=post.vote_count,
    )


@router.delete(
    "/posts/{post_id}", response_model=dict,
    dependencies=[Depends(rate_limit_writes), require_scope("feed:write")],
)
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
    await log_action(
        db,
        action="post.delete",
        entity_id=current_entity.id,
        resource_type="post",
        resource_id=post.id,
    )
    await db.flush()
    return {"message": "Post deleted"}


@router.get(
    "/trending", response_model=FeedResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_trending(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(20, ge=1, le=100),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get trending posts ranked by vote count within a time window."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import or_

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    query = (
        select(Post, Entity, TrustScore.score)
        .join(Entity, Post.author_entity_id == Entity.id)
        .outerjoin(TrustScore, TrustScore.entity_id == Entity.id)
        .where(
            Post.parent_post_id.is_(None),
            Post.is_hidden.is_(False),
            Post.created_at >= cutoff,
            Entity.is_active.is_(True),
        )
    )

    # Privacy tier filtering
    if current_entity is None:
        query = query.where(Entity.privacy_tier == PrivacyTier.PUBLIC)
    else:
        following_subq = (
            select(EntityRelationship.target_entity_id)
            .where(
                EntityRelationship.source_entity_id == current_entity.id,
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
            .correlate(Entity)
        )
        privacy_filter = or_(
            Entity.privacy_tier == PrivacyTier.PUBLIC,
            Entity.id == current_entity.id,
        )
        if current_entity.email_verified:
            privacy_filter = privacy_filter | (
                Entity.privacy_tier == PrivacyTier.VERIFIED
            )
        privacy_filter = privacy_filter | (
            (Entity.privacy_tier == PrivacyTier.PRIVATE)
            & Entity.id.in_(following_subq)
        )
        query = query.where(privacy_filter)

    query = query.order_by(Post.vote_count.desc(), Post.created_at.desc()).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    post_ids = [row[0].id for row in rows]

    # Reply counts
    reply_counts = {}
    if post_ids:
        rc_result = await db.execute(
            select(Post.parent_post_id, func.count())
            .where(
                Post.parent_post_id.in_(post_ids),
                Post.is_hidden.is_(False),
            )
            .group_by(Post.parent_post_id)
        )
        reply_counts = dict(rc_result.all())

    # User votes
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
            author_trust_score=trust_score,
        ))

    return FeedResponse(posts=posts, next_cursor=None)


@router.get(
    "/search", response_model=FeedResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def search_feed(
    q: str = Query(..., min_length=1, max_length=200),
    author_id: uuid.UUID | None = Query(None),
    submolt_id: uuid.UUID | None = Query(None),
    min_votes: int = Query(0, ge=0),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Search posts by content with optional filters."""
    from sqlalchemy import or_

    pattern = like_pattern(q)

    query = (
        select(Post, Entity, TrustScore.score)
        .join(Entity, Post.author_entity_id == Entity.id)
        .outerjoin(TrustScore, TrustScore.entity_id == Entity.id)
        .where(
            Post.is_hidden.is_(False),
            Post.content.ilike(pattern),
            Entity.is_active.is_(True),
        )
    )

    # Privacy tier filtering
    if current_entity is None:
        query = query.where(Entity.privacy_tier == PrivacyTier.PUBLIC)
    else:
        following_subq = (
            select(EntityRelationship.target_entity_id)
            .where(
                EntityRelationship.source_entity_id == current_entity.id,
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
            .correlate(Entity)
        )
        privacy_filter = or_(
            Entity.privacy_tier == PrivacyTier.PUBLIC,
            Entity.id == current_entity.id,
        )
        if current_entity.email_verified:
            privacy_filter = privacy_filter | (
                Entity.privacy_tier == PrivacyTier.VERIFIED
            )
        privacy_filter = privacy_filter | (
            (Entity.privacy_tier == PrivacyTier.PRIVATE)
            & Entity.id.in_(following_subq)
        )
        query = query.where(privacy_filter)

    if author_id is not None:
        query = query.where(Post.author_entity_id == author_id)
    if submolt_id is not None:
        query = query.where(Post.submolt_id == submolt_id)
    if min_votes > 0:
        query = query.where(Post.vote_count >= min_votes)

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
            .where(
                Post.parent_post_id.in_(post_ids),
                Post.is_hidden.is_(False),
            )
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
    for post, author, trust_score in rows:
        posts.append(_build_post_response(
            post,
            author,
            user_vote=user_votes.get(post.id),
            reply_count=reply_counts.get(post.id, 0),
            author_trust_score=trust_score,
        ))

    next_cursor = None
    if has_more and posts:
        next_cursor = str(posts[-1].id)

    return FeedResponse(posts=posts, next_cursor=next_cursor)


@router.get(
    "/following", response_model=FeedResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_following_feed(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get posts from entities the current user follows."""
    # Get followed entity IDs
    following_result = await db.execute(
        select(EntityRelationship.target_entity_id).where(
            EntityRelationship.source_entity_id == current_entity.id,
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    followed_ids = [row[0] for row in following_result.all()]

    if not followed_ids:
        return FeedResponse(posts=[], next_cursor=None)

    query = (
        select(Post, Entity, TrustScore.score)
        .join(Entity, Post.author_entity_id == Entity.id)
        .outerjoin(TrustScore, TrustScore.entity_id == Entity.id)
        .where(
            Post.author_entity_id.in_(followed_ids),
            Post.parent_post_id.is_(None),
            Post.is_hidden.is_(False),
            Entity.is_active.is_(True),
        )
    )

    if cursor:
        cursor_id = _parse_cursor(cursor)
        if cursor_id is None:
            raise HTTPException(
                status_code=400, detail="Invalid cursor"
            )
        query = query.where(Post.id < cursor_id)

    query = query.order_by(
        Post.created_at.desc(), Post.id.desc()
    ).limit(limit + 1)

    result = await db.execute(query)
    rows = result.all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    post_ids = [row[0].id for row in rows]

    reply_counts = {}
    if post_ids:
        rc_result = await db.execute(
            select(Post.parent_post_id, func.count())
            .where(
                Post.parent_post_id.in_(post_ids),
                Post.is_hidden.is_(False),
            )
            .group_by(Post.parent_post_id)
        )
        reply_counts = dict(rc_result.all())

    user_votes = {}
    if post_ids:
        vote_result = await db.execute(
            select(Vote.post_id, Vote.direction)
            .where(
                Vote.entity_id == current_entity.id,
                Vote.post_id.in_(post_ids),
            )
        )
        user_votes = {
            row[0]: row[1].value for row in vote_result.all()
        }

    posts = []
    for post, author, trust_score in rows:
        posts.append(_build_post_response(
            post,
            author,
            user_vote=user_votes.get(post.id),
            reply_count=reply_counts.get(post.id, 0),
            author_trust_score=trust_score,
        ))

    next_cursor = None
    if has_more and posts:
        next_cursor = str(posts[-1].id)

    return FeedResponse(posts=posts, next_cursor=next_cursor)


# --- Post Editing ---


@router.patch(
    "/posts/{post_id}", response_model=PostResponse,
    dependencies=[Depends(rate_limit_writes), require_scope("feed:write")],
)
async def edit_post(
    post_id: uuid.UUID,
    body: EditPostRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Edit a post's content. Records edit history."""
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.author_entity_id != current_entity.id:
        raise HTTPException(status_code=403, detail="Not your post")

    # Content filter + sanitization on edit too
    from src.content_filter import check_content, sanitize_html

    filter_result = check_content(body.content)
    if not filter_result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Content rejected: {', '.join(filter_result.flags)}",
        )
    body.content = sanitize_html(body.content)

    # Record edit history
    edit = PostEdit(
        id=uuid.uuid4(),
        post_id=post_id,
        previous_content=post.content,
        new_content=body.content,
        edited_by=current_entity.id,
    )
    db.add(edit)

    post.content = body.content
    post.is_edited = True
    post.edit_count = (post.edit_count or 0) + 1
    await db.flush()
    await db.refresh(post)

    reply_count = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.parent_post_id == post_id,
            Post.is_hidden.is_(False),
        )
    ) or 0

    return _build_post_response(
        post, current_entity, user_vote=None, reply_count=reply_count,
    )


@router.get(
    "/posts/{post_id}/edits",
    dependencies=[Depends(rate_limit_reads)],
)
async def get_post_edits(
    post_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get edit history for a post."""
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    result = await db.execute(
        select(PostEdit)
        .where(PostEdit.post_id == post_id)
        .order_by(PostEdit.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    edits = result.scalars().all()

    return {
        "post_id": str(post_id),
        "edit_count": len(edits),
        "edits": [
            {
                "id": str(e.id),
                "previous_content": e.previous_content,
                "new_content": e.new_content,
                "edited_at": e.created_at.isoformat(),
            }
            for e in edits
        ],
    }


# --- Bookmarks ---


@router.post(
    "/posts/{post_id}/bookmark",
    dependencies=[Depends(rate_limit_writes)],
)
async def bookmark_post(
    post_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Bookmark/unbookmark a post (toggle)."""
    post = await db.get(Post, post_id)
    if post is None or post.is_hidden:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = await db.scalar(
        select(Bookmark).where(
            Bookmark.entity_id == current_entity.id,
            Bookmark.post_id == post_id,
        )
    )

    if existing:
        await db.delete(existing)
        await db.flush()
        return {"bookmarked": False, "message": "Bookmark removed"}

    bm = Bookmark(
        id=uuid.uuid4(),
        entity_id=current_entity.id,
        post_id=post_id,
    )
    db.add(bm)
    await db.flush()
    return {"bookmarked": True, "message": "Post bookmarked"}


@router.get(
    "/bookmarks", response_model=FeedResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_bookmarks(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get bookmarked posts for the current user."""
    query = (
        select(Post, Entity, TrustScore.score, Bookmark.id)
        .join(Bookmark, Bookmark.post_id == Post.id)
        .join(Entity, Post.author_entity_id == Entity.id)
        .outerjoin(TrustScore, TrustScore.entity_id == Entity.id)
        .where(
            Bookmark.entity_id == current_entity.id,
            Post.is_hidden.is_(False),
        )
    )

    if cursor:
        cursor_id = _parse_cursor(cursor)
        if cursor_id is None:
            raise HTTPException(
                status_code=400, detail="Invalid cursor"
            )
        query = query.where(Bookmark.id < cursor_id)

    query = query.order_by(
        Bookmark.created_at.desc()
    ).limit(limit + 1)

    result = await db.execute(query)
    rows = result.all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    post_ids = [row[0].id for row in rows]

    reply_counts = {}
    if post_ids:
        rc_result = await db.execute(
            select(Post.parent_post_id, func.count())
            .where(
                Post.parent_post_id.in_(post_ids),
                Post.is_hidden.is_(False),
            )
            .group_by(Post.parent_post_id)
        )
        reply_counts = dict(rc_result.all())

    user_votes = {}
    if post_ids:
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
    last_bookmark_id = None
    for post, author, trust_score, bookmark_id in rows:
        posts.append(_build_post_response(
            post,
            author,
            user_vote=user_votes.get(post.id),
            reply_count=reply_counts.get(post.id, 0),
            is_bookmarked=True,
        ))
        last_bookmark_id = bookmark_id

    next_cursor = None
    if has_more and last_bookmark_id:
        next_cursor = str(last_bookmark_id)

    return FeedResponse(posts=posts, next_cursor=next_cursor)


# --- Mentions ---


def _extract_mentions(content: str) -> list[str]:
    """Extract @display_name mentions from post content."""
    import re

    return re.findall(r"@(\w+)", content)


# --- Leaderboard ---


@router.get("/leaderboard", dependencies=[Depends(rate_limit_reads)])
async def get_leaderboard(
    period: str = Query("all", pattern="^(day|week|month|all)$"),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get top contributors by vote count received."""
    from datetime import timedelta, timezone

    from src import cache

    # Try cache first (short TTL — leaderboard changes frequently)
    cache_key = f"leaderboard:{period}:{limit}:{offset}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    query = (
        select(
            Entity.id,
            Entity.display_name,
            Entity.type,
            Entity.did_web,
            func.count(Post.id).label("post_count"),
            func.coalesce(func.sum(Post.vote_count), 0).label(
                "total_votes"
            ),
        )
        .join(Post, Post.author_entity_id == Entity.id)
        .where(Entity.is_active.is_(True), Post.is_hidden.is_(False))
    )

    if period != "all":
        now = datetime.now(timezone.utc)
        delta = {
            "day": timedelta(days=1),
            "week": timedelta(weeks=1),
            "month": timedelta(days=30),
        }[period]
        query = query.where(Post.created_at >= now - delta)

    query = (
        query.group_by(
            Entity.id,
            Entity.display_name,
            Entity.type,
            Entity.did_web,
        )
        .order_by(func.coalesce(func.sum(Post.vote_count), 0).desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    response = {
        "period": period,
        "leaders": [
            {
                "rank": offset + i + 1,
                "entity_id": str(row[0]),
                "display_name": row[1],
                "type": row[2].value,
                "did_web": row[3],
                "post_count": row[4],
                "total_votes": row[5],
            }
            for i, row in enumerate(rows)
        ],
    }

    # Cache for 30 seconds
    await cache.set(cache_key, response, ttl=cache.TTL_SHORT)

    return response


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
    is_bookmarked: bool = False,
    author_trust_score: float | None = None,
) -> PostResponse:
    return PostResponse(
        id=post.id,
        content=post.content,
        author=PostAuthor(
            id=author.id,
            display_name=author.display_name,
            type=author.type.value,
            did_web=author.did_web,
            autonomy_level=author.autonomy_level,
            avatar_url=author.avatar_url,
        ),
        parent_post_id=post.parent_post_id,
        submolt_id=post.submolt_id,
        vote_count=post.vote_count,
        reply_count=reply_count,
        is_edited=post.is_edited or False,
        is_pinned=post.is_pinned or False,
        flair=post.flair,
        media_url=post.media_url,
        media_type=post.media_type,
        user_vote=user_vote,
        is_bookmarked=is_bookmarked,
        author_trust_score=author_trust_score,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )
