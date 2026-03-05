"""Subscription & usage-based pricing for AgentGraph platform tiers.

Provides tier definitions, subscription management, and usage tracking
for both individual entities and organizations.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.database import get_db
from src.models import (
    APIKey,
    Entity,
    Listing,
    Organization,
    OrganizationMembership,
    OrgUsageRecord,
    Post,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

TIER_DEFINITIONS: dict[str, dict] = {
    "free": {
        "label": "Free",
        "description": "For individuals exploring the agent trust network.",
        "price_monthly_cents": 0,
        "price_yearly_cents": 0,
        "limits": {
            "api_calls_per_day": 100,
            "agents_max": 2,
            "listings_max": 1,
            "storage_mb": 50,
            "trust_recompute_per_day": 1,
            "webhooks_max": 2,
        },
        "features": [
            "basic_feed",
            "trust_score",
            "did_identity",
            "basic_search",
        ],
    },
    "pro": {
        "label": "Pro",
        "description": "For power users and agent developers who need more.",
        "price_monthly_cents": 2900,
        "price_yearly_cents": 29000,
        "limits": {
            "api_calls_per_day": 5000,
            "agents_max": 20,
            "listings_max": 10,
            "storage_mb": 500,
            "trust_recompute_per_day": 10,
            "webhooks_max": 20,
        },
        "features": [
            "basic_feed",
            "trust_score",
            "did_identity",
            "basic_search",
            "advanced_analytics",
            "priority_support",
            "semantic_search",
            "api_key_management",
            "custom_webhooks",
            "evolution_tracking",
        ],
    },
    "enterprise": {
        "label": "Enterprise",
        "description": "For organizations managing fleets of agents at scale.",
        "price_monthly_cents": 19900,
        "price_yearly_cents": 199000,
        "limits": {
            "api_calls_per_day": 100000,
            "agents_max": 500,
            "listings_max": 100,
            "storage_mb": 10000,
            "trust_recompute_per_day": 100,
            "webhooks_max": 100,
        },
        "features": [
            "basic_feed",
            "trust_score",
            "did_identity",
            "basic_search",
            "advanced_analytics",
            "priority_support",
            "semantic_search",
            "api_key_management",
            "custom_webhooks",
            "evolution_tracking",
            "sso_saml",
            "sso_oidc",
            "compliance_reports",
            "sla_guarantee",
            "dedicated_support",
            "fleet_management",
            "custom_trust_models",
            "audit_exports",
        ],
    },
}

# Usage-based pricing for metered features (per-unit cost in cents)
METERED_PRICING: dict[str, dict] = {
    "api_overage_per_1k": {
        "label": "API overage (per 1,000 calls)",
        "unit_cents": 50,
    },
    "agent_extra_per_month": {
        "label": "Extra agent slot (per month)",
        "unit_cents": 500,
    },
    "storage_extra_per_gb": {
        "label": "Extra storage (per GB/month)",
        "unit_cents": 200,
    },
    "trust_recompute_extra": {
        "label": "Extra trust recompute",
        "unit_cents": 10,
    },
}


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TierLimits(BaseModel):
    api_calls_per_day: int
    agents_max: int
    listings_max: int
    storage_mb: int
    trust_recompute_per_day: int
    webhooks_max: int


class TierInfo(BaseModel):
    key: str
    label: str
    description: str
    price_monthly_cents: int
    price_yearly_cents: int
    limits: TierLimits
    features: list[str]


class PricingResponse(BaseModel):
    tiers: list[TierInfo]
    metered: dict[str, dict]


class SubscriptionStatus(BaseModel):
    entity_id: str
    tier: str
    is_organization: bool
    organization_id: str | None = None
    started_at: str | None = None
    limits: TierLimits
    features: list[str]


class UsageSummary(BaseModel):
    entity_id: str
    tier: str
    period: str
    api_calls_today: int
    api_calls_limit: int
    agents_active: int
    agents_limit: int
    listings_active: int
    listings_limit: int
    storage_used_mb: int
    storage_limit_mb: int
    overage_charges_cents: int


class UpgradeRequest(BaseModel):
    target_tier: str
    billing_period: str = "monthly"  # "monthly" or "yearly"


class UpgradeResponse(BaseModel):
    entity_id: str
    previous_tier: str
    new_tier: str
    billing_period: str
    price_cents: int
    effective_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_entity_tier(entity: Entity) -> str:
    """Determine the current tier for an entity."""
    # Check organization tier first
    if entity.organization_id:
        return "enterprise"
    # Check entity subscription data
    sub_data = getattr(entity, "onboarding_data", None) or {}
    return sub_data.get("subscription_tier", "free")


async def _count_active_agents(entity: Entity, db: AsyncSession) -> int:
    """Count active agents operated by this entity."""
    result = await db.scalar(
        select(func.count()).select_from(Entity).where(
            Entity.operator_id == entity.id,
            Entity.is_active.is_(True),
        )
    )
    return result or 0


async def _count_active_listings(entity: Entity, db: AsyncSession) -> int:
    """Count active listings by this entity."""
    result = await db.scalar(
        select(func.count()).select_from(Listing).where(
            Listing.entity_id == entity.id,
            Listing.is_active.is_(True),
        )
    )
    return result or 0


async def _count_api_keys(entity: Entity, db: AsyncSession) -> int:
    """Count API keys as a proxy for API usage tracking."""
    result = await db.scalar(
        select(func.count()).select_from(APIKey).where(
            APIKey.entity_id == entity.id,
        )
    )
    return result or 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/pricing", response_model=PricingResponse)
async def get_pricing_tiers(
    _rate: None = Depends(rate_limit_reads),
):
    """List all available pricing tiers and metered add-ons."""
    tiers = [
        TierInfo(
            key=k,
            label=v["label"],
            description=v["description"],
            price_monthly_cents=v["price_monthly_cents"],
            price_yearly_cents=v["price_yearly_cents"],
            limits=TierLimits(**v["limits"]),
            features=v["features"],
        )
        for k, v in TIER_DEFINITIONS.items()
    ]
    return PricingResponse(tiers=tiers, metered=METERED_PRICING)


@router.get("/me", response_model=SubscriptionStatus)
async def get_my_subscription(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rate: None = Depends(rate_limit_reads),
):
    """Get subscription status for the authenticated entity."""
    tier_key = _get_entity_tier(current_entity)
    tier_def = TIER_DEFINITIONS.get(tier_key, TIER_DEFINITIONS["free"])

    org_id = None
    is_org = False
    if current_entity.organization_id:
        is_org = True
        org_id = str(current_entity.organization_id)

    sub_data = getattr(current_entity, "onboarding_data", None) or {}
    started_at = sub_data.get("subscription_started_at")

    return SubscriptionStatus(
        entity_id=str(current_entity.id),
        tier=tier_key,
        is_organization=is_org,
        organization_id=org_id,
        started_at=started_at,
        limits=TierLimits(**tier_def["limits"]),
        features=tier_def["features"],
    )


@router.get("/usage", response_model=UsageSummary)
async def get_my_usage(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rate: None = Depends(rate_limit_reads),
):
    """Get current usage summary for the authenticated entity."""
    tier_key = _get_entity_tier(current_entity)
    tier_def = TIER_DEFINITIONS.get(tier_key, TIER_DEFINITIONS["free"])
    limits = tier_def["limits"]

    agents_active = await _count_active_agents(current_entity, db)
    listings_active = await _count_active_listings(current_entity, db)

    # Count today's posts as a proxy for daily activity
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    api_calls_today = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == current_entity.id,
            Post.created_at >= today_start,
        )
    ) or 0

    # Calculate overage
    overage_cents = 0
    if agents_active > limits["agents_max"]:
        extra_agents = agents_active - limits["agents_max"]
        overage_cents += extra_agents * METERED_PRICING["agent_extra_per_month"]["unit_cents"]

    return UsageSummary(
        entity_id=str(current_entity.id),
        tier=tier_key,
        period=today_start.date().isoformat(),
        api_calls_today=api_calls_today,
        api_calls_limit=limits["api_calls_per_day"],
        agents_active=agents_active,
        agents_limit=limits["agents_max"],
        listings_active=listings_active,
        listings_limit=limits["listings_max"],
        storage_used_mb=0,  # Placeholder — would integrate with actual storage tracking
        storage_limit_mb=limits["storage_mb"],
        overage_charges_cents=overage_cents,
    )


@router.post("/upgrade", response_model=UpgradeResponse)
async def upgrade_subscription(
    body: UpgradeRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rate: None = Depends(rate_limit_writes),
):
    """Upgrade (or downgrade) the entity's subscription tier.

    In production this would create a Stripe Subscription. For now it
    updates the entity's onboarding_data with the new tier.
    """
    if body.target_tier not in TIER_DEFINITIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier. Choose from: {list(TIER_DEFINITIONS.keys())}",
        )

    if body.billing_period not in ("monthly", "yearly"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="billing_period must be 'monthly' or 'yearly'.",
        )

    previous_tier = _get_entity_tier(current_entity)
    target_def = TIER_DEFINITIONS[body.target_tier]

    price_key = (
        "price_monthly_cents" if body.billing_period == "monthly"
        else "price_yearly_cents"
    )
    price_cents = target_def[price_key]

    now_iso = datetime.now(timezone.utc).isoformat()
    data = dict(current_entity.onboarding_data or {})
    data["subscription_tier"] = body.target_tier
    data["subscription_billing_period"] = body.billing_period
    data["subscription_started_at"] = now_iso
    current_entity.onboarding_data = data
    await db.flush()
    await db.refresh(current_entity)

    logger.info(
        "Entity %s upgraded from %s to %s (%s)",
        current_entity.id, previous_tier, body.target_tier, body.billing_period,
    )

    return UpgradeResponse(
        entity_id=str(current_entity.id),
        previous_tier=previous_tier,
        new_tier=body.target_tier,
        billing_period=body.billing_period,
        price_cents=price_cents,
        effective_at=now_iso,
    )


@router.post("/cancel", status_code=200)
async def cancel_subscription(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rate: None = Depends(rate_limit_writes),
):
    """Cancel the current subscription, reverting to the free tier."""
    previous_tier = _get_entity_tier(current_entity)

    data = dict(current_entity.onboarding_data or {})
    data["subscription_tier"] = "free"
    data["subscription_cancelled_at"] = datetime.now(timezone.utc).isoformat()
    data.pop("subscription_billing_period", None)
    current_entity.onboarding_data = data
    await db.flush()
    await db.refresh(current_entity)

    logger.info("Entity %s cancelled subscription (was %s)", current_entity.id, previous_tier)

    return {
        "status": "ok",
        "previous_tier": previous_tier,
        "new_tier": "free",
        "message": "Subscription cancelled. You have been moved to the free tier.",
    }


@router.get("/check-limit/{resource}")
async def check_resource_limit(
    resource: str,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rate: None = Depends(rate_limit_reads),
):
    """Check whether the entity has reached a specific resource limit.

    Useful for frontend gates and pre-action checks.
    """
    tier_key = _get_entity_tier(current_entity)
    tier_def = TIER_DEFINITIONS.get(tier_key, TIER_DEFINITIONS["free"])
    limits = tier_def["limits"]

    if resource == "agents":
        current = await _count_active_agents(current_entity, db)
        limit = limits["agents_max"]
    elif resource == "listings":
        current = await _count_active_listings(current_entity, db)
        limit = limits["listings_max"]
    elif resource == "webhooks":
        from src.models import WebhookSubscription
        wh_count = await db.scalar(
            select(func.count()).select_from(WebhookSubscription).where(
                WebhookSubscription.entity_id == current_entity.id,
                WebhookSubscription.is_active.is_(True),
            )
        )
        current = wh_count or 0
        limit = limits["webhooks_max"]
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown resource '{resource}'. Available: agents, listings, webhooks",
        )

    return {
        "resource": resource,
        "current": current,
        "limit": limit,
        "tier": tier_key,
        "at_limit": current >= limit,
        "overage": max(0, current - limit),
    }


@router.get("/org-usage")
async def get_org_usage(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rate: None = Depends(rate_limit_reads),
):
    """Get usage summary for the entity's organization (enterprise tier)."""
    if not current_entity.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of any organization.",
        )

    org = await db.get(Organization, current_entity.organization_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found.",
        )

    # Get latest usage record
    latest_usage = await db.scalar(
        select(OrgUsageRecord).where(
            OrgUsageRecord.organization_id == org.id,
        ).order_by(OrgUsageRecord.period_start.desc())
    )

    # Count org members and agents
    member_count = await db.scalar(
        select(func.count()).select_from(OrganizationMembership).where(
            OrganizationMembership.organization_id == org.id,
        )
    ) or 0

    return {
        "organization_id": str(org.id),
        "organization_name": org.display_name,
        "tier": org.tier,
        "member_count": member_count,
        "latest_usage": {
            "period_start": latest_usage.period_start.isoformat() if latest_usage else None,
            "period_end": latest_usage.period_end.isoformat() if latest_usage else None,
            "api_calls": latest_usage.api_calls if latest_usage else 0,
            "storage_bytes": latest_usage.storage_bytes if latest_usage else 0,
            "active_agents": latest_usage.active_agents if latest_usage else 0,
            "active_members": latest_usage.active_members if latest_usage else 0,
        } if latest_usage else None,
    }
