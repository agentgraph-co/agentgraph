from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src import cache
from src.api.deps import get_current_entity, get_optional_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.database import get_db
from src.models import (
    CapabilityEndorsement,
    Entity,
    EntityRelationship,
    EntityType,
    ModerationFlag,
    ModerationReason,
    Post,
    PrivacyTier,
    RelationshipType,
    Review,
    TrustScore,
    Vote,
)
from src.ssrf import validate_url_optional
from src.utils import like_pattern

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
        if v is not None and v.startswith("/avatars/"):
            return v  # Allow local avatar library paths
        if v is not None and v.startswith("https://api.dicebear.com/"):
            return v  # Allow DiceBear avatar URLs
        return validate_url_optional(v, field_name="avatar_url")


class ProfileResponse(BaseModel):
    id: uuid.UUID
    type: str
    display_name: str
    bio_markdown: str
    avatar_url: str | None = None
    did_web: str
    capabilities: list | None = None
    autonomy_level: int | None = None
    framework_source: str | None = None
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
    is_provisional: bool = False
    provisional_expires_at: str | None = None
    created_at: str
    operator_id: str | None = None
    operator_display_name: str | None = None
    is_own_profile: bool = False
    is_following: bool = False
    source_url: str | None = None
    source_type: str | None = None
    source_verified_at: str | None = None
    onboarding_data: dict | None = None

    model_config = {"from_attributes": True}


