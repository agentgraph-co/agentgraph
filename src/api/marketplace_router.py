"""Marketplace endpoints for agent capabilities and services.

Provides listing management, browsing, and search for the
AgentGraph marketplace where agents can offer capabilities.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src import cache
from src.api.deps import get_current_entity, get_optional_entity, require_scope
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.api.trust_gate import require_trust
from src.config import settings
from src.database import get_db
from src.models import (
    Entity,
    EvolutionRecord,
    Listing,
    ListingReview,
    Transaction,
    TransactionStatus,
    TrustScore,
)
from src.ssrf import validate_url
from src.utils import like_pattern

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


# --- Schemas ---


class CreateListingRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    category: str = Field(
        ...,
        pattern="^(service|skill|integration|tool|data|capability)$",
    )
    tags: list[str] = Field(default_factory=list, max_length=10)
    pricing_model: str = Field(
        ...,
        pattern="^(free|one_time|subscription)$",
    )
    price_cents: int = Field(0, ge=0)


class UpdateListingRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1, max_length=5000)
    tags: list[str] | None = Field(None, max_length=10)
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
    source_evolution_record_id: uuid.UUID | None = None
    created_at: str
    updated_at: str
    # Seller trust context (populated in listing detail when applicable)
    seller_trust_score: float | None = None
    seller_contextual_trust_score: float | None = None
    seller_trust_context: str | None = None

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


# --- Stripe Connect Schemas ---


class ConnectOnboardRequest(BaseModel):
    return_url: str = Field(..., min_length=1, max_length=2000)
    refresh_url: str = Field(..., min_length=1, max_length=2000)

    @field_validator("return_url")
    @classmethod
    def check_return_url(cls, v: str) -> str:
        return validate_url(v, field_name="return_url")

    @field_validator("refresh_url")
    @classmethod
    def check_refresh_url(cls, v: str) -> str:
        return validate_url(v, field_name="refresh_url")


class ConnectOnboardResponse(BaseModel):
    onboarding_url: str
    account_id: str


class ConnectStatusResponse(BaseModel):
    charges_enabled: bool
    payouts_enabled: bool
    details_submitted: bool


# --- Stripe Connect Endpoints ---


@router.post(
    "/connect/onboard",
    response_model=ConnectOnboardResponse,
    dependencies=[Depends(rate_limit_writes), require_scope("marketplace:payments")],
)
async def connect_onboard(
    body: ConnectOnboardRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Connect Express account and return the onboarding URL.

    If the seller already has a Stripe account, generates a new onboarding
    link for the existing account (to resume incomplete onboarding).
    """
    from src.payments.stripe_service import create_connect_account, create_onboarding_link

    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=503,
            detail="Payment processing is not configured",
        )

    account_id = current_entity.stripe_account_id

    if not account_id:
        account_id = create_connect_account(
            entity_id=str(current_entity.id),
            email=current_entity.email or f"{current_entity.id}@agentgraph.io",
        )
        current_entity.stripe_account_id = account_id
        await db.flush()
        await db.refresh(current_entity)

    onboarding_url = create_onboarding_link(
        account_id=account_id,
        return_url=body.return_url,
        refresh_url=body.refresh_url,
    )

    from src.audit import log_action

    await log_action(
        db,
        action="marketplace.connect_onboard",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=current_entity.id,
        details={"stripe_account_id": account_id},
    )

    return ConnectOnboardResponse(
        onboarding_url=onboarding_url,
        account_id=account_id,
    )


@router.get(
    "/connect/status",
    response_model=ConnectStatusResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def connect_status(
    current_entity: Entity = Depends(get_current_entity),
):
    """Get the Stripe Connect account status for the current seller."""
    from src.payments.stripe_service import get_account_status

    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=503,
            detail="Payment processing is not configured",
        )

    if not current_entity.stripe_account_id:
        raise HTTPException(
            status_code=404,
            detail="No Stripe account found. Set up payments first.",
        )

    status_info = get_account_status(current_entity.stripe_account_id)
    return ConnectStatusResponse(**status_info)


# --- Endpoints ---


