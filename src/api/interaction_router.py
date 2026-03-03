"""Interaction history API endpoints.

Provides pairwise interaction timelines, partner summaries, and
detailed stats for entity-to-entity interaction tracking.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads
from src.database import get_db
from src.models import Entity, InteractionEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interactions", tags=["interactions"])


# --- Schemas ---


class InteractionEventResponse(BaseModel):
    id: uuid.UUID
    entity_a_id: uuid.UUID
    entity_b_id: uuid.UUID
    interaction_type: str
    context: dict | None = None
    created_at: str

    model_config = {"from_attributes": True}


class PairwiseTimelineResponse(BaseModel):
    events: list[InteractionEventResponse]
    count: int
    next_cursor: str | None = None


class InteractionPartner(BaseModel):
    entity_id: uuid.UUID
    display_name: str
    interaction_count: int
    last_interaction_at: str


class InteractionSummaryResponse(BaseModel):
    entity_id: uuid.UUID
    top_partners: list[InteractionPartner]
    total_interactions: int


class TypeBreakdown(BaseModel):
    interaction_type: str
    count: int


class PairwiseStatsResponse(BaseModel):
    entity_a_id: uuid.UUID
    entity_b_id: uuid.UUID
    total_interactions: int
    type_breakdown: list[TypeBreakdown]
    first_interaction_at: str | None = None
    last_interaction_at: str | None = None


# --- Helpers ---


def _can_view_interactions(
    current_entity: Entity,
    entity_a_id: uuid.UUID,
    entity_b_id: uuid.UUID,
) -> bool:
    """Check if the current user can view these pairwise interactions.

    Users can view interactions if they are one of the two parties.
    """
    return current_entity.id in (entity_a_id, entity_b_id)


def _can_view_summary(
    current_entity: Entity,
    entity_id: uuid.UUID,
) -> bool:
    """Check if the current user can view this entity's interaction summary.

    Users can only view their own interaction summary.
    """
    return current_entity.id == entity_id


# --- Endpoints ---


@router.get(
    "/{entity_a_id}/{entity_b_id}",
    response_model=PairwiseTimelineResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_pairwise_timeline(
    entity_a_id: uuid.UUID,
    entity_b_id: uuid.UUID,
    cursor: str | None = Query(None, description="ISO datetime cursor for pagination"),
    limit: int = Query(50, ge=1, le=200),
    interaction_type: str | None = Query(None, description="Filter by interaction type"),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> PairwiseTimelineResponse:
    """Get the pairwise interaction timeline between two entities.

    Returns interactions in reverse chronological order with cursor pagination.
    Only accessible if the authenticated user is one of the two entities.
    """
    if not _can_view_interactions(current_entity, entity_a_id, entity_b_id):
        raise HTTPException(
            status_code=403,
            detail="You can only view interactions you are a party to",
        )

    # Match interactions in both directions (A->B and B->A)
    filters = [
        or_(
            (InteractionEvent.entity_a_id == entity_a_id)
            & (InteractionEvent.entity_b_id == entity_b_id),
            (InteractionEvent.entity_a_id == entity_b_id)
            & (InteractionEvent.entity_b_id == entity_a_id),
        )
    ]

    if interaction_type:
        filters.append(InteractionEvent.interaction_type == interaction_type)

    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid cursor format")
        filters.append(InteractionEvent.created_at < cursor_dt)

    query = (
        select(InteractionEvent)
        .where(*filters)
        .order_by(InteractionEvent.created_at.desc())
        .limit(limit + 1)  # fetch one extra to determine if there's a next page
    )

    result = await db.execute(query)
    rows = list(result.scalars().all())

    has_next = len(rows) > limit
    events = rows[:limit]

    next_cursor = None
    if has_next and events:
        next_cursor = events[-1].created_at.isoformat()

    return PairwiseTimelineResponse(
        events=[
            InteractionEventResponse(
                id=ev.id,
                entity_a_id=ev.entity_a_id,
                entity_b_id=ev.entity_b_id,
                interaction_type=ev.interaction_type,
                context=ev.context,
                created_at=ev.created_at.isoformat(),
            )
            for ev in events
        ],
        count=len(events),
        next_cursor=next_cursor,
    )


@router.get(
    "/{entity_id}/summary",
    response_model=InteractionSummaryResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_interaction_summary(
    entity_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=50, description="Number of top partners to return"),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> InteractionSummaryResponse:
    """Get top interaction partners for an entity with counts.

    Only accessible by the entity themselves.
    """
    if not _can_view_summary(current_entity, entity_id):
        raise HTTPException(
            status_code=403,
            detail="You can only view your own interaction summary",
        )

    # Determine the "other" entity for each interaction
    other_entity_id = case(
        (InteractionEvent.entity_a_id == entity_id, InteractionEvent.entity_b_id),
        else_=InteractionEvent.entity_a_id,
    )

    # Aggregate: count interactions per partner, get last interaction time
    partner_query = (
        select(
            other_entity_id.label("partner_id"),
            func.count().label("interaction_count"),
            func.max(InteractionEvent.created_at).label("last_interaction_at"),
        )
        .where(
            or_(
                InteractionEvent.entity_a_id == entity_id,
                InteractionEvent.entity_b_id == entity_id,
            )
        )
        .group_by(other_entity_id)
        .order_by(func.count().desc(), func.max(InteractionEvent.created_at).desc())
        .limit(limit)
    )

    partner_result = await db.execute(partner_query)
    partner_rows = partner_result.all()

    # Fetch display names for the top partners
    partner_ids = [row.partner_id for row in partner_rows]
    entities_result = await db.execute(
        select(Entity.id, Entity.display_name).where(Entity.id.in_(partner_ids))
    ) if partner_ids else None
    name_map = {}
    if entities_result:
        for eid, name in entities_result.all():
            name_map[eid] = name

    # Total interaction count
    total = await db.scalar(
        select(func.count())
        .select_from(InteractionEvent)
        .where(
            or_(
                InteractionEvent.entity_a_id == entity_id,
                InteractionEvent.entity_b_id == entity_id,
            )
        )
    ) or 0

    return InteractionSummaryResponse(
        entity_id=entity_id,
        top_partners=[
            InteractionPartner(
                entity_id=row.partner_id,
                display_name=name_map.get(row.partner_id, "Unknown"),
                interaction_count=row.interaction_count,
                last_interaction_at=row.last_interaction_at.isoformat(),
            )
            for row in partner_rows
        ],
        total_interactions=total,
    )


@router.get(
    "/{entity_a_id}/{entity_b_id}/stats",
    response_model=PairwiseStatsResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_pairwise_stats(
    entity_a_id: uuid.UUID,
    entity_b_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> PairwiseStatsResponse:
    """Get interaction statistics between two entities.

    Returns frequency, type breakdown, and first/last interaction dates.
    Only accessible if the authenticated user is one of the two entities.
    """
    if not _can_view_interactions(current_entity, entity_a_id, entity_b_id):
        raise HTTPException(
            status_code=403,
            detail="You can only view interactions you are a party to",
        )

    pair_filter = or_(
        (InteractionEvent.entity_a_id == entity_a_id)
        & (InteractionEvent.entity_b_id == entity_b_id),
        (InteractionEvent.entity_a_id == entity_b_id)
        & (InteractionEvent.entity_b_id == entity_a_id),
    )

    # Total count
    total = await db.scalar(
        select(func.count())
        .select_from(InteractionEvent)
        .where(pair_filter)
    ) or 0

    # Type breakdown
    type_query = (
        select(
            InteractionEvent.interaction_type,
            func.count().label("cnt"),
        )
        .where(pair_filter)
        .group_by(InteractionEvent.interaction_type)
        .order_by(func.count().desc())
    )
    type_result = await db.execute(type_query)
    type_rows = type_result.all()

    # First and last interaction dates
    first_at = await db.scalar(
        select(func.min(InteractionEvent.created_at)).where(pair_filter)
    )
    last_at = await db.scalar(
        select(func.max(InteractionEvent.created_at)).where(pair_filter)
    )

    return PairwiseStatsResponse(
        entity_a_id=entity_a_id,
        entity_b_id=entity_b_id,
        total_interactions=total,
        type_breakdown=[
            TypeBreakdown(interaction_type=itype, count=cnt)
            for itype, cnt in type_rows
        ],
        first_interaction_at=first_at.isoformat() if first_at else None,
        last_interaction_at=last_at.isoformat() if last_at else None,
    )
