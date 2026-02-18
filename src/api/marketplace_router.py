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
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.database import get_db
from src.models import Entity, Listing, ListingReview, Transaction, TransactionStatus

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
    average_rating: float | None = None
    review_count: int = 0
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class ListingListResponse(BaseModel):
    listings: list[ListingResponse]
    total: int


class CreateListingReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    text: str | None = Field(None, max_length=5000)


class ListingReviewResponse(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID
    reviewer_entity_id: uuid.UUID
    reviewer_display_name: str = ""
    rating: int
    text: str | None = None
    created_at: str
    updated_at: str


class ListingReviewListResponse(BaseModel):
    reviews: list[ListingReviewResponse]
    total: int
    average_rating: float | None = None


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
    from src.content_filter import check_content, sanitize_html

    filter_result = check_content(body.title)
    if not filter_result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Title rejected: {', '.join(filter_result.flags)}",
        )
    filter_result = check_content(body.description)
    if not filter_result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Description rejected: {', '.join(filter_result.flags)}",
        )

    listing = Listing(
        id=uuid.uuid4(),
        entity_id=current_entity.id,
        title=sanitize_html(body.title),
        description=sanitize_html(body.description),
        category=body.category,
        tags=body.tags,
        pricing_model=body.pricing_model,
        price_cents=body.price_cents,
    )
    db.add(listing)
    await db.flush()

    # Dispatch webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "post.created", {
            "listing_id": str(listing.id),
            "title": listing.title,
            "category": listing.category,
            "seller_id": str(current_entity.id),
            "seller_name": current_entity.display_name,
        })
    except Exception:
        pass  # Best-effort

    return _to_response(listing)


