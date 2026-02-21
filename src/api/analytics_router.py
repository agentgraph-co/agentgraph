from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.database import get_db
from src.models import AnalyticsEvent, Entity

router = APIRouter(prefix="/analytics", tags=["analytics"])

ALLOWED_EVENT_TYPES = {
    "guest_page_view",
    "guest_cta_click",
    "register_start",
    "register_complete",
    "first_action",
}

FUNNEL_ORDER = [
    "guest_page_view",
    "guest_cta_click",
    "register_start",
    "register_complete",
    "first_action",
]


# --- Schemas ---


class TrackEventRequest(BaseModel):
    event_type: str = Field(..., max_length=50)
    session_id: str = Field(..., max_length=64)
    page: str = Field(..., max_length=200)
    intent: str | None = Field(None, max_length=50)
    referrer: str | None = Field(None, max_length=500)
    metadata: dict | None = None


class FunnelStep(BaseModel):
    event_type: str
    count: int
    conversion_rate: float | None = None  # % of previous step


class ConversionSummary(BaseModel):
    period_days: int
    funnel: list[FunnelStep]
    top_pages: list[dict]
    top_intents: list[dict]
    total_events: int


class DailyConversion(BaseModel):
    period_days: int
    daily: list[dict]


# --- Public endpoint ---


@router.post(
    "/event",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_writes)],
)
async def track_event(
    body: TrackEventRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Record a conversion funnel event. No auth required."""
    if body.event_type not in ALLOWED_EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid event_type. Must be one of: {', '.join(sorted(ALLOWED_EVENT_TYPES))}",
        )

    event = AnalyticsEvent(
        event_type=body.event_type,
        session_id=body.session_id,
        page=body.page,
        intent=body.intent,
        referrer=body.referrer,
        extra_metadata=body.metadata or {},
        ip_address=request.client.host if request.client else None,
    )
    db.add(event)
    await db.flush()
    return {"status": "ok"}


# --- Admin endpoints ---


def _require_admin(entity: Entity) -> None:
    if not entity.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get(
    "/conversion",
    response_model=ConversionSummary,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_conversion_funnel(
    days: int = Query(30, ge=1, le=90),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Conversion funnel summary. Admin only."""
    _require_admin(current_entity)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Count per event_type
    type_counts_result = await db.execute(
        select(
            AnalyticsEvent.event_type,
            func.count().label("count"),
        )
        .where(AnalyticsEvent.created_at >= cutoff)
        .group_by(AnalyticsEvent.event_type)
    )
    type_counts = {row[0]: row[1] for row in type_counts_result.all()}

    # Build funnel with conversion rates
    funnel: list[FunnelStep] = []
    prev_count: int | None = None
    for event_type in FUNNEL_ORDER:
        count = type_counts.get(event_type, 0)
        rate = None
        if prev_count is not None and prev_count > 0:
            rate = round((count / prev_count) * 100, 1)
        funnel.append(FunnelStep(
            event_type=event_type,
            count=count,
            conversion_rate=rate,
        ))
        prev_count = count

    # Top pages
    top_pages_result = await db.execute(
        select(
            AnalyticsEvent.page,
            func.count().label("count"),
        )
        .where(AnalyticsEvent.created_at >= cutoff)
        .group_by(AnalyticsEvent.page)
        .order_by(func.count().desc())
        .limit(10)
    )
    top_pages = [{"page": row[0], "count": row[1]} for row in top_pages_result.all()]

    # Top intents
    top_intents_result = await db.execute(
        select(
            AnalyticsEvent.intent,
            func.count().label("count"),
        )
        .where(
            AnalyticsEvent.created_at >= cutoff,
            AnalyticsEvent.intent.isnot(None),
        )
        .group_by(AnalyticsEvent.intent)
        .order_by(func.count().desc())
        .limit(10)
    )
    top_intents = [{"intent": row[0], "count": row[1]} for row in top_intents_result.all()]

    total = sum(type_counts.values())

    return ConversionSummary(
        period_days=days,
        funnel=funnel,
        top_pages=top_pages,
        top_intents=top_intents,
        total_events=total,
    )


@router.get(
    "/conversion/daily",
    response_model=DailyConversion,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_daily_conversion(
    days: int = Query(30, ge=1, le=90),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Daily event breakdown. Admin only."""
    _require_admin(current_entity)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    _day = literal_column("'day'")
    day_col = func.date_trunc(_day, AnalyticsEvent.created_at)

    result = await db.execute(
        select(
            day_col.label("day"),
            AnalyticsEvent.event_type,
            func.count().label("count"),
        )
        .where(AnalyticsEvent.created_at >= cutoff)
        .group_by(day_col, AnalyticsEvent.event_type)
        .order_by(day_col)
    )

    # Group by date
    daily_map: dict[str, dict[str, int]] = {}
    for row in result.all():
        date_str = row[0].isoformat()[:10]
        if date_str not in daily_map:
            daily_map[date_str] = {}
        daily_map[date_str][row[1]] = row[2]

    daily = [
        {"date": date, **counts}
        for date, counts in sorted(daily_map.items())
    ]

    return DailyConversion(period_days=days, daily=daily)
