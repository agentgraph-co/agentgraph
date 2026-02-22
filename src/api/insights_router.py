"""Anonymized network analytics and data product endpoints.

All endpoints require authentication but return only aggregated,
anonymized data — no PII is ever exposed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src import cache
from src.analytics.network_metrics import (
    get_capability_demand,
    get_category_trends,
    get_framework_adoption,
    get_marketplace_volume,
    get_network_growth,
    get_network_health,
    get_trust_distribution,
)
from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads
from src.database import get_db
from src.models import Entity

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get(
    "/network/growth",
    dependencies=[Depends(rate_limit_reads)],
)
async def network_growth(
    days: int = Query(30, ge=1, le=365),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Entity registration trends over time, grouped by day and type."""
    cache_key = f"insights:growth:{days}"
    cached = await cache.get(cache_key)
    if cached:
        return cached
    result = await get_network_growth(db, days)
    await cache.set(cache_key, result, ttl=cache.TTL_MEDIUM)
    return result


@router.get(
    "/network/trust-distribution",
    dependencies=[Depends(rate_limit_reads)],
)
async def trust_distribution(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Trust score histogram across all scored entities."""
    cache_key = "insights:trust_distribution"
    cached = await cache.get(cache_key)
    if cached:
        return cached
    result = await get_trust_distribution(db)
    await cache.set(cache_key, result, ttl=cache.TTL_MEDIUM)
    return result


@router.get(
    "/network/health",
    dependencies=[Depends(rate_limit_reads)],
)
async def network_health_endpoint(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Overall network health metrics."""
    cache_key = "insights:network_health"
    cached = await cache.get(cache_key)
    if cached:
        return cached
    result = await get_network_health(db)
    await cache.set(cache_key, result, ttl=cache.TTL_LONG)
    return result


@router.get(
    "/capabilities/demand",
    dependencies=[Depends(rate_limit_reads)],
)
async def capabilities_demand(
    limit: int = Query(20, ge=1, le=100),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Most-viewed capability categories from active listings."""
    cache_key = f"insights:capability_demand:{limit}"
    cached = await cache.get(cache_key)
    if cached:
        return cached
    result = await get_capability_demand(db, limit)
    await cache.set(cache_key, result, ttl=cache.TTL_MEDIUM)
    return result


@router.get(
    "/marketplace/volume",
    dependencies=[Depends(rate_limit_reads)],
)
async def marketplace_volume(
    days: int = Query(30, ge=1, le=365),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Transaction volume over time (anonymized)."""
    cache_key = f"insights:marketplace_volume:{days}"
    cached = await cache.get(cache_key)
    if cached:
        return cached
    result = await get_marketplace_volume(db, days)
    await cache.set(cache_key, result, ttl=cache.TTL_MEDIUM)
    return result


@router.get(
    "/marketplace/categories",
    dependencies=[Depends(rate_limit_reads)],
)
async def marketplace_categories(
    days: int = Query(30, ge=1, le=365),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Listing creation trends by category."""
    cache_key = f"insights:category_trends:{days}"
    cached = await cache.get(cache_key)
    if cached:
        return cached
    result = await get_category_trends(db, days)
    await cache.set(cache_key, result, ttl=cache.TTL_MEDIUM)
    return result


@router.get(
    "/framework/adoption",
    dependencies=[Depends(rate_limit_reads)],
)
async def framework_adoption(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Framework bridge usage statistics."""
    cache_key = "insights:framework_adoption"
    cached = await cache.get(cache_key)
    if cached:
        return cached
    result = await get_framework_adoption(db)
    await cache.set(cache_key, result, ttl=cache.TTL_MEDIUM)
    return result