@router.get(
    "", response_model=ListingListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def browse_listings(
    category: str | None = Query(None),
    pricing_model: str | None = Query(None),
    tag: str | None = Query(None),
    search: str | None = Query(None),
    sort: str = Query(
        "newest",
        pattern="^(newest|popular|price_asc|price_desc)$",
    ),
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

    # Fetch page — apply user-requested sort
    sort_clauses = {
        "newest": [Listing.is_featured.desc(), Listing.created_at.desc()],
        "popular": [Listing.is_featured.desc(), Listing.view_count.desc()],
        "price_asc": [Listing.price_cents.asc()],
        "price_desc": [Listing.price_cents.desc()],
    }
    query = query.order_by(*sort_clauses[sort]).offset(offset).limit(limit)
    result = await db.execute(query)
    listings = result.scalars().all()

    return ListingListResponse(
        listings=[_to_response(item) for item in listings],
        total=total,
    )


@router.get(
    "/featured", response_model=ListingListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_featured_listings(
    category: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get featured marketplace listings with optional category filter."""
    query = select(Listing).where(
        Listing.is_active.is_(True),
        Listing.is_featured.is_(True),
    )
    if category:
        query = query.where(Listing.category == category)

    total = await db.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0

    result = await db.execute(
        query.order_by(Listing.view_count.desc(), Listing.created_at.desc())
        .limit(limit)
    )
    listings = result.scalars().all()

    return ListingListResponse(
        listings=[_to_response(item) for item in listings],
        total=total,
    )


@router.get(
    "/categories/stats",
    dependencies=[Depends(rate_limit_reads)],
)
async def marketplace_category_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get marketplace category breakdown with listing counts."""
    result = await db.execute(
        select(
            Listing.category,
            func.count().label("listing_count"),
            func.coalesce(func.avg(Listing.price_cents), 0).label("avg_price"),
        )
        .where(Listing.is_active.is_(True))
        .group_by(Listing.category)
        .order_by(func.count().desc())
    )
    rows = result.all()

    total_active = await db.scalar(
        select(func.count()).select_from(Listing).where(
            Listing.is_active.is_(True),
        )
    ) or 0

    return {
        "total_active_listings": total_active,
        "categories": [
            {
                "category": row[0],
                "listing_count": row[1],
                "avg_price_cents": round(float(row[2])),
            }
            for row in rows
        ],
    }


@router.get("/my-listings", response_model=ListingListResponse)
async def get_my_listings(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get the authenticated user's own listings (including inactive)."""
    base = select(Listing).where(Listing.entity_id == current_entity.id)

    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0

    result = await db.execute(
        base.order_by(Listing.created_at.desc()).offset(offset).limit(limit)
    )
    listings = result.scalars().all()

    return ListingListResponse(
        listings=[_to_response(item) for item in listings],
        total=total,
    )


@router.get(
    "/{listing_id}", response_model=ListingResponse,
    dependencies=[Depends(rate_limit_reads)],
)
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

    avg_rating, review_count = await _get_listing_review_stats(db, listing_id)
    return _to_response(listing, avg_rating=avg_rating, review_count=review_count)


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

    # Content filter on text fields
    from src.content_filter import check_content, sanitize_html

    updates = body.model_dump(exclude_unset=True)
    if "title" in updates and updates["title"] is not None:
        filter_result = check_content(updates["title"])
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Title rejected: {', '.join(filter_result.flags)}",
            )
        updates["title"] = sanitize_html(updates["title"])
    if "description" in updates and updates["description"] is not None:
        filter_result = check_content(updates["description"])
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Description rejected: {', '.join(filter_result.flags)}",
            )
        updates["description"] = sanitize_html(updates["description"])

    for field, value in updates.items():
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


@router.get(
    "/entity/{entity_id}", response_model=ListingListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
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


def _to_response(
    listing: Listing,
    avg_rating: float | None = None,
    review_count: int = 0,
) -> ListingResponse:
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
        average_rating=avg_rating,
        review_count=review_count,
        created_at=listing.created_at.isoformat(),
        updated_at=listing.updated_at.isoformat(),
    )


async def _get_listing_review_stats(
    db: AsyncSession, listing_id: uuid.UUID,
) -> tuple[float | None, int]:
    """Return (average_rating, review_count) for a listing."""
    result = await db.execute(
        select(
            func.avg(ListingReview.rating),
            func.count(ListingReview.id),
        ).where(ListingReview.listing_id == listing_id)
    )
    row = result.one()
    avg = round(float(row[0]), 2) if row[0] is not None else None
    return avg, row[1]


# --- Listing Review Endpoints ---


@router.post(
    "/{listing_id}/reviews",
    response_model=ListingReviewResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
async def create_listing_review(
    listing_id: uuid.UUID,
    body: CreateListingReviewRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Create or update a review for a marketplace listing."""
    listing = await db.get(Listing, listing_id)
    if listing is None or not listing.is_active:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.entity_id == current_entity.id:
        raise HTTPException(
            status_code=400, detail="Cannot review your own listing",
        )

    # Content filter + sanitization
    if body.text:
        from src.content_filter import check_content
        from src.content_filter import sanitize_html as _sanitize

        filter_result = check_content(body.text)
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Content rejected: {', '.join(filter_result.flags)}",
            )
        body.text = _sanitize(body.text)

    # Upsert: update if already reviewed
    existing = await db.scalar(
        select(ListingReview).where(
            ListingReview.listing_id == listing_id,
            ListingReview.reviewer_entity_id == current_entity.id,
        )
    )

    if existing:
        existing.rating = body.rating
        existing.text = body.text
        await db.flush()
        await db.refresh(existing)
        return ListingReviewResponse(
            id=existing.id,
            listing_id=listing_id,
            reviewer_entity_id=current_entity.id,
            reviewer_display_name=current_entity.display_name,
            rating=existing.rating,
            text=existing.text,
            created_at=existing.created_at.isoformat(),
            updated_at=existing.updated_at.isoformat(),
        )

    review = ListingReview(
        id=uuid.uuid4(),
        listing_id=listing_id,
        reviewer_entity_id=current_entity.id,
        rating=body.rating,
        text=body.text,
    )
    db.add(review)
    await db.flush()

    # Notify listing owner
    from src.api.notification_router import create_notification

    await create_notification(
        db,
        entity_id=listing.entity_id,
        kind="review",
        title="New listing review",
        body=(
            f"{current_entity.display_name} rated your listing "
            f"'{listing.title}' {body.rating}/5"
        ),
        reference_id=str(review.id),
    )

    return ListingReviewResponse(
        id=review.id,
        listing_id=listing_id,
        reviewer_entity_id=current_entity.id,
        reviewer_display_name=current_entity.display_name,
        rating=review.rating,
        text=review.text,
        created_at=review.created_at.isoformat(),
        updated_at=review.updated_at.isoformat(),
    )


@router.get(
    "/{listing_id}/reviews",
    response_model=ListingReviewListResponse,
)
async def list_listing_reviews(
    listing_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List reviews for a marketplace listing."""
    listing = await db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")

    avg_rating, total = await _get_listing_review_stats(db, listing_id)

    result = await db.execute(
        select(ListingReview, Entity.display_name)
        .join(Entity, ListingReview.reviewer_entity_id == Entity.id)
        .where(ListingReview.listing_id == listing_id)
        .order_by(ListingReview.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    return ListingReviewListResponse(
        reviews=[
            ListingReviewResponse(
                id=r.id,
                listing_id=r.listing_id,
                reviewer_entity_id=r.reviewer_entity_id,
                reviewer_display_name=name,
                rating=r.rating,
                text=r.text,
                created_at=r.created_at.isoformat(),
                updated_at=r.updated_at.isoformat(),
            )
            for r, name in result.all()
        ],
        total=total,
        average_rating=avg_rating,
    )


@router.delete(
    "/{listing_id}/reviews",
    dependencies=[Depends(rate_limit_writes)],
)
async def delete_listing_review(
    listing_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Delete your review of a listing."""
    review = await db.scalar(
        select(ListingReview).where(
            ListingReview.listing_id == listing_id,
            ListingReview.reviewer_entity_id == current_entity.id,
        )
    )
    if review is None:
        raise HTTPException(
            status_code=404, detail="Review not found",
        )
    await db.delete(review)
    await db.flush()
    return {"message": "Review deleted"}


# --- Purchase / Transaction Endpoints ---


class PurchaseRequest(BaseModel):
    notes: str | None = Field(None, max_length=500)


class TransactionResponse(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID | None
    buyer_entity_id: uuid.UUID
    seller_entity_id: uuid.UUID
    amount_cents: int
    status: str
    listing_title: str
    listing_category: str
    notes: str | None = None
    completed_at: str | None = None
    created_at: str


class TransactionListResponse(BaseModel):
    transactions: list[TransactionResponse]
    total: int


def _txn_response(txn: Transaction) -> TransactionResponse:
    return TransactionResponse(
        id=txn.id,
        listing_id=txn.listing_id,
        buyer_entity_id=txn.buyer_entity_id,
        seller_entity_id=txn.seller_entity_id,
        amount_cents=txn.amount_cents,
        status=txn.status.value,
        listing_title=txn.listing_title,
        listing_category=txn.listing_category,
        notes=txn.notes,
        completed_at=txn.completed_at.isoformat() if txn.completed_at else None,
        created_at=txn.created_at.isoformat(),
    )


@router.post(
    "/{listing_id}/purchase",
    response_model=TransactionResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
async def purchase_listing(
    listing_id: uuid.UUID,
    body: PurchaseRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Purchase a marketplace listing. Creates a transaction record."""
    listing = await db.get(Listing, listing_id)
    if listing is None or not listing.is_active:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.entity_id == current_entity.id:
        raise HTTPException(
            status_code=400, detail="Cannot purchase your own listing",
        )

    # For free listings, auto-complete
    is_free = listing.pricing_model == "free" or listing.price_cents == 0

    from datetime import datetime, timezone
    txn = Transaction(
        id=uuid.uuid4(),
        listing_id=listing.id,
        buyer_entity_id=current_entity.id,
        seller_entity_id=listing.entity_id,
        amount_cents=listing.price_cents or 0,
        status=TransactionStatus.COMPLETED if is_free else TransactionStatus.PENDING,
        listing_title=listing.title,
        listing_category=listing.category,
        notes=body.notes,
        completed_at=datetime.now(timezone.utc) if is_free else None,
    )
    db.add(txn)
    await db.flush()

    # Notify the seller
    from src.api.notification_router import create_notification

    await create_notification(
        db,
        entity_id=listing.entity_id,
        kind="review",
        title="New purchase",
        body=(
            f"{current_entity.display_name} purchased your listing "
            f"'{listing.title}'"
        ),
        reference_id=str(txn.id),
    )

    # Broadcast via WebSocket
    try:
        from src.ws import manager

        await manager.send_to_entity(str(listing.entity_id), "marketplace", {
            "type": "purchase",
            "transaction_id": str(txn.id),
            "buyer_id": str(current_entity.id),
            "buyer_name": current_entity.display_name,
            "listing_title": listing.title,
        })
    except Exception:
        pass  # Best-effort

    # Dispatch webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "entity.messaged", {
            "event": "marketplace.purchased",
            "transaction_id": str(txn.id),
            "listing_id": str(listing.id),
            "listing_title": listing.title,
            "buyer_id": str(current_entity.id),
            "seller_id": str(listing.entity_id),
            "amount_cents": txn.amount_cents,
        })
    except Exception:
        pass  # Best-effort

    return _txn_response(txn)


@router.get(
    "/purchases/history",
    response_model=TransactionListResponse,
)
async def get_purchase_history(
    role: str = Query("buyer", pattern="^(buyer|seller|all)$"),
    status: str | None = Query(None, pattern="^(pending|completed|refunded|cancelled)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get transaction history for the current entity."""
    from sqlalchemy import or_

    if role == "buyer":
        base_filter = Transaction.buyer_entity_id == current_entity.id
    elif role == "seller":
        base_filter = Transaction.seller_entity_id == current_entity.id
    else:
        base_filter = or_(
            Transaction.buyer_entity_id == current_entity.id,
            Transaction.seller_entity_id == current_entity.id,
        )

    query = select(Transaction).where(base_filter)
    count_query = select(func.count()).select_from(Transaction).where(base_filter)

    if status:
        txn_status = TransactionStatus(status)
        query = query.where(Transaction.status == txn_status)
        count_query = count_query.where(Transaction.status == txn_status)

    total = await db.scalar(count_query) or 0

    result = await db.execute(
        query.order_by(Transaction.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    transactions = result.scalars().all()

    return TransactionListResponse(
        transactions=[_txn_response(t) for t in transactions],
        total=total,
    )


@router.get(
    "/purchases/{transaction_id}",
    response_model=TransactionResponse,
)
async def get_transaction(
    transaction_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific transaction (must be buyer or seller)."""
    txn = await db.get(Transaction, transaction_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.buyer_entity_id != current_entity.id and txn.seller_entity_id != current_entity.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this transaction")
    return _txn_response(txn)


@router.patch(
    "/purchases/{transaction_id}/cancel",
    response_model=TransactionResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def cancel_transaction(
    transaction_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a pending transaction. Only the buyer can cancel."""
    txn = await db.get(Transaction, transaction_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.buyer_entity_id != current_entity.id:
        raise HTTPException(status_code=403, detail="Only the buyer can cancel")
    if txn.status != TransactionStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel a transaction with status '{txn.status.value}'",
        )

    txn.status = TransactionStatus.CANCELLED

    from src.audit import log_action

    await log_action(
        db,
        action="transaction.cancel",
        entity_id=current_entity.id,
        resource_type="transaction",
        resource_id=txn.id,
        details={"listing_id": str(txn.listing_id), "amount_cents": txn.amount_cents},
    )
    await db.flush()

    # Dispatch webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "entity.messaged", {
            "event": "marketplace.cancelled",
            "transaction_id": str(txn.id),
            "listing_id": str(txn.listing_id),
            "buyer_id": str(txn.buyer_entity_id),
            "seller_id": str(txn.seller_entity_id),
        })
    except Exception:
        pass  # Best-effort

    return _txn_response(txn)


@router.patch(
    "/purchases/{transaction_id}/refund",
    response_model=TransactionResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def refund_transaction(
    transaction_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Refund a completed transaction. Only the seller can refund."""
    txn = await db.get(Transaction, transaction_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.seller_entity_id != current_entity.id:
        raise HTTPException(status_code=403, detail="Only the seller can refund")
    if txn.status != TransactionStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot refund a transaction with status '{txn.status.value}'",
        )

    txn.status = TransactionStatus.REFUNDED

    from src.audit import log_action

    await log_action(
        db,
        action="transaction.refund",
        entity_id=current_entity.id,
        resource_type="transaction",
        resource_id=txn.id,
        details={"listing_id": str(txn.listing_id), "amount_cents": txn.amount_cents},
    )
    await db.flush()

    # Dispatch webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "entity.messaged", {
            "event": "marketplace.refunded",
            "transaction_id": str(txn.id),
            "listing_id": str(txn.listing_id),
            "buyer_id": str(txn.buyer_entity_id),
            "seller_id": str(txn.seller_entity_id),
            "amount_cents": txn.amount_cents,
        })
    except Exception:
        pass  # Best-effort

    return _txn_response(txn)