async def _get_profile_stats(
    db: AsyncSession, entity_id: uuid.UUID,
) -> dict:
    """Return all profile stats in 2 queries (down from 5).

    Returns dict with keys: post_count, follower_count, following_count,
    average_rating, review_count, endorsement_count.
    """

    # Query 1: counts via scalar subqueries in a single SELECT
    post_sq = (
        select(func.count())
        .select_from(Post)
        .where(
            Post.author_entity_id == entity_id,
            Post.is_hidden.is_(False),
        )
        .correlate(None)
        .scalar_subquery()
        .label("post_count")
    )
    follower_sq = (
        select(func.count())
        .select_from(EntityRelationship)
        .join(Entity, EntityRelationship.source_entity_id == Entity.id)
        .where(
            EntityRelationship.target_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
        )
        .correlate(None)
        .scalar_subquery()
        .label("follower_count")
    )
    following_sq = (
        select(func.count())
        .select_from(EntityRelationship)
        .join(Entity, EntityRelationship.target_entity_id == Entity.id)
        .where(
            EntityRelationship.source_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
        )
        .correlate(None)
        .scalar_subquery()
        .label("following_count")
    )
    endorsement_sq = (
        select(func.count())
        .select_from(CapabilityEndorsement)
        .join(Entity, CapabilityEndorsement.endorser_entity_id == Entity.id)
        .where(
            CapabilityEndorsement.agent_entity_id == entity_id,
            Entity.is_active.is_(True),
        )
        .correlate(None)
        .scalar_subquery()
        .label("endorsement_count")
    )

    result = await db.execute(
        select(post_sq, follower_sq, following_sq, endorsement_sq)
    )
    row = result.one()
    post_count = row[0] or 0
    follower_count = row[1] or 0
    following_count = row[2] or 0
    endorsement_count = row[3] or 0

    # Query 2: review stats
    review_result = await db.execute(
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
    review_row = review_result.one()
    avg_rating = round(float(review_row[0]), 2) if review_row[0] is not None else None
    review_count = review_row[1]

    return {
        "post_count": post_count,
        "follower_count": follower_count,
        "following_count": following_count,
        "average_rating": avg_rating,
        "review_count": review_count,
        "endorsement_count": endorsement_count,
    }


def _compute_badges(
    entity: Entity, framework_diversity_count: int = 0,
) -> list[str]:
    """Compute verification badges for an entity.

    Args:
        entity: The entity to compute badges for.
        framework_diversity_count: Number of distinct framework_source values
            among the entity's interaction partners.  When >= 2 the entity
            earns the ``multi_framework`` badge.
    """
    badges = []
    if entity.email_verified:
        badges.append("email_verified")
    if entity.bio_markdown and len(entity.bio_markdown) > 10:
        badges.append("profile_complete")
    if entity.type == EntityType.AGENT and entity.operator_id:
        badges.append("operator_linked")
    if entity.is_admin:
        badges.append("admin")
    if framework_diversity_count >= 2:
        badges.append("multi_framework")
    if getattr(entity, "is_provisional", False):
        badges.append("unclaimed")
    return badges


async def _get_framework_diversity_count(
    db: AsyncSession, entity_id: uuid.UUID,
) -> int:
    """Count distinct framework_source values among an entity's interaction partners.

    Interaction partners = entities that follow this entity + entities this
    entity follows.  Only partners with a non-null framework_source are counted.
    """
    from sqlalchemy import union_all

    # Followers' frameworks
    follower_fw = (
        select(Entity.framework_source)
        .join(EntityRelationship, EntityRelationship.source_entity_id == Entity.id)
        .where(
            EntityRelationship.target_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
            Entity.framework_source.isnot(None),
        )
    )
    # Following's frameworks
    following_fw = (
        select(Entity.framework_source)
        .join(EntityRelationship, EntityRelationship.target_entity_id == Entity.id)
        .where(
            EntityRelationship.source_entity_id == entity_id,
            EntityRelationship.type == RelationshipType.FOLLOW,
            Entity.is_active.is_(True),
            Entity.framework_source.isnot(None),
        )
    )
    combined = union_all(follower_fw, following_fw).subquery()
    result = await db.scalar(
        select(func.count(func.distinct(combined.c.framework_source)))
    )
    return result or 0


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
    source_type: str | None = Query(
        None, max_length=30,
        description="Filter by import source (e.g. moltbook, github, npm, pypi)",
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Browse entity profiles with optional filters."""
    # By default, exclude bulk-imported Moltbook entities unless
    # the caller explicitly filters by source_type=moltbook.
    _exclude_moltbook = source_type != "moltbook"

    query = select(Entity).where(
        Entity.is_active.is_(True),
        Entity.privacy_tier != PrivacyTier.PRIVATE,
    )

    if _exclude_moltbook:
        query = query.where(
            or_(
                Entity.source_type.is_(None),
                Entity.source_type != "moltbook",
            )
        )

    if q:
        pattern = like_pattern(q)
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

    if source_type:
        query = query.where(Entity.source_type == source_type.lower())

    # Cap offset to prevent deep scans on large tables
    capped_offset = min(offset, 5000)

    total = await db.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0

    result = await db.execute(
        query.order_by(Entity.created_at.desc())
        .offset(capped_offset)
        .limit(min(limit, 100))
    )
    entities = result.scalars().all()

    # Batch-fetch trust scores for all entities in one query (avoids N+1)
    entity_ids = [e.id for e in entities]
    trust_map: dict = {}
    trust_comp_map: dict = {}
    if entity_ids:
        ts_result = await db.execute(
            select(TrustScore).where(TrustScore.entity_id.in_(entity_ids))
        )
        for ts in ts_result.scalars().all():
            trust_map[ts.entity_id] = ts.score
            trust_comp_map[ts.entity_id] = ts.components

    # Batch-fetch operator display names for agents (avoids N+1)
    operator_ids = {e.operator_id for e in entities if e.operator_id}
    operator_names: dict = {}
    if operator_ids:
        op_result = await db.execute(
            select(Entity.id, Entity.display_name).where(Entity.id.in_(operator_ids))
        )
        for row in op_result.all():
            operator_names[row[0]] = row[1]

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
                framework_source=entity.framework_source,
                privacy_tier=entity.privacy_tier.value,
                is_active=entity.is_active,
                email_verified=entity.email_verified,
                trust_score=trust_map.get(entity.id),
                trust_components=trust_comp_map.get(entity.id),
                badges=_compute_badges(entity),
                operator_id=str(entity.operator_id) if entity.operator_id else None,
                operator_display_name=operator_names.get(entity.operator_id),
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

    # Try cache for public, non-own profiles (only for unauthenticated
    # viewers — is_following is viewer-specific so we skip cache when logged in)
    if not is_own and entity.privacy_tier == PrivacyTier.PUBLIC and current_entity is None:
        cached = await cache.get(f"profile:{entity_id}")
        if cached is not None:
            return ProfileResponse(**cached)

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

    # Fetch operator display name for agents
    operator_name = None
    if entity.operator_id:
        op = await db.execute(
            select(Entity.display_name).where(Entity.id == entity.operator_id)
        )
        operator_name = op.scalar_one_or_none()

    ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    stats = await _get_profile_stats(db, entity_id)
    fw_diversity = await _get_framework_diversity_count(db, entity_id)

    # Check if current user follows this entity
    viewer_is_following = False
    if current_entity and not is_own:
        follow_rel = await db.scalar(
            select(EntityRelationship).where(
                EntityRelationship.source_entity_id == current_entity.id,
                EntityRelationship.target_entity_id == entity_id,
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
        )
        viewer_is_following = follow_rel is not None

    response = ProfileResponse(
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
        framework_source=entity.framework_source,
        privacy_tier=entity.privacy_tier.value,
        is_active=entity.is_active,
        email_verified=entity.email_verified,
        trust_score=ts.score if ts else None,
        trust_components=ts.components if ts else None,
        badges=_compute_badges(entity, framework_diversity_count=fw_diversity),
        average_rating=stats["average_rating"],
        review_count=stats["review_count"],
        endorsement_count=stats["endorsement_count"],
        post_count=stats["post_count"],
        follower_count=stats["follower_count"],
        following_count=stats["following_count"],
        operator_id=str(entity.operator_id) if entity.operator_id else None,
        operator_display_name=operator_name,
        is_provisional=getattr(entity, "is_provisional", False) or False,
        provisional_expires_at=(
            entity.provisional_expires_at.isoformat()
            if entity.provisional_expires_at is not None
            else None
        ),
        created_at=entity.created_at.isoformat(),
        is_own_profile=is_own,
        is_following=viewer_is_following,
        source_url=entity.source_url,
        source_type=entity.source_type,
        source_verified_at=(
            entity.source_verified_at.isoformat()
            if entity.source_verified_at is not None
            else None
        ),
        onboarding_data=entity.onboarding_data if entity.onboarding_data else None,
    )

    # Cache public profiles for 60 seconds
    if not is_own and entity.privacy_tier == PrivacyTier.PUBLIC:
        await cache.set(
            f"profile:{entity_id}",
            response.model_dump(mode="json"),
            ttl=cache.TTL_SHORT,
        )

    return response


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
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Allow self-edit OR operator editing their bot
    is_self = current_entity.id == entity_id
    is_operator = (
        entity.type == EntityType.AGENT
        and entity.operator_id == current_entity.id
    )
    if not is_self and not is_operator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own profile or your operated bots",
        )

    from src.content_filter import check_content, sanitize_html, sanitize_text

    update_data = body.model_dump(exclude_unset=True)

    # Platform bot SVGs are admin-only
    av = update_data.get("avatar_url")
    if av and av.startswith("/avatars/") and not current_entity.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform bot avatars are reserved for administrators",
        )
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
        update_data["display_name"] = sanitize_text(update_data["display_name"])
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
    await db.refresh(entity)

    # Invalidate cached profile
    await cache.invalidate(f"profile:{entity_id}")

    ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )
    stats = await _get_profile_stats(db, entity_id)
    fw_diversity = await _get_framework_diversity_count(db, entity_id)

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
        framework_source=entity.framework_source,
        privacy_tier=entity.privacy_tier.value,
        is_active=entity.is_active,
        email_verified=entity.email_verified,
        trust_score=ts.score if ts else None,
        trust_components=ts.components if ts else None,
        badges=_compute_badges(entity, framework_diversity_count=fw_diversity),
        average_rating=stats["average_rating"],
        review_count=stats["review_count"],
        endorsement_count=stats["endorsement_count"],
        post_count=stats["post_count"],
        follower_count=stats["follower_count"],
        following_count=stats["following_count"],
        operator_id=str(entity.operator_id) if entity.operator_id else None,
        created_at=entity.created_at.isoformat(),
        is_own_profile=is_self,
        source_url=entity.source_url,
        source_type=entity.source_type,
        source_verified_at=(
            entity.source_verified_at.isoformat()
            if entity.source_verified_at is not None
            else None
        ),
        onboarding_data=entity.onboarding_data if entity.onboarding_data else None,
    )


@router.get(
    "/{entity_id}/operated-bots",
    dependencies=[Depends(rate_limit_reads)],
)
async def get_operated_bots(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get bots operated by a given entity."""
    _not_moltbook = or_(Entity.source_type.is_(None), Entity.source_type != "moltbook")

    result = await db.execute(
        select(Entity).where(
            Entity.operator_id == entity_id,
            Entity.type == EntityType.AGENT,
            Entity.is_active.is_(True),
            _not_moltbook,
        ).order_by(Entity.display_name)
    )
    bots = result.scalars().all()

    # Batch trust scores
    bot_ids = [b.id for b in bots]
    trust_map: dict = {}
    if bot_ids:
        ts_result = await db.execute(
            select(TrustScore).where(TrustScore.entity_id.in_(bot_ids))
        )
        for ts in ts_result.scalars().all():
            trust_map[ts.entity_id] = ts.score

    return {
        "bots": [
            {
                "id": str(b.id),
                "display_name": b.display_name,
                "avatar_url": b.avatar_url,
                "bio_markdown": b.bio_markdown or "",
                "trust_score": trust_map.get(b.id),
                "framework_source": b.framework_source,
                "capabilities": b.capabilities,
                "created_at": b.created_at.isoformat(),
            }
            for b in bots
        ],
        "total": len(bots),
    }


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


# ---------------------------------------------------------------------------
# Removal request for imported/provisional profiles
# ---------------------------------------------------------------------------


class RemovalRequestBody(BaseModel):
    reason: str = Field("", max_length=2000, description="Why this profile should be removed")


class RemovalRequestResponse(BaseModel):
    status: str
    message: str


@router.post(
    "/{entity_id}/request-removal",
    response_model=RemovalRequestResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
async def request_profile_removal(
    entity_id: uuid.UUID,
    body: RemovalRequestBody,
    db: AsyncSession = Depends(get_db),
):
    """Request removal of a provisional (imported) profile.

    No authentication required — anyone can request removal of an imported
    profile.  Creates a ModerationFlag for admin review.
    """
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    if not entity.is_active:
        raise HTTPException(status_code=400, detail="Profile is already deactivated")

    if not entity.is_provisional:
        raise HTTPException(
            status_code=400,
            detail="Only provisional (imported) profiles can be requested for removal",
        )

    # Content-filter the reason
    if body.reason:
        from src.content_filter import check_content

        reason_check = check_content(body.reason)
        if not reason_check.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Reason rejected: {', '.join(reason_check.flags)}",
            )

    # Create a moderation flag for admin review
    flag = ModerationFlag(
        id=uuid.uuid4(),
        reporter_entity_id=None,  # No auth required
        target_type="entity",
        target_id=entity_id,
        reason=ModerationReason.OTHER,
        details=f"[Removal request] {body.reason}".strip() if body.reason else "[Removal request]",
    )
    db.add(flag)
    await db.flush()

    return RemovalRequestResponse(
        status="submitted",
        message="Removal request submitted for review. We'll review it within 48 hours.",
    )
