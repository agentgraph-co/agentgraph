from __future__ import annotations

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import bindparam, func, literal_column, select, text, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from src import cache
from src.api.rate_limit import rate_limit_reads
from src.cache import TTL_SHORT
from src.database import get_db
from src.models import Entity, Post, PrivacyTier

router = APIRouter(prefix="/search", tags=["semantic-search"])


# --- Response models ---


class SemanticResult(BaseModel):
    source_type: str  # "entity" or "post"
    id: uuid.UUID
    snippet: str
    rank: float
    display_name: str | None = None
    entity_type: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SemanticSearchResponse(BaseModel):
    results: list[SemanticResult]
    total: int
    query: str
    scope: str


class SuggestionItem(BaseModel):
    entity_id: uuid.UUID
    display_name: str
    entity_type: str


class SuggestResponse(BaseModel):
    suggestions: list[SuggestionItem]
    query: str


class FacetCounts(BaseModel):
    entity_types: dict[str, int]
    has_posts: int
    has_entities: int
    recent_24h: int
    recent_7d: int


class FacetResponse(BaseModel):
    facets: FacetCounts
    query: str


# --- Helpers ---


def _make_tsquery_safe(q: str) -> str:
    """Convert user query to a safe plainto_tsquery-compatible string.

    Strips characters that could break tsquery parsing.
    """
    # Remove anything that is not alphanumeric, whitespace, or hyphen
    cleaned = re.sub(r"[^\w\s\-]", "", q.strip())
    return cleaned


def _make_prefix_tsquery(q: str) -> str:
    """Convert user query to prefix-matching tsquery string.

    Each word gets a :* suffix for prefix matching, joined with &.
    """
    tokens = q.strip().split()
    if not tokens:
        return ""
    safe = [re.sub(r"[^\w\-]", "", t) + ":*" for t in tokens if t.strip()]
    safe = [t for t in safe if t != ":*"]
    if not safe:
        return ""
    return " & ".join(safe)


# --- Endpoints ---


