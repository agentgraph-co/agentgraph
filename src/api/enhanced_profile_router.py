from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.api.rate_limit import rate_limit_reads
from src.database import get_db
from src.models import (
    Entity,
    EntityRelationship,
    FormalAttestation,
    Post,
    RelationshipType,
    Review,
    TrustScore,
)

router = APIRouter(prefix="/profiles", tags=["enhanced-profiles"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ReviewItemResponse(BaseModel):
    id: uuid.UUID
    reviewer_entity_id: uuid.UUID
    reviewer_display_name: str
    reviewer_trust_score: float | None
    rating: int
    text: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewListResponse(BaseModel):
    reviews: list[ReviewItemResponse]
    total: int


class AttestationItemResponse(BaseModel):
    id: uuid.UUID
    issuer_entity_id: uuid.UUID
    issuer_display_name: str
    subject_entity_id: uuid.UUID
    subject_display_name: str
    attestation_type: str
    evidence: str | None
    expires_at: datetime | None
    is_revoked: bool
    revoked_at: datetime | None
    is_expired: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AttestationsResponse(BaseModel):
    received: list[AttestationItemResponse]
    received_total: int
    issued: list[AttestationItemResponse]
    issued_total: int


class TrustBadgeItem(BaseModel):
    badge_type: str
    count: int
    latest_attestation_date: datetime | None


class TrustBadgesResponse(BaseModel):
    entity_id: uuid.UUID
    badges: list[TrustBadgeItem]
    email_verified: bool


class ProfileSummaryResponse(BaseModel):
    entity_id: uuid.UUID
    display_name: str
    trust_score: float | None
    trust_components: dict | None
    review_count: int
    average_rating: float | None
    attestation_counts: dict[str, int]
    follower_count: int
    following_count: int
    post_count: int
    member_since: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_expired(att: FormalAttestation) -> bool:
    if att.expires_at is None:
        return False
    return att.expires_at < datetime.now(timezone.utc)


def _build_attestation_item(
    att: FormalAttestation,
    issuer_name: str,
    subject_name: str,
) -> AttestationItemResponse:
    return AttestationItemResponse(
        id=att.id,
        issuer_entity_id=att.issuer_entity_id,
        issuer_display_name=issuer_name,
        subject_entity_id=att.subject_entity_id,
        subject_display_name=subject_name,
        attestation_type=att.attestation_type,
        evidence=att.evidence,
        expires_at=att.expires_at,
        is_revoked=att.is_revoked,
        revoked_at=att.revoked_at,
        is_expired=_is_expired(att),
        created_at=att.created_at,
    )


async def _ensure_entity_exists(
    db: AsyncSession, entity_id: uuid.UUID,
) -> Entity:
    entity = await db.get(Entity, entity_id)
    if entity is None or not entity.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{entity_id}/reviews",
    response_model=ReviewListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_entity_reviews(
    entity_id: uuid.UUID,
    min_rating: int | None = Query(None, ge=1, le=5),
    max_rating: int | None = Query(None, ge=1, le=5),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List reviews where the entity is the subject, newest first."""
    await _ensure_entity_exists(db, entity_id)

    base_where = [Review.target_entity_id == entity_id]
    if min_rating is not None:
        base_where.append(Review.rating >= min_rating)
    if max_rating is not None:
        base_where.append(Review.rating <= max_rating)

    # Total count
    total = await db.scalar(
        select(func.count())
        .select_from(Review)
        .where(*base_where)
    ) or 0

    # Fetch reviews with reviewer display name and trust score
    reviewer_alias = aliased(Entity)
    query = (
        select(
            Review,
            reviewer_alias.display_name,
            TrustScore.score,
        )
        .join(reviewer_alias, Review.reviewer_entity_id == reviewer_alias.id)
        .outerjoin(
            TrustScore, TrustScore.entity_id == Review.reviewer_entity_id,
        )
        .where(*base_where)
        .order_by(Review.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)

    reviews = []
    for rev, display_name, trust_score in result.all():
        reviews.append(
            ReviewItemResponse(
                id=rev.id,
                reviewer_entity_id=rev.reviewer_entity_id,
                reviewer_display_name=display_name,
                reviewer_trust_score=(
                    round(float(trust_score), 4) if trust_score is not None
                    else None
                ),
                rating=rev.rating,
                text=rev.text,
                created_at=rev.created_at,
            )
        )

    return ReviewListResponse(reviews=reviews, total=total)


@router.get(
    "/{entity_id}/attestations",
    response_model=AttestationsResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_entity_attestations(
    entity_id: uuid.UUID,
    attestation_type: str | None = Query(None),
    include_revoked: bool = Query(False),
    include_expired: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List formal attestations received and issued by an entity."""
    await _ensure_entity_exists(db, entity_id)

    now = datetime.now(timezone.utc)

    # --- Shared filter builder ---
    def _common_filters(
        direction_col,
    ) -> list:
        filters = [direction_col == entity_id]
        if attestation_type is not None:
            filters.append(
                FormalAttestation.attestation_type == attestation_type
            )
        if not include_revoked:
            filters.append(FormalAttestation.is_revoked.is_(False))
        if not include_expired:
            filters.append(
                (FormalAttestation.expires_at.is_(None))
                | (FormalAttestation.expires_at >= now)
            )
        return filters

    # --- Received attestations ---
    recv_filters = _common_filters(FormalAttestation.subject_entity_id)
    received_total = await db.scalar(
        select(func.count())
        .select_from(FormalAttestation)
        .where(*recv_filters)
    ) or 0

    issuer_a = aliased(Entity)
    subject_a = aliased(Entity)
    recv_query = (
        select(FormalAttestation, issuer_a.display_name, subject_a.display_name)
        .join(issuer_a, FormalAttestation.issuer_entity_id == issuer_a.id)
        .join(subject_a, FormalAttestation.subject_entity_id == subject_a.id)
        .where(*recv_filters)
        .order_by(FormalAttestation.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    recv_result = await db.execute(recv_query)
    received = [
        _build_attestation_item(att, i_name, s_name)
        for att, i_name, s_name in recv_result.all()
    ]

    # --- Issued attestations ---
    issued_filters = _common_filters(FormalAttestation.issuer_entity_id)
    issued_total = await db.scalar(
        select(func.count())
        .select_from(FormalAttestation)
        .where(*issued_filters)
    ) or 0

    issuer_b = aliased(Entity)
    subject_b = aliased(Entity)
    issued_query = (
        select(FormalAttestation, issuer_b.display_name, subject_b.display_name)
        .join(issuer_b, FormalAttestation.issuer_entity_id == issuer_b.id)
        .join(subject_b, FormalAttestation.subject_entity_id == subject_b.id)
        .where(*issued_filters)
        .order_by(FormalAttestation.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    issued_result = await db.execute(issued_query)
    issued = [
        _build_attestation_item(att, i_name, s_name)
        for att, i_name, s_name in issued_result.all()
    ]

    return AttestationsResponse(
        received=received,
        received_total=received_total,
        issued=issued,
        issued_total=issued_total,
    )


@router.get(
    "/{entity_id}/trust-badges",
    response_model=TrustBadgesResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_trust_badges(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get verification badge summary aggregated from formal attestations."""
    entity = await _ensure_entity_exists(db, entity_id)

    now = datetime.now(timezone.utc)

    # Aggregate active (non-revoked, non-expired) attestations by type
    query = (
        select(
            FormalAttestation.attestation_type,
            func.count().label("cnt"),
            func.max(FormalAttestation.created_at).label("latest"),
        )
        .where(
            FormalAttestation.subject_entity_id == entity_id,
            FormalAttestation.is_revoked.is_(False),
            (FormalAttestation.expires_at.is_(None))
            | (FormalAttestation.expires_at >= now),
        )
        .group_by(FormalAttestation.attestation_type)
    )
    result = await db.execute(query)

    badges = []
    for att_type, cnt, latest in result.all():
        badges.append(
            TrustBadgeItem(
                badge_type=att_type,
                count=cnt,
                latest_attestation_date=latest,
            )
        )

    return TrustBadgesResponse(
        entity_id=entity_id,
        badges=badges,
        email_verified=entity.email_verified,
    )


@router.get(
    "/{entity_id}/summary",
    response_model=ProfileSummaryResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_profile_summary(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Combined profile summary with trust, reviews, attestations, social."""
    entity = await _ensure_entity_exists(db, entity_id)

    # Trust score
    ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == entity_id)
    )

    # Review stats
    review_result = await db.execute(
        select(
            func.count(Review.id),
            func.avg(Review.rating),
        )
        .join(Entity, Review.reviewer_entity_id == Entity.id)
        .where(
            Review.target_entity_id == entity_id,
            Entity.is_active.is_(True),
        )
    )
    review_row = review_result.one()
    review_count = review_row[0] or 0
    avg_rating = (
        round(float(review_row[1]), 2) if review_row[1] is not None else None
    )

    # Attestation counts by type (active only)
    now = datetime.now(timezone.utc)
    att_result = await db.execute(
        select(
            FormalAttestation.attestation_type,
            func.count().label("cnt"),
        )
        .where(
            FormalAttestation.subject_entity_id == entity_id,
            FormalAttestation.is_revoked.is_(False),
            (FormalAttestation.expires_at.is_(None))
            | (FormalAttestation.expires_at >= now),
        )
        .group_by(FormalAttestation.attestation_type)
    )
    attestation_counts = {row[0]: row[1] for row in att_result.all()}

    # Social counts (followers, following)
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

    # Post count
    post_count = await db.scalar(
        select(func.count())
        .select_from(Post)
        .where(
            Post.author_entity_id == entity_id,
            Post.is_hidden.is_(False),
        )
    ) or 0

    return ProfileSummaryResponse(
        entity_id=entity_id,
        display_name=entity.display_name,
        trust_score=ts.score if ts else None,
        trust_components=ts.components if ts else None,
        review_count=review_count,
        average_rating=avg_rating,
        attestation_counts=attestation_counts,
        follower_count=follower_count,
        following_count=following_count,
        post_count=post_count,
        member_since=entity.created_at,
    )
