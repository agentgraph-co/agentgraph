"""Marketplace endpoints for agent capabilities and services.

Provides listing management, browsing, and search for the
AgentGraph marketplace where agents can offer capabilities.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.api.deps import get_current_entity, get_optional_entity
from src.api.rate_limit import rate_limit_writes
from src.database import get_db
from src.models import Entity, Listing

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


# --- Schemas ---


class CreateListingRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    category: str = Field(
        ...,
        pattern="^(service|skill|integration|tool|data)$",
    )
    tags: list[str] = Field(default_factory=list)
    pricing_model: str = Field(
        ...,
        pattern="^(free|one_time|subscription)$",
    )
    price_cents: int = Field(0, ge=0)


class UpdateListingRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1, max_length=5000)
    tags: list[str] | None = None
    pricing_model: str | None = Field(
        None,
        pattern="^(free|one_time|subscription)$",
    )
    price_cents: int | None = Field(None, ge=0)
    is_active: bool | None = None


class ListingResponse(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    title: str
    description: str
    category: str
    tags: list[str]
    pricing_model: str
    price_cents: int
    is_active: bool
    is_featured: bool
    view_count: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class ListingListResponse(BaseModel):
    listings: list[ListingResponse]
    total: int


# --- Endpoints ---


@router.post(
    "", response_model=ListingResponse, status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
async def create_listing(
    body: CreateListingRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Create a new marketplace listing."""
    listing = Listing(
        id=uuid.uuid4(),
        entity_id=current_entity.id,
        title=body.title,
        description=body.description,
        category=body.category,
        tags=body.tags,
        pricing_model=body.pricing_model,
        price_cents=body.price_cents,
    )
    db.add(listing)
    await db.flush()

    return _to_response(listing)


@router.get("", response_model=ListingListResponse)
async def browse_listings(
    category: str | None = Query(None),
    pricing_model: str | None = Query(None),
    tag: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Browse marketplace listings. Filter by category, pricing, or tag."""
    query = select(Listing).where(Listing.is_active.is_(True))

    if category:
        query = query.where(Listing.category == category)
    if pricing_model:
        query = query.where(Listing.pricing_model == pricing_model)
    if tag:
        query = query.where(Listing.tags.contains([tag]))
    if search:
        pattern = f"%{search}%"
        query = query.where(
            Listing.title.ilike(pattern) | Listing.description.ilike(pattern)
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Fetch page
    query = query.order_by(
        Listing.is_featured.desc(), Listing.created_at.desc()
    ).offset(offset).limit(limit)
    result = await db.execute(query)
    listings = result.scalars().all()

    return ListingListResponse(
        listings=[_to_response(item) for item in listings],
        total=total,
    )


@router.get("/{listing_id}", response_model=ListingResponse)
async def get_listing(
    listing_id: uuid.UUID,
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific listing by ID. Increments view count."""
    listing = await db.get(Listing, listing_id)
    if listing is None or not listing.is_active:
        raise HTTPException(status_code=404, detail="Listing not found")

    # Increment view count (don't count self-views)
    if current_entity is None or current_entity.id != listing.entity_id:
        listing.view_count = (listing.view_count or 0) + 1
        await db.flush()
        await db.refresh(listing)

    return _to_response(listing)


@router.patch(
    "/{listing_id}", response_model=ListingResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def update_listing(
    listing_id: uuid.UUID,
    body: UpdateListingRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Update a listing. Only the owner can update."""
    listing = await db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")

    if listing.entity_id != current_entity.id:
        raise HTTPException(
            status_code=403, detail="Only the listing owner can update",
        )

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(listing, field, value)

    await db.flush()
    await db.refresh(listing)
    return _to_response(listing)


@router.delete("/{listing_id}", dependencies=[Depends(rate_limit_writes)])
async def delete_listing(
    listing_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Delete a listing. Only the owner can delete."""
    listing = await db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")

    if listing.entity_id != current_entity.id:
        raise HTTPException(
            status_code=403, detail="Only the listing owner can delete",
        )

    await db.delete(listing)
    await db.flush()
    return {"message": "Listing deleted"}


@router.get("/entity/{entity_id}", response_model=ListingListResponse)
async def get_entity_listings(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get all active listings for a specific entity."""
    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    result = await db.execute(
        select(Listing)
        .where(
            Listing.entity_id == entity_id,
            Listing.is_active.is_(True),
        )
        .order_by(Listing.created_at.desc())
    )
    listings = result.scalars().all()

    return ListingListResponse(
        listings=[_to_response(item) for item in listings],
        total=len(listings),
    )


def _to_response(listing: Listing) -> ListingResponse:
    return ListingResponse(
        id=listing.id,
        entity_id=listing.entity_id,
        title=listing.title,
        description=listing.description,
        category=listing.category,
        tags=listing.tags or [],
        pricing_model=listing.pricing_model,
        price_cents=listing.price_cents or 0,
        is_active=listing.is_active,
        is_featured=listing.is_featured or False,
        view_count=listing.view_count or 0,
        created_at=listing.created_at.isoformat(),
        updated_at=listing.updated_at.isoformat(),
    )
