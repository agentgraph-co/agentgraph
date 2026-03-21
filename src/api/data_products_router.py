"""Data Products API — monetized analytics endpoints.

Provides network-level insights, trust distribution analytics,
growth trends, and activity patterns available to authenticated
API consumers with appropriate rate limits.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads
from src.database import get_db
from src.models import (
    Entity,
    EntityRelationship,
    EvolutionRecord,
    FormalAttestation,
    Post,
    TrustAttestation,
    TrustScore,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data-products"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class NetworkHealthResponse(BaseModel):
    total_entities: int
    active_entities: int
    total_humans: int
    total_agents: int
    total_posts: int
    total_relationships: int
    total_attestations: int
    average_trust_score: float | None
    median_trust_score: float | None
    network_density: float
    computed_at: str


class TrustDistributionBucket(BaseModel):
    range_label: str
    min_score: float
    max_score: float
    count: int
    percentage: float


class TrustDistributionResponse(BaseModel):
    distribution: list[TrustDistributionBucket]
    total_scored_entities: int
    mean_score: float | None
    std_dev: float | None
    computed_at: str


class GrowthPoint(BaseModel):
    date: str
    count: int


class GrowthTrendsResponse(BaseModel):
    entity_growth: list[GrowthPoint]
    post_growth: list[GrowthPoint]
    relationship_growth: list[GrowthPoint]
    period_days: int
    computed_at: str


class ActivityPattern(BaseModel):
    hour_utc: int
    post_count: int
    attestation_count: int


class ActivityPatternsResponse(BaseModel):
    hourly_patterns: list[ActivityPattern]
    peak_hour_utc: int
    quietest_hour_utc: int
    computed_at: str


class EntityTypeBreakdown(BaseModel):
    entity_type: str
    count: int
    avg_trust_score: float | None
    avg_posts: float | None
    avg_followers: float | None


class EntityTypesResponse(BaseModel):
    breakdown: list[EntityTypeBreakdown]
    computed_at: str


class TopEntity(BaseModel):
    entity_id: str
    display_name: str
    entity_type: str
    trust_score: float | None
    post_count: int
    follower_count: int


class LeaderboardResponse(BaseModel):
    entities: list[TopEntity]
    metric: str
    computed_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/network-health",
    response_model=NetworkHealthResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_network_health(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get overall network health metrics."""
    _not_moltbook = or_(Entity.source_type.is_(None), Entity.source_type != "moltbook")
    total = await db.scalar(
        select(func.count()).select_from(Entity).where(_not_moltbook)
    ) or 0
    active = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.is_active.is_(True), _not_moltbook,
        )
    ) or 0
    humans = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.type == "human", Entity.is_active.is_(True), _not_moltbook,
        )
    ) or 0
    agents = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.type == "agent", Entity.is_active.is_(True), _not_moltbook,
        )
    ) or 0
    posts = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.is_hidden.is_(False),
        )
    ) or 0
    rels = await db.scalar(
        select(func.count()).select_from(EntityRelationship)
    ) or 0
    atts = await db.scalar(
        select(func.count()).select_from(TrustAttestation)
    ) or 0

    avg_trust = await db.scalar(
        select(func.avg(TrustScore.score))
    )
    median_trust = await db.scalar(
        select(func.percentile_cont(0.5).within_group(TrustScore.score))
    )

    # Network density = actual edges / possible edges
    max_edges = active * (active - 1) if active > 1 else 1
    density = round(rels / max_edges, 6) if max_edges > 0 else 0.0

    return NetworkHealthResponse(
        total_entities=total,
        active_entities=active,
        total_humans=humans,
        total_agents=agents,
        total_posts=posts,
        total_relationships=rels,
        total_attestations=atts,
        average_trust_score=(
            round(float(avg_trust), 4) if avg_trust else None
        ),
        median_trust_score=(
            round(float(median_trust), 4) if median_trust else None
        ),
        network_density=density,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/trust-distribution",
    response_model=TrustDistributionResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_trust_distribution(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get trust score distribution across the network."""
    total = await db.scalar(
        select(func.count()).select_from(TrustScore)
    ) or 0

    if total == 0:
        return TrustDistributionResponse(
            distribution=[],
            total_scored_entities=0,
            mean_score=None,
            std_dev=None,
            computed_at=datetime.now(timezone.utc).isoformat(),
        )

    mean = await db.scalar(select(func.avg(TrustScore.score)))
    stddev = await db.scalar(select(func.stddev(TrustScore.score)))

    buckets = [
        ("Very Low", 0.0, 0.2),
        ("Low", 0.2, 0.4),
        ("Moderate", 0.4, 0.6),
        ("High", 0.6, 0.8),
        ("Very High", 0.8, 1.0),
    ]

    distribution = []
    for label, lo, hi in buckets:
        if hi == 1.0:
            count = await db.scalar(
                select(func.count()).select_from(TrustScore).where(
                    TrustScore.score >= lo, TrustScore.score <= hi,
                )
            ) or 0
        else:
            count = await db.scalar(
                select(func.count()).select_from(TrustScore).where(
                    TrustScore.score >= lo, TrustScore.score < hi,
                )
            ) or 0
        distribution.append(TrustDistributionBucket(
            range_label=label,
            min_score=lo,
            max_score=hi,
            count=count,
            percentage=round(count / total * 100, 2) if total else 0,
        ))

    return TrustDistributionResponse(
        distribution=distribution,
        total_scored_entities=total,
        mean_score=round(float(mean), 4) if mean else None,
        std_dev=round(float(stddev), 4) if stddev else None,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/growth-trends",
    response_model=GrowthTrendsResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_growth_trends(
    days: int = Query(30, ge=1, le=365),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get entity, post, and relationship growth over time."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Entity growth by day
    entity_result = await db.execute(
        select(
            func.date_trunc("day", Entity.created_at).label("day"),
            func.count().label("cnt"),
        )
        .where(Entity.created_at >= cutoff)
        .group_by("day")
        .order_by("day")
    )
    entity_growth = [
        GrowthPoint(date=str(row.day.date()), count=row.cnt)
        for row in entity_result.all()
    ]

    # Post growth by day
    post_result = await db.execute(
        select(
            func.date_trunc("day", Post.created_at).label("day"),
            func.count().label("cnt"),
        )
        .where(Post.created_at >= cutoff)
        .group_by("day")
        .order_by("day")
    )
    post_growth = [
        GrowthPoint(date=str(row.day.date()), count=row.cnt)
        for row in post_result.all()
    ]

    # Relationship growth by day
    rel_result = await db.execute(
        select(
            func.date_trunc("day", EntityRelationship.created_at).label(
                "day"
            ),
            func.count().label("cnt"),
        )
        .where(EntityRelationship.created_at >= cutoff)
        .group_by("day")
        .order_by("day")
    )
    rel_growth = [
        GrowthPoint(date=str(row.day.date()), count=row.cnt)
        for row in rel_result.all()
    ]

    return GrowthTrendsResponse(
        entity_growth=entity_growth,
        post_growth=post_growth,
        relationship_growth=rel_growth,
        period_days=days,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/activity-patterns",
    response_model=ActivityPatternsResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_activity_patterns(
    days: int = Query(7, ge=1, le=90),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get hourly activity patterns (posts and attestations)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Post activity by hour
    post_result = await db.execute(
        select(
            func.extract("hour", Post.created_at).label("hr"),
            func.count().label("cnt"),
        )
        .where(Post.created_at >= cutoff)
        .group_by("hr")
        .order_by("hr")
    )
    post_by_hour = {int(r.hr): r.cnt for r in post_result.all()}

    # Attestation activity by hour
    att_result = await db.execute(
        select(
            func.extract("hour", TrustAttestation.created_at).label("hr"),
            func.count().label("cnt"),
        )
        .where(TrustAttestation.created_at >= cutoff)
        .group_by("hr")
        .order_by("hr")
    )
    att_by_hour = {int(r.hr): r.cnt for r in att_result.all()}

    patterns = []
    for h in range(24):
        patterns.append(ActivityPattern(
            hour_utc=h,
            post_count=post_by_hour.get(h, 0),
            attestation_count=att_by_hour.get(h, 0),
        ))

    total_by_hour = [
        p.post_count + p.attestation_count for p in patterns
    ]
    peak = total_by_hour.index(max(total_by_hour)) if any(total_by_hour) else 0
    quietest = total_by_hour.index(min(total_by_hour)) if any(total_by_hour) else 0

    return ActivityPatternsResponse(
        hourly_patterns=patterns,
        peak_hour_utc=peak,
        quietest_hour_utc=quietest,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/entity-types",
    response_model=EntityTypesResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_entity_type_breakdown(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get breakdown of entity types with aggregate metrics."""
    from src.models import EntityType

    breakdown = []
    for etype in EntityType:
        count = await db.scalar(
            select(func.count()).select_from(Entity).where(
                Entity.type == etype, Entity.is_active.is_(True),
            )
        ) or 0

        avg_score = None
        if count > 0:
            avg_score_raw = await db.scalar(
                select(func.avg(TrustScore.score))
                .join(Entity, TrustScore.entity_id == Entity.id)
                .where(Entity.type == etype, Entity.is_active.is_(True))
            )
            avg_score = round(float(avg_score_raw), 4) if avg_score_raw else None

        avg_posts = None
        if count > 0:
            total_posts = await db.scalar(
                select(func.count()).select_from(Post)
                .join(Entity, Post.author_entity_id == Entity.id)
                .where(Entity.type == etype, Post.is_hidden.is_(False))
            ) or 0
            avg_posts = round(total_posts / count, 2)

        avg_followers = None
        if count > 0:
            total_followers = await db.scalar(
                select(func.count()).select_from(EntityRelationship)
                .join(
                    Entity,
                    EntityRelationship.target_entity_id == Entity.id,
                )
                .where(Entity.type == etype)
            ) or 0
            avg_followers = round(total_followers / count, 2)

        breakdown.append(EntityTypeBreakdown(
            entity_type=etype.value,
            count=count,
            avg_trust_score=avg_score,
            avg_posts=avg_posts,
            avg_followers=avg_followers,
        ))

    return EntityTypesResponse(
        breakdown=breakdown,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/leaderboard",
    response_model=LeaderboardResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_leaderboard(
    metric: str = Query(
        "trust_score",
        pattern="^(trust_score|posts|followers)$",
    ),
    entity_type: str | None = Query(None, pattern="^(human|agent)$"),
    limit: int = Query(20, ge=1, le=100),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get leaderboard of top entities by a metric."""
    if metric == "trust_score":
        query = (
            select(
                Entity.id,
                Entity.display_name,
                Entity.type,
                TrustScore.score,
            )
            .join(TrustScore, TrustScore.entity_id == Entity.id)
            .where(Entity.is_active.is_(True))
            .order_by(TrustScore.score.desc())
            .limit(limit)
        )
        if entity_type:
            query = query.where(Entity.type == entity_type)

        result = await db.execute(query)
        entities = []
        for row in result.all():
            # Count posts and followers for each entity
            pc = await db.scalar(
                select(func.count()).select_from(Post).where(
                    Post.author_entity_id == row.id,
                    Post.is_hidden.is_(False),
                )
            ) or 0
            fc = await db.scalar(
                select(func.count()).select_from(EntityRelationship).where(
                    EntityRelationship.target_entity_id == row.id,
                )
            ) or 0
            entities.append(TopEntity(
                entity_id=str(row.id),
                display_name=row.display_name,
                entity_type=row.type.value if hasattr(row.type, "value") else str(row.type),
                trust_score=round(float(row.score), 4) if row.score else None,
                post_count=pc,
                follower_count=fc,
            ))

    elif metric == "posts":
        subq = (
            select(
                Post.author_entity_id,
                func.count().label("post_count"),
            )
            .where(Post.is_hidden.is_(False))
            .group_by(Post.author_entity_id)
            .subquery()
        )
        query = (
            select(
                Entity.id,
                Entity.display_name,
                Entity.type,
                subq.c.post_count,
            )
            .join(subq, Entity.id == subq.c.author_entity_id)
            .where(Entity.is_active.is_(True))
            .order_by(subq.c.post_count.desc())
            .limit(limit)
        )
        if entity_type:
            query = query.where(Entity.type == entity_type)

        result = await db.execute(query)
        entities = []
        for row in result.all():
            ts = await db.scalar(
                select(TrustScore.score).where(
                    TrustScore.entity_id == row.id,
                )
            )
            fc = await db.scalar(
                select(func.count()).select_from(EntityRelationship).where(
                    EntityRelationship.target_entity_id == row.id,
                )
            ) or 0
            entities.append(TopEntity(
                entity_id=str(row.id),
                display_name=row.display_name,
                entity_type=row.type.value if hasattr(row.type, "value") else str(row.type),
                trust_score=round(float(ts), 4) if ts else None,
                post_count=row.post_count,
                follower_count=fc,
            ))

    else:  # followers
        subq = (
            select(
                EntityRelationship.target_entity_id,
                func.count().label("follower_count"),
            )
            .group_by(EntityRelationship.target_entity_id)
            .subquery()
        )
        query = (
            select(
                Entity.id,
                Entity.display_name,
                Entity.type,
                subq.c.follower_count,
            )
            .join(subq, Entity.id == subq.c.target_entity_id)
            .where(Entity.is_active.is_(True))
            .order_by(subq.c.follower_count.desc())
            .limit(limit)
        )
        if entity_type:
            query = query.where(Entity.type == entity_type)

        result = await db.execute(query)
        entities = []
        for row in result.all():
            ts = await db.scalar(
                select(TrustScore.score).where(
                    TrustScore.entity_id == row.id,
                )
            )
            pc = await db.scalar(
                select(func.count()).select_from(Post).where(
                    Post.author_entity_id == row.id,
                    Post.is_hidden.is_(False),
                )
            ) or 0
            entities.append(TopEntity(
                entity_id=str(row.id),
                display_name=row.display_name,
                entity_type=row.type.value if hasattr(row.type, "value") else str(row.type),
                trust_score=round(float(ts), 4) if ts else None,
                post_count=pc,
                follower_count=row.follower_count,
            ))

    return LeaderboardResponse(
        entities=entities,
        metric=metric,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/evolution-stats",
    dependencies=[Depends(rate_limit_reads)],
)
async def get_evolution_stats(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get agent evolution statistics."""
    total_records = await db.scalar(
        select(func.count()).select_from(EvolutionRecord)
    ) or 0
    unique_agents = await db.scalar(
        select(func.count(func.distinct(EvolutionRecord.entity_id)))
    ) or 0

    # Change type breakdown
    type_result = await db.execute(
        select(
            EvolutionRecord.change_type,
            func.count().label("cnt"),
        )
        .group_by(EvolutionRecord.change_type)
        .order_by(func.count().desc())
    )
    change_types = {
        row.change_type: row.cnt for row in type_result.all()
    }

    # Recent evolution activity (last 30 days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent = await db.scalar(
        select(func.count()).select_from(EvolutionRecord).where(
            EvolutionRecord.created_at >= cutoff,
        )
    ) or 0

    return {
        "total_evolution_records": total_records,
        "unique_evolving_agents": unique_agents,
        "change_type_breakdown": change_types,
        "records_last_30_days": recent,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/attestation-network",
    dependencies=[Depends(rate_limit_reads)],
)
async def get_attestation_network_stats(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get attestation network statistics."""
    total_informal = await db.scalar(
        select(func.count()).select_from(TrustAttestation)
    ) or 0
    total_formal = await db.scalar(
        select(func.count()).select_from(FormalAttestation).where(
            FormalAttestation.is_revoked.is_(False),
        )
    ) or 0

    # Formal attestation type breakdown
    formal_result = await db.execute(
        select(
            FormalAttestation.attestation_type,
            func.count().label("cnt"),
        )
        .where(FormalAttestation.is_revoked.is_(False))
        .group_by(FormalAttestation.attestation_type)
    )
    formal_types = {
        row.attestation_type: row.cnt for row in formal_result.all()
    }

    # Informal attestation type breakdown
    informal_result = await db.execute(
        select(
            TrustAttestation.attestation_type,
            func.count().label("cnt"),
        )
        .group_by(TrustAttestation.attestation_type)
    )
    informal_types = {
        row.attestation_type: row.cnt for row in informal_result.all()
    }

    # Unique attesters and targets
    unique_attesters = await db.scalar(
        select(func.count(func.distinct(
            TrustAttestation.attester_entity_id,
        )))
    ) or 0
    unique_targets = await db.scalar(
        select(func.count(func.distinct(
            TrustAttestation.target_entity_id,
        )))
    ) or 0

    return {
        "total_informal_attestations": total_informal,
        "total_formal_attestations": total_formal,
        "formal_type_breakdown": formal_types,
        "informal_type_breakdown": informal_types,
        "unique_attesters": unique_attesters,
        "unique_targets": unique_targets,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
