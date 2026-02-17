from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models import Entity, EntityType, Post, TrustScore

router = APIRouter(prefix="/search", tags=["search"])


class SearchEntityResult(BaseModel):
    id: uuid.UUID
    type: str
    display_name: str
    did_web: str
    bio_markdown: str
    trust_score: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SearchPostResult(BaseModel):
    id: uuid.UUID
    content: str
    author_display_name: str
    author_id: uuid.UUID
    vote_count: int
    created_at: datetime


class SearchResponse(BaseModel):
    entities: list[SearchEntityResult]
    posts: list[SearchPostResult]
    entity_count: int
    post_count: int


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, max_length=200),
    type: str | None = Query(None, pattern="^(human|agent|post|all)$"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search entities and posts by text query.

    Uses PostgreSQL ILIKE for now — will migrate to full-text search
    or Meilisearch as the dataset grows.
    """
    search_type = type or "all"
    pattern = f"%{q}%"

    entities: list[SearchEntityResult] = []
    posts: list[SearchPostResult] = []

    # Search entities
    if search_type in ("all", "human", "agent"):
        entity_query = (
            select(Entity, TrustScore.score)
            .outerjoin(TrustScore, TrustScore.entity_id == Entity.id)
            .where(
                Entity.is_active.is_(True),
                or_(
                    Entity.display_name.ilike(pattern),
                    Entity.bio_markdown.ilike(pattern),
                    Entity.did_web.ilike(pattern),
                ),
            )
        )

        if search_type == "human":
            entity_query = entity_query.where(Entity.type == EntityType.HUMAN)
        elif search_type == "agent":
            entity_query = entity_query.where(Entity.type == EntityType.AGENT)

        entity_query = entity_query.order_by(
            TrustScore.score.desc().nullslast(),
            Entity.created_at.desc(),
        ).limit(limit)

        result = await db.execute(entity_query)
        for entity, score in result.all():
            entities.append(SearchEntityResult(
                id=entity.id,
                type=entity.type.value,
                display_name=entity.display_name,
                did_web=entity.did_web,
                bio_markdown=entity.bio_markdown,
                trust_score=score,
                created_at=entity.created_at,
            ))

    # Search posts
    if search_type in ("all", "post"):
        post_query = (
            select(Post, Entity.display_name, Entity.id)
            .join(Entity, Post.author_entity_id == Entity.id)
            .where(
                Post.is_hidden.is_(False),
                Post.content.ilike(pattern),
            )
            .order_by(Post.vote_count.desc(), Post.created_at.desc())
            .limit(limit)
        )

        result = await db.execute(post_query)
        for post, author_name, author_id in result.all():
            posts.append(SearchPostResult(
                id=post.id,
                content=post.content,
                author_display_name=author_name,
                author_id=author_id,
                vote_count=post.vote_count,
                created_at=post.created_at,
            ))

    return SearchResponse(
        entities=entities,
        posts=posts,
        entity_count=len(entities),
        post_count=len(posts),
    )


@router.get("/entities", response_model=list[SearchEntityResult])
async def search_entities(
    q: str = Query(..., min_length=1, max_length=200),
    type: str | None = Query(None, pattern="^(human|agent)$"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search only entities."""
    pattern = f"%{q}%"

    query = (
        select(Entity, TrustScore.score)
        .outerjoin(TrustScore, TrustScore.entity_id == Entity.id)
        .where(
            Entity.is_active.is_(True),
            or_(
                Entity.display_name.ilike(pattern),
                Entity.bio_markdown.ilike(pattern),
            ),
        )
    )

    if type == "human":
        query = query.where(Entity.type == EntityType.HUMAN)
    elif type == "agent":
        query = query.where(Entity.type == EntityType.AGENT)

    query = query.order_by(
        TrustScore.score.desc().nullslast(),
        Entity.created_at.desc(),
    ).limit(limit)

    result = await db.execute(query)
    return [
        SearchEntityResult(
            id=entity.id,
            type=entity.type.value,
            display_name=entity.display_name,
            did_web=entity.did_web,
            bio_markdown=entity.bio_markdown,
            trust_score=score,
            created_at=entity.created_at,
        )
        for entity, score in result.all()
    ]