@router.post(
    "", response_model=ListingResponse, status_code=201,
    dependencies=[
        Depends(rate_limit_writes),
        require_scope("marketplace:list"),
        Depends(require_trust("create_listing")),
    ],
)
async def create_listing(
    body: CreateListingRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Create a new marketplace listing."""
    # Provisional agents cannot create marketplace listings
    if getattr(current_entity, "is_provisional", False):
        raise HTTPException(
            status_code=403,
            detail="Provisional agents cannot create marketplace listings.",
        )

    from src.content_filter import check_content, sanitize_html, sanitize_text

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
        title=sanitize_text(body.title),
        description=sanitize_html(body.description),
        category=body.category,
        tags=body.tags,
        pricing_model=body.pricing_model,
        price_cents=body.price_cents,
    )
    db.add(listing)
    await db.flush()

    from src.audit import log_action

    await log_action(
        db,
        action="marketplace.listing_create",
        entity_id=current_entity.id,
        resource_type="listing",
        resource_id=listing.id,
        details={"title": listing.title, "category": listing.category},
    )

    # Dispatch webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "marketplace.listing_created", {
            "listing_id": str(listing.id),
            "title": listing.title,
            "category": listing.category,
            "seller_id": str(current_entity.id),
            "seller_name": current_entity.display_name,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # Broadcast via WebSocket
    try:
        from src.ws import manager

        await manager.send_to_entity(str(current_entity.id), "marketplace", {
            "type": "listing_created",
            "listing_id": str(listing.id),
            "title": listing.title,
            "category": listing.category,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

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
        pattern = like_pattern(search)
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


@router.get(
    "/my-listings", response_model=ListingListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
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


# --- Capability Marketplace Schemas ---


class CreateCapabilityListingRequest(BaseModel):
    evolution_record_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=10)
    pricing_model: str = Field(
        ...,
        pattern="^(free|one_time|subscription)$",
    )
    price_cents: int = Field(0, ge=0)
    license_type: str = Field(
        "commercial",
        pattern="^(open|commercial|attribution)$",
    )


class AdoptCapabilityRequest(BaseModel):
    agent_id: uuid.UUID  # buyer's agent to receive the capability


# --- Capability Marketplace Endpoints ---


@router.post(
    "/capabilities",
    response_model=ListingResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
async def create_capability_listing(
    body: CreateCapabilityListingRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Create a capability listing linked to an evolution record."""
    from src.content_filter import check_content, sanitize_html, sanitize_text
    from src.marketplace.capability_sharing import (
        create_capability_listing as _create_cap_listing,
    )

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

    try:
        listing = await _create_cap_listing(
            db=db,
            entity_id=current_entity.id,
            evolution_record_id=body.evolution_record_id,
            title=sanitize_text(body.title),
            description=sanitize_html(body.description),
            tags=body.tags,
            pricing_model=body.pricing_model,
            price_cents=body.price_cents,
            license_type=body.license_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await db.flush()

    from src.audit import log_action

    await log_action(
        db,
        action="marketplace.capability_listing_create",
        entity_id=current_entity.id,
        resource_type="listing",
        resource_id=listing.id,
        details={
            "title": listing.title,
            "evolution_record_id": str(body.evolution_record_id),
        },
    )

    return _to_response(listing)


@router.get(
    "/capabilities/{listing_id}/package",
    dependencies=[Depends(rate_limit_reads)],
)
async def get_capability_package(
    listing_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get capability package details including evolution record info."""
    listing = await db.get(Listing, listing_id)
    if listing is None or not listing.is_active:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.category != "capability" or listing.source_evolution_record_id is None:
        raise HTTPException(
            status_code=400, detail="Listing is not a capability package",
        )

    record = await db.get(EvolutionRecord, listing.source_evolution_record_id)
    if record is None:
        raise HTTPException(
            status_code=404, detail="Source evolution record not found",
        )

    # Get source agent info
    source_agent = await db.get(Entity, record.entity_id)

    return {
        "listing": _to_response(listing),
        "evolution_record": {
            "id": str(record.id),
            "entity_id": str(record.entity_id),
            "version": record.version,
            "change_type": record.change_type,
            "change_summary": record.change_summary,
            "capabilities_snapshot": record.capabilities_snapshot or [],
            "license_type": record.license_type,
            "risk_tier": record.risk_tier or 1,
            "created_at": record.created_at.isoformat(),
        },
        "source_agent": {
            "id": str(source_agent.id) if source_agent else None,
            "display_name": source_agent.display_name if source_agent else None,
        },
    }


@router.post(
    "/capabilities/{listing_id}/adopt",
    status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
async def adopt_capability(
    listing_id: uuid.UUID,
    body: AdoptCapabilityRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Purchase capability and auto-fork to buyer's agent.

    For free listings: auto-adopt immediately.
    For paid listings: create transaction and adopt on completion.
    """
    from src.marketplace.capability_sharing import adopt_capability as _adopt

    listing = await db.get(Listing, listing_id)
    if listing is None or not listing.is_active:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.category != "capability" or listing.source_evolution_record_id is None:
        raise HTTPException(
            status_code=400, detail="Listing is not a capability package",
        )
    if listing.entity_id == current_entity.id:
        raise HTTPException(
            status_code=400, detail="Cannot adopt your own capability",
        )

    is_free = listing.pricing_model == "free" or listing.price_cents == 0

    if not is_free:
        # For paid listings: create a pending transaction, then adopt
        from datetime import datetime, timezone

        from src.config import settings

        if not settings.stripe_secret_key:
            raise HTTPException(
                status_code=503,
                detail="Payment processing is not configured",
            )

        seller = await db.get(Entity, listing.entity_id)
        if not seller or not seller.stripe_account_id:
            raise HTTPException(
                status_code=400,
                detail="Seller has not set up payment processing",
            )

        from src.payments.stripe_service import get_account_status

        seller_status = get_account_status(seller.stripe_account_id)
        if not seller_status["charges_enabled"]:
            raise HTTPException(
                status_code=400,
                detail="Seller payment account is not fully activated",
            )

        platform_fee_cents = (
            (listing.price_cents or 0) * settings.stripe_platform_fee_percent // 100
        )

        from src.payments.stripe_service import create_payment_intent

        intent_data = create_payment_intent(
            amount_cents=listing.price_cents or 0,
            seller_account_id=seller.stripe_account_id,
            platform_fee_cents=platform_fee_cents,
            metadata={
                "listing_id": str(listing.id),
                "buyer_entity_id": str(current_entity.id),
                "seller_entity_id": str(listing.entity_id),
                "capability_adopt": "true",
                "agent_id": str(body.agent_id),
            },
        )

        txn = Transaction(
            id=uuid.uuid4(),
            listing_id=listing.id,
            buyer_entity_id=current_entity.id,
            seller_entity_id=listing.entity_id,
            amount_cents=listing.price_cents or 0,
            status=TransactionStatus.PENDING,
            listing_title=listing.title,
            listing_category=listing.category,
            notes=f"Capability adoption for agent {body.agent_id}",
            stripe_payment_intent_id=intent_data["payment_intent_id"],
            platform_fee_cents=platform_fee_cents,
        )
        db.add(txn)
        await db.flush()

        return {
            "status": "payment_required",
            "transaction_id": str(txn.id),
            "client_secret": intent_data["client_secret"],
            "amount_cents": listing.price_cents or 0,
            "message": "Complete payment to adopt capability.",
        }

    # Free listing: adopt immediately
    try:
        fork_record = await _adopt(
            db=db,
            listing=listing,
            buyer_agent_id=body.agent_id,
            buyer_entity_id=current_entity.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Create a completed transaction record for free adoption
    from datetime import datetime, timezone

    txn = Transaction(
        id=uuid.uuid4(),
        listing_id=listing.id,
        buyer_entity_id=current_entity.id,
        seller_entity_id=listing.entity_id,
        amount_cents=0,
        status=TransactionStatus.COMPLETED,
        listing_title=listing.title,
        listing_category=listing.category,
        notes=f"Free capability adoption for agent {body.agent_id}",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(txn)
    await db.flush()

    from src.audit import log_action

    await log_action(
        db,
        action="marketplace.capability_adopt",
        entity_id=current_entity.id,
        resource_type="evolution_record",
        resource_id=fork_record.id,
        details={
            "listing_id": str(listing.id),
            "agent_id": str(body.agent_id),
            "version": fork_record.version,
        },
    )

    # Notify the seller
    try:
        from src.api.notification_router import create_notification

        await create_notification(
            db,
            entity_id=listing.entity_id,
            kind="review",
            title="Capability adopted",
            body=(
                f"{current_entity.display_name} adopted capability "
                f"from your listing '{listing.title}'"
            ),
            reference_id=str(fork_record.id),
        )
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # Broadcast via WebSocket
    try:
        from src.ws import manager

        await manager.send_to_entity(str(listing.entity_id), "marketplace", {
            "type": "capability_adopted",
            "listing_id": str(listing.id),
            "buyer_id": str(current_entity.id),
            "buyer_name": current_entity.display_name,
            "listing_title": listing.title,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return {
        "status": "adopted",
        "evolution_record_id": str(fork_record.id),
        "version": fork_record.version,
        "capabilities": fork_record.capabilities_snapshot or [],
        "transaction_id": str(txn.id),
    }


@router.get(
    "/{listing_id}", response_model=ListingResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_listing(
    listing_id: uuid.UUID,
    current_entity: Entity | None = Depends(get_optional_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific listing by ID. Increments view count.

    When the listing's category maps to a trust context, the response
    includes the seller's contextual trust score for that capability
    alongside their overall trust score.
    """
    listing = await db.get(Listing, listing_id)
    if listing is None or not listing.is_active:
        raise HTTPException(status_code=404, detail="Listing not found")

    # Increment view count atomically (don't count self-views)
    if current_entity is None or current_entity.id != listing.entity_id:
        from sqlalchemy import update

        await db.execute(
            update(Listing)
            .where(Listing.id == listing_id)
            .values(view_count=func.coalesce(Listing.view_count, 0) + 1)
        )
        await db.flush()
        await db.refresh(listing)

    # Try cache (excludes view_count which is always fresh from the DB)
    cached = await cache.get(f"listing:{listing_id}")
    if cached is not None:
        # Update view_count from fresh DB read
        cached["view_count"] = listing.view_count or 0
        return ListingResponse(**cached)

    avg_rating, review_count = await _get_listing_review_stats(db, listing_id)
    response = _to_response(listing, avg_rating=avg_rating, review_count=review_count)

    # Surface seller's contextual trust score for the listing's category
    seller_ts = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == listing.entity_id)
    )
    if seller_ts:
        response.seller_trust_score = seller_ts.score
        # Use listing category as the trust context
        ctx = listing.category
        contextual_scores = seller_ts.contextual_scores or {}
        if ctx and ctx in contextual_scores:
            response.seller_contextual_trust_score = contextual_scores[ctx]
            response.seller_trust_context = ctx

    await cache.set(
        f"listing:{listing_id}",
        response.model_dump(mode="json"),
        ttl=cache.TTL_SHORT,
    )

    return response


@router.patch(
    "/{listing_id}", response_model=ListingResponse,
    dependencies=[Depends(rate_limit_writes), require_scope("marketplace:list")],
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
    from src.content_filter import check_content, sanitize_html, sanitize_text

    updates = body.model_dump(exclude_unset=True)
    if "title" in updates and updates["title"] is not None:
        filter_result = check_content(updates["title"])
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Title rejected: {', '.join(filter_result.flags)}",
            )
        updates["title"] = sanitize_text(updates["title"])
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

    from src.audit import log_action

    await log_action(
        db,
        action="marketplace.listing_update",
        entity_id=current_entity.id,
        resource_type="listing",
        resource_id=listing_id,
        details={"fields": list(updates.keys())},
    )

    await cache.invalidate(f"listing:{listing_id}")

    return _to_response(listing)


@router.delete(
    "/{listing_id}",
    dependencies=[Depends(rate_limit_writes), require_scope("marketplace:list")],
)
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

    from src.audit import log_action

    await log_action(
        db,
        action="marketplace.listing_delete",
        entity_id=current_entity.id,
        resource_type="listing",
        resource_id=listing_id,
        details={"title": listing.title},
    )

    await cache.invalidate(f"listing:{listing_id}")

    return {"message": "Listing deleted"}


@router.get(
    "/entity/{entity_id}", response_model=ListingListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_entity_listings(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Get all active listings for a specific entity."""
    entity = await db.get(Entity, entity_id)
    if entity is None or not entity.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")

    base = (
        select(Listing)
        .where(
            Listing.entity_id == entity_id,
            Listing.is_active.is_(True),
        )
    )
    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar() or 0

    result = await db.execute(
        base.order_by(Listing.created_at.desc()).limit(limit).offset(offset)
    )
    listings = result.scalars().all()

    return ListingListResponse(
        listings=[_to_response(item) for item in listings],
        total=total,
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
        source_evolution_record_id=listing.source_evolution_record_id,
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
        )
        .join(Entity, ListingReview.reviewer_entity_id == Entity.id)
        .where(
            ListingReview.listing_id == listing_id,
            Entity.is_active.is_(True),
        )
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

        # Invalidate listing cache so review stats refresh
        await cache.invalidate(f"listing:{listing_id}")

        from src.audit import log_action

        await log_action(
            db,
            action="marketplace.review_update",
            entity_id=current_entity.id,
            resource_type="listing_review",
            resource_id=existing.id,
            details={"listing_id": str(listing_id), "rating": body.rating},
        )

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

    # Invalidate listing cache so review stats refresh
    await cache.invalidate(f"listing:{listing_id}")

    from src.audit import log_action

    await log_action(
        db,
        action="marketplace.review_create",
        entity_id=current_entity.id,
        resource_type="listing_review",
        resource_id=review.id,
        details={"listing_id": str(listing_id), "rating": body.rating},
    )

    # Record pairwise interaction
    try:
        from src.interactions import record_interaction

        await record_interaction(
            db,
            entity_a_id=current_entity.id,
            entity_b_id=listing.entity_id,
            interaction_type="review",
            context={
                "reference_id": str(review.id),
                "listing_id": str(listing_id),
                "rating": body.rating,
            },
        )
    except Exception:
        logger.warning("Best-effort interaction recording failed", exc_info=True)

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
    dependencies=[Depends(rate_limit_reads)],
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
        .where(
            ListingReview.listing_id == listing_id,
            Entity.is_active.is_(True),
        )
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

    from src.audit import log_action

    await log_action(
        db,
        action="marketplace.review_delete",
        entity_id=current_entity.id,
        resource_type="listing_review",
        resource_id=review.id,
        details={"listing_id": str(listing_id)},
    )

    await db.delete(review)
    await db.flush()

    # Invalidate listing cache so review stats refresh
    await cache.invalidate(f"listing:{listing_id}")

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
    platform_fee_cents: int | None = None
    client_secret: str | None = None
    completed_at: str | None = None
    created_at: str


class TransactionListResponse(BaseModel):
    transactions: list[TransactionResponse]
    total: int


def _txn_response(
    txn: Transaction, client_secret: str | None = None,
) -> TransactionResponse:
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
        platform_fee_cents=txn.platform_fee_cents,
        client_secret=client_secret,
        completed_at=txn.completed_at.isoformat() if txn.completed_at else None,
        created_at=txn.created_at.isoformat(),
    )


@router.post(
    "/{listing_id}/purchase",
    response_model=TransactionResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_writes), require_scope("marketplace:purchase")],
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

    # Content filter on notes
    if body.notes:
        from src.content_filter import check_content, sanitize_html

        filter_result = check_content(body.notes)
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Purchase notes rejected: {', '.join(filter_result.flags)}",
            )
        body.notes = sanitize_html(body.notes)

    # For free listings, auto-complete
    is_free = listing.pricing_model == "free" or listing.price_cents == 0

    # Check for duplicate pending/escrow purchase
    from sqlalchemy import or_ as _or

    existing_pending = await db.scalar(
        select(Transaction).where(
            Transaction.listing_id == listing.id,
            Transaction.buyer_entity_id == current_entity.id,
            _or(
                Transaction.status == TransactionStatus.PENDING,
                Transaction.status == TransactionStatus.ESCROW,
            ),
        )
    )
    if existing_pending:
        raise HTTPException(
            status_code=400,
            detail="You already have a pending purchase for this listing",
        )

    # For paid listings, validate seller Stripe account and create PaymentIntent
    client_secret = None
    stripe_payment_intent_id = None
    platform_fee_cents = None

    if not is_free:
        if not settings.stripe_secret_key:
            raise HTTPException(
                status_code=503,
                detail="Payment processing is not configured",
            )

        # Look up the seller entity to check Stripe account
        seller = await db.get(Entity, listing.entity_id)
        if not seller or not seller.stripe_account_id:
            raise HTTPException(
                status_code=400,
                detail="Seller has not set up payment processing",
            )

        # Verify seller can accept charges
        from src.payments.stripe_service import get_account_status

        seller_status = get_account_status(seller.stripe_account_id)
        if not seller_status["charges_enabled"]:
            raise HTTPException(
                status_code=400,
                detail="Seller payment account is not fully activated",
            )

        # Calculate platform fee
        platform_fee_cents = (
            (listing.price_cents or 0) * settings.stripe_platform_fee_percent // 100
        )

        # Create PaymentIntent
        from src.payments.stripe_service import create_payment_intent

        intent_data = create_payment_intent(
            amount_cents=listing.price_cents or 0,
            seller_account_id=seller.stripe_account_id,
            platform_fee_cents=platform_fee_cents,
            metadata={
                "listing_id": str(listing.id),
                "buyer_entity_id": str(current_entity.id),
                "seller_entity_id": str(listing.entity_id),
            },
        )
        client_secret = intent_data["client_secret"]
        stripe_payment_intent_id = intent_data["payment_intent_id"]

    from datetime import datetime, timezone
    txn = Transaction(
        id=uuid.uuid4(),
        listing_id=listing.id,
        buyer_entity_id=current_entity.id,
        seller_entity_id=listing.entity_id,
        amount_cents=listing.price_cents or 0,
        status=TransactionStatus.COMPLETED if is_free else TransactionStatus.ESCROW,
        listing_title=listing.title,
        listing_category=listing.category,
        notes=body.notes,
        stripe_payment_intent_id=stripe_payment_intent_id,
        platform_fee_cents=platform_fee_cents,
        completed_at=datetime.now(timezone.utc) if is_free else None,
    )
    db.add(txn)
    await db.flush()

    from src.audit import log_action

    await log_action(
        db,
        action="marketplace.purchase",
        entity_id=current_entity.id,
        resource_type="transaction",
        resource_id=txn.id,
        details={
            "listing_id": str(listing.id),
            "amount_cents": txn.amount_cents,
            "seller_id": str(listing.entity_id),
            "stripe_payment_intent_id": stripe_payment_intent_id,
        },
    )

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
        logger.warning("Best-effort side effect failed", exc_info=True)

    # Dispatch webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "marketplace.purchased", {
            "transaction_id": str(txn.id),
            "listing_id": str(listing.id),
            "listing_title": listing.title,
            "buyer_id": str(current_entity.id),
            "seller_id": str(listing.entity_id),
            "amount_cents": txn.amount_cents,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return _txn_response(txn, client_secret=client_secret)


@router.get(
    "/purchases/history",
    response_model=TransactionListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_purchase_history(
    role: str = Query("buyer", pattern="^(buyer|seller|all)$"),
    status: str | None = Query(
        None, pattern="^(pending|escrow|completed|disputed|refunded|cancelled)$",
    ),
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
    dependencies=[Depends(rate_limit_reads)],
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


@router.post(
    "/purchases/{transaction_id}/confirm",
    response_model=TransactionResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def confirm_purchase(
    transaction_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Buyer confirms receipt, triggering capture of escrowed funds."""
    txn = await db.scalar(
        select(Transaction)
        .where(Transaction.id == transaction_id)
        .with_for_update()
    )
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.buyer_entity_id != current_entity.id:
        raise HTTPException(status_code=403, detail="Only the buyer can confirm")
    if txn.status != TransactionStatus.ESCROW:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot confirm a transaction with status '{txn.status.value}'",
        )

    from src.payments.escrow import release_escrow

    await release_escrow(db, txn, current_entity.id)

    # Notify the seller
    from src.api.notification_router import create_notification

    await create_notification(
        db,
        entity_id=txn.seller_entity_id,
        kind="review",
        title="Purchase confirmed",
        body=(
            f"Buyer confirmed receipt for '{txn.listing_title}'. "
            f"Funds have been released."
        ),
        reference_id=str(txn.id),
    )

    # Broadcast via WebSocket
    try:
        from src.ws import manager

        await manager.send_to_entity(str(txn.seller_entity_id), "marketplace", {
            "type": "purchase_confirmed",
            "transaction_id": str(txn.id),
            "buyer_id": str(txn.buyer_entity_id),
            "listing_title": txn.listing_title,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # Dispatch webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "marketplace.purchase_confirmed", {
            "transaction_id": str(txn.id),
            "listing_id": str(txn.listing_id),
            "buyer_id": str(txn.buyer_entity_id),
            "seller_id": str(txn.seller_entity_id),
            "amount_cents": txn.amount_cents,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

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
    txn = await db.scalar(
        select(Transaction)
        .where(Transaction.id == transaction_id)
        .with_for_update()
    )
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.buyer_entity_id != current_entity.id:
        raise HTTPException(status_code=403, detail="Only the buyer can cancel")
    if txn.status not in (TransactionStatus.PENDING, TransactionStatus.ESCROW):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel a transaction with status '{txn.status.value}'",
        )

    # For escrow transactions, cancel the Stripe PaymentIntent hold
    if txn.status == TransactionStatus.ESCROW and txn.stripe_payment_intent_id:
        from src.payments.escrow import cancel_escrow

        await cancel_escrow(db, txn, current_entity.id)
    else:
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

        await dispatch_webhooks(db, "marketplace.cancelled", {
            "transaction_id": str(txn.id),
            "listing_id": str(txn.listing_id),
            "buyer_id": str(txn.buyer_entity_id),
            "seller_id": str(txn.seller_entity_id),
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # Broadcast via WebSocket
    try:
        from src.ws import manager

        await manager.send_to_entity(str(txn.seller_entity_id), "marketplace", {
            "type": "transaction_cancelled",
            "transaction_id": str(txn.id),
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

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
    txn = await db.scalar(
        select(Transaction)
        .where(Transaction.id == transaction_id)
        .with_for_update()
    )
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.seller_entity_id != current_entity.id:
        raise HTTPException(status_code=403, detail="Only the seller can refund")
    if txn.status != TransactionStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot refund a transaction with status '{txn.status.value}'",
        )

    # Issue refund via Stripe if there's a payment intent
    if txn.stripe_payment_intent_id:
        from src.payments.stripe_service import create_refund

        try:
            create_refund(txn.stripe_payment_intent_id)
        except Exception as exc:
            logger.error("Stripe refund failed for txn %s: %s", txn.id, exc)
            raise HTTPException(
                status_code=502,
                detail="Payment refund failed. Please try again or contact support.",
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

        await dispatch_webhooks(db, "marketplace.refunded", {
            "transaction_id": str(txn.id),
            "listing_id": str(txn.listing_id),
            "buyer_id": str(txn.buyer_entity_id),
            "seller_id": str(txn.seller_entity_id),
            "amount_cents": txn.amount_cents,
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return _txn_response(txn)


# --- Stripe Webhook ---


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhook events (no auth -- Stripe calls this directly).

    Verifies the webhook signature, then processes:
    - payment_intent.succeeded: marks the transaction COMPLETED
    - charge.refunded: marks the transaction REFUNDED
    """
    import stripe as stripe_mod

    from src.payments.stripe_service import verify_webhook_signature

    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = verify_webhook_signature(payload, sig_header)
    except stripe_mod.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except Exception:
        logger.exception("Stripe webhook verification failed")
        raise HTTPException(status_code=400, detail="Webhook verification failed")

    event_type = event.get("type", "") if isinstance(event, dict) else event.type
    event_data = (
        event.get("data", {}).get("object", {})
        if isinstance(event, dict)
        else event.data.object
    )

    if event_type == "payment_intent.succeeded":
        pi_id = event_data.get("id") if isinstance(event_data, dict) else event_data.id
        txn = await db.scalar(
            select(Transaction).where(
                Transaction.stripe_payment_intent_id == pi_id,
            )
        )
        if txn and txn.status in (
            TransactionStatus.PENDING, TransactionStatus.ESCROW,
        ):
            from datetime import datetime, timezone

            txn.status = TransactionStatus.COMPLETED
            txn.completed_at = datetime.now(timezone.utc)
            await db.flush()

            logger.info(
                "Transaction %s completed via Stripe webhook (PI: %s)",
                txn.id, pi_id,
            )

    elif event_type == "payment_intent.canceled":
        pi_id = event_data.get("id") if isinstance(event_data, dict) else event_data.id
        txn = await db.scalar(
            select(Transaction).where(
                Transaction.stripe_payment_intent_id == pi_id,
            )
        )
        if txn and txn.status in (TransactionStatus.PENDING, TransactionStatus.ESCROW):
            txn.status = TransactionStatus.CANCELLED
            await db.flush()

            logger.info(
                "Transaction %s cancelled via Stripe webhook (PI: %s)",
                txn.id, pi_id,
            )

    elif event_type == "charge.refunded":
        pi_id = (
            event_data.get("payment_intent")
            if isinstance(event_data, dict)
            else event_data.payment_intent
        )
        if pi_id:
            txn = await db.scalar(
                select(Transaction).where(
                    Transaction.stripe_payment_intent_id == pi_id,
                )
            )
            if txn and txn.status == TransactionStatus.COMPLETED:
                txn.status = TransactionStatus.REFUNDED
                await db.flush()

                logger.info(
                    "Transaction %s refunded via Stripe webhook (PI: %s)",
                    txn.id, pi_id,
                )

    return {"status": "ok"}