@router.get(
    "/semantic",
    response_model=SemanticSearchResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def semantic_search(
    q: str = Query(..., min_length=1, max_length=200),
    scope: str = Query("all", pattern="^(all|entities|posts)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> SemanticSearchResponse:
    """Full-text semantic search across entities and posts.

    Uses PostgreSQL ``to_tsvector`` / ``plainto_tsquery`` with ``ts_rank``
    for relevance scoring.  Entity display_name + bio and post content are
    searched.  Results are combined and ranked by relevance score.
    """
    cache_key = f"semantic:{q}:{scope}:{limit}:{offset}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    tsquery_str = _make_tsquery_safe(q)
    if not tsquery_str.strip():
        return SemanticSearchResponse(
            results=[], total=0, query=q, scope=scope,
        )

    results: list[SemanticResult] = []
    subqueries = []

    if scope in ("all", "entities"):
        entity_ts = func.to_tsvector(
            text("'english'"),
            func.coalesce(Entity.display_name, text("''"))
            + text("' '")
            + func.coalesce(Entity.bio_markdown, text("''")),
        )
        entity_tsq = func.plainto_tsquery(
            text("'english'"),
            bindparam("eq_sem", tsquery_str),
        )
        entity_rank = func.ts_rank(entity_ts, entity_tsq)
        entity_headline = func.ts_headline(
            text("'english'"),
            func.coalesce(Entity.display_name, text("''"))
            + text("' — '")
            + func.coalesce(Entity.bio_markdown, text("''")),
            entity_tsq,
            text("'MaxFragments=1, MaxWords=30, MinWords=5'"),
        )

        entity_q = (
            select(
                literal_column("'entity'").label("source_type"),
                Entity.id.label("id"),
                entity_headline.label("snippet"),
                entity_rank.label("rank"),
                Entity.display_name.label("display_name"),
                Entity.type.label("entity_type"),
                Entity.created_at.label("created_at"),
            )
            .where(
                Entity.is_active.is_(True),
                Entity.privacy_tier == PrivacyTier.PUBLIC,
                entity_ts.op("@@")(entity_tsq),
            )
        )
        subqueries.append(entity_q)

    if scope in ("all", "posts"):
        post_ts = func.to_tsvector(
            text("'english'"), Post.content,
        )
        post_tsq = func.plainto_tsquery(
            text("'english'"),
            bindparam("pq_sem", tsquery_str),
        )
        post_rank = func.ts_rank(post_ts, post_tsq)
        post_headline = func.ts_headline(
            text("'english'"),
            Post.content,
            post_tsq,
            text("'MaxFragments=1, MaxWords=30, MinWords=5'"),
        )

        post_q = (
            select(
                literal_column("'post'").label("source_type"),
                Post.id.label("id"),
                post_headline.label("snippet"),
                post_rank.label("rank"),
                Entity.display_name.label("display_name"),
                Entity.type.label("entity_type"),
                Post.created_at.label("created_at"),
            )
            .join(Entity, Post.author_entity_id == Entity.id)
            .where(
                Post.is_hidden.is_(False),
                Entity.is_active.is_(True),
                post_ts.op("@@")(post_tsq),
            )
        )
        subqueries.append(post_q)

    if not subqueries:
        return SemanticSearchResponse(
            results=[], total=0, query=q, scope=scope,
        )

    if len(subqueries) == 1:
        combined = subqueries[0].order_by(
            text("rank DESC"),
        ).offset(offset).limit(limit)
    else:
        combined_union = union_all(*subqueries).subquery()
        combined = (
            select(combined_union)
            .order_by(combined_union.c.rank.desc())
            .offset(offset)
            .limit(limit)
        )

    result = await db.execute(combined)
    rows = result.all()

    for row in rows:
        results.append(SemanticResult(
            source_type=row.source_type,
            id=row.id,
            snippet=row.snippet or "",
            rank=float(row.rank) if row.rank else 0.0,
            display_name=row.display_name,
            entity_type=(
                row.entity_type.value
                if hasattr(row.entity_type, "value")
                else row.entity_type
            ),
            created_at=row.created_at,
        ))

    # Count total matches (without offset/limit) for pagination
    count_subqueries = []
    if scope in ("all", "entities"):
        e_ts = func.to_tsvector(
            text("'english'"),
            func.coalesce(Entity.display_name, text("''"))
            + text("' '")
            + func.coalesce(Entity.bio_markdown, text("''")),
        )
        e_tsq = func.plainto_tsquery(
            text("'english'"),
            bindparam("eq_cnt", tsquery_str),
        )
        count_subqueries.append(
            select(func.count()).select_from(Entity).where(
                Entity.is_active.is_(True),
                Entity.privacy_tier == PrivacyTier.PUBLIC,
                e_ts.op("@@")(e_tsq),
            )
        )
    if scope in ("all", "posts"):
        p_ts = func.to_tsvector(
            text("'english'"), Post.content,
        )
        p_tsq = func.plainto_tsquery(
            text("'english'"),
            bindparam("pq_cnt", tsquery_str),
        )
        count_subqueries.append(
            select(func.count()).select_from(Post).join(
                Entity, Post.author_entity_id == Entity.id,
            ).where(
                Post.is_hidden.is_(False),
                Entity.is_active.is_(True),
                p_ts.op("@@")(p_tsq),
            )
        )

    total = 0
    for cq in count_subqueries:
        count_result = await db.execute(cq)
        total += count_result.scalar() or 0

    response = SemanticSearchResponse(
        results=results, total=total, query=q, scope=scope,
    )
    await cache.set(
        cache_key, response.model_dump(mode="json"), ttl=TTL_SHORT,
    )
    return response


@router.get(
    "/suggest",
    response_model=SuggestResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def suggest(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> SuggestResponse:
    """Autocomplete suggestions based on prefix matching of entity display names.

    Requires at least 2 characters.  Returns matching entity names with IDs.
    """
    from src.utils import like_pattern

    pattern = like_pattern(q)

    query = (
        select(Entity.id, Entity.display_name, Entity.type)
        .where(
            Entity.is_active.is_(True),
            Entity.privacy_tier == PrivacyTier.PUBLIC,
            Entity.display_name.ilike(pattern),
        )
        .order_by(Entity.display_name)
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    suggestions = [
        SuggestionItem(
            entity_id=row.id,
            display_name=row.display_name,
            entity_type=row.type.value,
        )
        for row in rows
    ]

    return SuggestResponse(suggestions=suggestions, query=q)


@router.get(
    "/facets",
    response_model=FacetResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def facets(
    q: str = Query(..., min_length=1, max_length=200),
    db: AsyncSession = Depends(get_db),
) -> FacetResponse:
    """Search with faceted results — counts by entity type and date range.

    Returns grouped counts useful for building filter UIs.
    """
    from sqlalchemy import case

    tsquery_str = _make_tsquery_safe(q)
    if not tsquery_str.strip():
        return FacetResponse(
            facets=FacetCounts(
                entity_types={},
                has_posts=0,
                has_entities=0,
                recent_24h=0,
                recent_7d=0,
            ),
            query=q,
        )

    now = func.now()

    # Entity facets
    e_ts = func.to_tsvector(
        text("'english'"),
        func.coalesce(Entity.display_name, text("''"))
        + text("' '")
        + func.coalesce(Entity.bio_markdown, text("''")),
    )
    e_tsq = func.plainto_tsquery(
        text("'english'"),
        bindparam("eq_facet", tsquery_str),
    )

    entity_type_q = (
        select(
            Entity.type.label("etype"),
            func.count().label("cnt"),
        )
        .where(
            Entity.is_active.is_(True),
            Entity.privacy_tier == PrivacyTier.PUBLIC,
            e_ts.op("@@")(e_tsq),
        )
        .group_by(Entity.type)
    )
    entity_type_result = await db.execute(entity_type_q)
    entity_types: dict[str, int] = {}
    has_entities = 0
    for row in entity_type_result.all():
        entity_types[row.etype.value] = row.cnt
        has_entities += row.cnt

    # Entity date facets
    e_date_q = (
        select(
            func.count(case(
                (Entity.created_at >= now - text("interval '24 hours'"), 1),
            )).label("recent_24h"),
            func.count(case(
                (Entity.created_at >= now - text("interval '7 days'"), 1),
            )).label("recent_7d"),
        )
        .where(
            Entity.is_active.is_(True),
            Entity.privacy_tier == PrivacyTier.PUBLIC,
            e_ts.op("@@")(func.plainto_tsquery(
                text("'english'"),
                bindparam("eq_facet_date", tsquery_str),
            )),
        )
    )
    e_date_result = await db.execute(e_date_q)
    e_date_row = e_date_result.one()
    entity_24h = e_date_row.recent_24h or 0
    entity_7d = e_date_row.recent_7d or 0

    # Post facets
    p_ts = func.to_tsvector(
        text("'english'"), Post.content,
    )
    p_tsq = func.plainto_tsquery(
        text("'english'"),
        bindparam("pq_facet", tsquery_str),
    )

    post_count_q = (
        select(
            func.count().label("total"),
            func.count(case(
                (Post.created_at >= now - text("interval '24 hours'"), 1),
            )).label("recent_24h"),
            func.count(case(
                (Post.created_at >= now - text("interval '7 days'"), 1),
            )).label("recent_7d"),
        )
        .select_from(Post)
        .join(Entity, Post.author_entity_id == Entity.id)
        .where(
            Post.is_hidden.is_(False),
            Entity.is_active.is_(True),
            p_ts.op("@@")(p_tsq),
        )
    )
    post_result = await db.execute(post_count_q)
    post_row = post_result.one()
    has_posts = post_row.total or 0
    post_24h = post_row.recent_24h or 0
    post_7d = post_row.recent_7d or 0

    return FacetResponse(
        facets=FacetCounts(
            entity_types=entity_types,
            has_posts=has_posts,
            has_entities=has_entities,
            recent_24h=entity_24h + post_24h,
            recent_7d=entity_7d + post_7d,
        ),
        query=q,
    )
