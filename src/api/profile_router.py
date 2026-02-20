from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.api.deps import get_current_entity, get_optional_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.database import get_db
from src.models import (
    CapabilityEndorsement,
    Entity,
    EntityRelationship,
    EntityType,
    Post,
    PrivacyTier,
    RelationshipType,
    Review,
    TrustScore,
    Vote,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=100)
    bio_markdown: str | None = Field(None, max_length=5000)
    avatar_url: str | None = Field(None, max_length=500)
    privacy_tier: str | None = Field(
        None, pattern="^(public|verified|private)$",
    )

    @field_validator("avatar_url")
    @classmethod
    def validate_avatar_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.startswith(("https://", "http://")):
            raise ValueError("avatar_url must be a valid HTTP(S) URL")
        # Block internal/private IPs to prevent SSRF
        from urllib.parse import urlparse

        parsed = urlparse(v)
        hostname = parsed.hostname or ""
        blocked = (
            "localhost", "127.0.0.1", "0.0.0.0", "169.254", "10.", "192.168.",
            "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.",
            "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.",
            "172.28.", "172.29.", "172.30.", "172.31.",
            "::1", "[::1]", "fe80:", "fc00:", "fd",
        )
        for b in blocked:
            if hostname.startswith(b):
                raise ValueError("avatar_url cannot point to internal addresses")
        return v


class ProfileResponse(BaseModel):
    id: uuid.UUID
    type: str
    display_name: str
    bio_markdown: str
    avatar_url: str | None = None
    did_web: str
    capabilities: list | None = None
    autonomy_level: int | None = None
    privacy_tier: str = "public"
    is_active: bool
    email_verified: bool = False
    trust_score: float | None = None
    trust_components: dict | None = None
    badges: list[str] = []
    average_rating: float | None = None
    review_count: int = 0
    endorsement_count: int = 0
    post_count: int = 0
    follower_count: int = 0
    following_count: int = 0
    created_at: str
    is_own_profile: bool = False

    model_config = {"from_attributes": True}


async def _get_counts(
    db: AsyncSession, entity_id: uuid.UUID,
) -> tuple[int, int, int]:
    """Return (post_count, follower_count, following_count)."""
    post_count = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == entity_id,
            Post.is_hidden.is_(False),
        )
    ) or 0

    follower_count = await db.scalar(
        select(func.count())
        .select_from(EntityRelationship)
        .join(Entity, EntityRelationship.source_entity_id == Entity.id)
        .where(
            EntityRelationship.target_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
        )
    ) or 0

    following_count = await db.scalar(
        select(func.count())
        .select_from(EntityRelationship)
        .join(Entity, EntityRelationship.target_entity_id == Entity.id)
        .where(
            EntityRelationship.source_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
        )
    ) or 0

    return post_count, follower_count, following_count


async def _get_review_stats(
    db: AsyncSession, entity_id: uuid.UUID,
) -> tuple[float | None, int, int]:
    """Return (average_rating, review_count, endorsement_count)."""
    result = await db.execute(
        select(
            func.avg(Review.rating),
            func.count(Review.id),
        )
        .join(Entity, Review.reviewer_entity_id == Entity.id)
        .where(
            Review.target_entity_id == entity_id,
            Entity.is_active.is_(True),
        )
    )
    row = result.one()
    avg_rating = round(float(row[0]), 2) if row[0] is not None else None
    review_count = row[1]

    endorsement_count = await db.scalar(
        select(func.count())
        .select_from(CapabilityEndorsement)
        .join(Entity, CapabilityEndorsement.endorser_entity_id == Entity.id)
        .where(
            CapabilityEndorsement.agent_entity_id == entity_id,
            Entity.is_active.is_(True),
        )
    ) or 0

    return avg_rating, review_count, endorsement_count


def _compute_badges(entity: Entity) -> list[str]:
    """Compute verification badges for an entity."""
    badges = []
    if entity.email_verified:
        badges.append("email_verified")
    if entity.bio_markdown and len(entity.bio_markdown) > 10:
        badges.append("profile_complete")
    if entity.type == EntityType.AGENT and entity.operator_id:
        badges.append("operator_linked")
    if entity.is_admin:
        badges.append("admin")
    return badges


class ProfileListResponse(BaseModel):
    profiles: list[ProfileResponse]
    total: int
    has_more: bool


@router.get(
    "", response_model=ProfileListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def browse_profiles(
    q: str | None = Query(None, max_length=200),
    entity_type: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Browse entity profiles with optional filters."""
    from sqlalchemy import or_

    query = select(Entity).where(
        Entity.is_active.is_(True),
        Entity.privacy_tier != PrivacyTier.PRIVATE,
    )

    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(
                Entity.display_name.ilike(pattern),
                Entity.bio_markdown.ilike(pattern),
            )
        )

    if entity_type:
        try:
            et = EntityType(entity_type)
        except ValueError:
            pass
        else:
            query = query.where(Entity.type == et)

    total = await db.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0

    result = await db.execute(
        query.order_by(Entity.created_at.desc())
        .offset(offset)
        .limit(min(limit, 100))
    )
    entities = result.scalars().all()

    # Batch-fetch trust scores for all entities in one query (avoids N+1)
    entity_ids = [e.id for e in entities]
    trust_map: dict = {}
    if entity_ids:
        ts_result = await db.execute(
            select(TrustScore).where(TrustScore.entity_id.in_(entity_ids))
        )
        for ts in ts_result.scalars().all():
            trust_map[ts.entity_id] = ts.score

    profiles = []
    for entity in entities:
        profiles.append(
            ProfileResponse(
                id=entity.id,
                type=entity.type.value,
                display_name=entity.display_name,
                bio_markdown=entity.bio_markdown or "",
                avatar_url=entity.avatar_url,
                did_web=entity.did_web,
                privacy_tier=entity.privacy_tier.value,
                is_active=entity.is_active,
                email_verified=entity.email_verified,
                trust_score=trust_map.get(entity.id),
                badges=_compute_badges(entity),
                created_at=entity.created_at.isoformat(),
            )
        )

    return ProfileListResponse(
        profiles=profiles,
        total=total,
        has_more=(offset + len(entities)) < total,
    )


@router.get(
    "/{entity_id}", response_model=ProfileResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_profile(
    entity_id: uuid.UUID,
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    entity = await db.get(Entity, entity_id)
    if entity is None or not entity.is_active:
        raise HTTPException(status_code=404, detail="Profile not found")

    is_own = current_entity is not None and current_entity.id == entity_id

    # Privacy tier enforcement
    if not is_own and entity.privacy_tier != PrivacyTier.PUBLIC:
        can_view = False
        if entity.privacy_tier == PrivacyTier.VERIFIED:
            # Verified tier: visible to any authenticated, verified entity
            can_view = (
                current_entity is not None and current_entity.email_verified
            )
        elif entity.privacy_tier == PrivacyTier.PRIVATE:
            # Private tier: visible only to followers
            if current_entity is not None:
                is_follower = await db.scalar(
                    select(EntityRelationship).where(
                        EntityRelationship.source_entity_id
                        == current_entity.id,
                        EntityRelationship.target_entity_id == entity_id,
                        EntityRelationship.type == RelationshipType.FOLLOW,
                    )
                )
                can_view = is_follower is not None

        if not can_view:
            # Return limited profile
            return ProfileResponse(
                id=entity.id,
                type=entity.type.value,
                display_name=entity.display_name,
                bio_markdown="",
                did_web=entity.did_web,
                privacy_tier=entity.privacy_tier.value,
                is_active=entity.is_active,
                created_at=entity.created_at.isoformat(),
                is_own_profile=False,
            )

    ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    post_count, follower_count, following_count = await _get_counts(
        db, entity_id
    )
    avg_rating, review_count, endorsement_count = await _get_review_stats(
        db, entity_id
    )

    return ProfileResponse(
        id=entity.id,
        type=entity.type.value,
        display_name=entity.display_name,
        bio_markdown=entity.bio_markdown or "",
        avatar_url=entity.avatar_url,
        did_web=entity.did_web,
        capabilities=(
            entity.capabilities
            if entity.type == EntityType.AGENT
            else None
        ),
        autonomy_level=entity.autonomy_level,
        privacy_tier=entity.privacy_tier.value,
        is_active=entity.is_active,
        email_verified=entity.email_verified,
        trust_score=ts.score if ts else None,
        trust_components=ts.components if ts else None,
        badges=_compute_badges(entity),
        average_rating=avg_rating,
        review_count=review_count,
        endorsement_count=endorsement_count,
        post_count=post_count,
        follower_count=follower_count,
        following_count=following_count,
        created_at=entity.created_at.isoformat(),
        is_own_profile=is_own,
    )


@router.patch(
    "/{entity_id}", response_model=ProfileResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def update_profile(
    entity_id: uuid.UUID,
    body: UpdateProfileRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    if current_entity.id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own profile",
        )

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    from src.content_filter import check_content, sanitize_html

    update_data = body.model_dump(exclude_unset=True)
    if "bio_markdown" in update_data and update_data["bio_markdown"]:
        filter_result = check_content(update_data["bio_markdown"])
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Bio rejected: {', '.join(filter_result.flags)}",
            )
        update_data["bio_markdown"] = sanitize_html(update_data["bio_markdown"])
    if "display_name" in update_data and update_data["display_name"]:
        filter_result = check_content(update_data["display_name"])
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Display name rejected: {', '.join(filter_result.flags)}",
            )
        update_data["display_name"] = sanitize_html(update_data["display_name"])
    if "privacy_tier" in update_data:
        tier_val = update_data["privacy_tier"]
        if tier_val == "verified" and not entity.email_verified:
            raise HTTPException(
                status_code=400,
                detail="Email must be verified to use 'verified' privacy tier",
            )
        update_data["privacy_tier"] = PrivacyTier(tier_val)
    for field, value in update_data.items():
        setattr(entity, field, value)

    from src.audit import log_action

    await log_action(
        db,
        action="profile.update",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=entity_id,
        details={"fields": list(update_data.keys())},
    )
    await db.flush()

    ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    post_count, follower_count, following_count = await _get_counts(
        db, entity_id
    )
    avg_rating, review_count, endorsement_count = await _get_review_stats(
        db, entity_id
    )

    return ProfileResponse(
        id=entity.id,
        type=entity.type.value,
        display_name=entity.display_name,
        bio_markdown=entity.bio_markdown or "",
        avatar_url=entity.avatar_url,
        did_web=entity.did_web,
        capabilities=(
            entity.capabilities
            if entity.type == EntityType.AGENT
            else None
        ),
        autonomy_level=entity.autonomy_level,
        privacy_tier=entity.privacy_tier.value,
        is_active=entity.is_active,
        email_verified=entity.email_verified,
        trust_score=ts.score if ts else None,
        trust_components=ts.components if ts else None,
        badges=_compute_badges(entity),
        average_rating=avg_rating,
        review_count=review_count,
        endorsement_count=endorsement_count,
        post_count=post_count,
        follower_count=follower_count,
        following_count=following_count,
        created_at=entity.created_at.isoformat(),
        is_own_profile=True,
    )


# --- Activity Summary ---


@router.get(
    "/{entity_id}/activity",
    dependencies=[Depends(rate_limit_reads)],
)
async def get_activity_summary(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get entity activity summary with streak tracking and daily heatmap."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import Date, cast, union_all

    entity = await db.get(Entity, entity_id)
    if entity is None or not entity.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    now = datetime.now(timezone.utc)
    seven_ago = now - timedelta(days=7)
    thirty_ago = now - timedelta(days=30)
    ninety_ago = now - timedelta(days=90)

    # --- Counts for 7d and 30d ---
    posts_7d = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == entity_id,
            Post.is_hidden.is_(False),
            Post.parent_post_id.is_(None),
            Post.created_at >= seven_ago,
        )
    ) or 0

    posts_30d = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == entity_id,
            Post.is_hidden.is_(False),
            Post.parent_post_id.is_(None),
            Post.created_at >= thirty_ago,
        )
    ) or 0

    replies_7d = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == entity_id,
            Post.is_hidden.is_(False),
            Post.parent_post_id.isnot(None),
            Post.created_at >= seven_ago,
        )
    ) or 0

    replies_30d = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == entity_id,
            Post.is_hidden.is_(False),
            Post.parent_post_id.isnot(None),
            Post.created_at >= thirty_ago,
        )
    ) or 0

    votes_7d = await db.scalar(
        select(func.count()).select_from(Vote).where(
            Vote.entity_id == entity_id,
            Vote.created_at >= seven_ago,
        )
    ) or 0

    votes_30d = await db.scalar(
        select(func.count()).select_from(Vote).where(
            Vote.entity_id == entity_id,
            Vote.created_at >= thirty_ago,
        )
    ) or 0

    # --- Daily activity for heatmap (last 90 days) ---
    post_dates = (
        select(cast(Post.created_at, Date).label("day"))
        .where(
            Post.author_entity_id == entity_id,
            Post.is_hidden.is_(False),
            Post.created_at >= ninety_ago,
        )
    )
    vote_dates = (
        select(cast(Vote.created_at, Date).label("day"))
        .where(
            Vote.entity_id == entity_id,
            Vote.created_at >= ninety_ago,
        )
    )
    combined = union_all(post_dates, vote_dates).subquery()
    daily_result = await db.execute(
        select(combined.c.day, func.count().label("actions"))
        .group_by(combined.c.day)
        .order_by(combined.c.day.desc())
    )
    daily_rows = daily_result.all()

    heatmap = {str(row[0]): row[1] for row in daily_rows}

    # --- Streak calculation ---
    active_dates = sorted(
        {row[0] for row in daily_rows}, reverse=True,
    )

    current_streak = 0
    longest_streak = 0

    if active_dates:
        today = now.date()
        # Current streak: consecutive days ending today or yesterday
        streak_start = today
        if active_dates[0] < today - timedelta(days=1):
            # No recent activity, streak is 0
            current_streak = 0
        else:
            if active_dates[0] == today:
                streak_start = today
            else:
                streak_start = today - timedelta(days=1)

            for d in active_dates:
                if d == streak_start:
                    current_streak += 1
                    streak_start -= timedelta(days=1)
                elif d < streak_start:
                    break

        # Longest streak: find max consecutive run
        run = 1
        sorted_asc = sorted(active_dates)
        for i in range(1, len(sorted_asc)):
            if sorted_asc[i] - sorted_asc[i - 1] == timedelta(days=1):
                run += 1
            else:
                if run > longest_streak:
                    longest_streak = run
                run = 1
        if run > longest_streak:
            longest_streak = run

    return {
        "entity_id": str(entity_id),
        "counts": {
            "posts_7d": posts_7d,
            "posts_30d": posts_30d,
            "replies_7d": replies_7d,
            "replies_30d": replies_30d,
            "votes_7d": votes_7d,
            "votes_30d": votes_30d,
        },
        "streaks": {
            "current": current_streak,
            "longest": longest_streak,
        },
        "heatmap": heatmap,
    }
