"""Rate limit information endpoints.

Provides transparency about rate limiting tiers, current limits,
and how trust scores affect rate limits.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.api.deps import get_optional_entity
from src.api.rate_limit import (
    _get_client_ip,
    _get_entity_trust_score,
    _limiter,
    _maybe_upgrade_to_trusted,
    _resolve_tier,
    _tier_read_limit,
    _tier_write_limit,
    _trust_scaled_limit,
    get_tier_info,
)
from src.models import Entity

router = APIRouter(prefix="/rate-limits", tags=["rate-limits"])


@router.get("/tiers")
async def list_rate_limit_tiers():
    """List all rate limit tiers with their limits and trust scaling info."""
    return get_tier_info()


@router.get("/me")
async def my_rate_limit_info(
    request: Request,
    current_entity: Entity | None = Depends(get_optional_entity),
):
    """Get your current rate limit tier, limits, and usage."""
    tier = _resolve_tier(current_entity)
    tier = await _maybe_upgrade_to_trusted(tier, current_entity)

    base_read = _tier_read_limit(tier)
    base_write = _tier_write_limit(tier)

    trust_score = None
    scaled_read = base_read
    scaled_write = base_write

    if current_entity is not None:
        entity_id = str(current_entity.id)
        trust_score = await _get_entity_trust_score(entity_id)
        if trust_score is not None:
            scaled_read = _trust_scaled_limit(base_read, trust_score)
            scaled_write = _trust_scaled_limit(base_write, trust_score)

    # Get current usage
    ip = _get_client_ip(request)
    read_remaining = await _limiter.get_remaining(
        f"read:{ip}", scaled_read,
    )
    write_remaining = await _limiter.get_remaining(
        f"write:{ip}", scaled_write,
    )

    return {
        "tier": tier.value,
        "trust_score": trust_score,
        "limits": {
            "reads_per_minute": {
                "base": base_read,
                "effective": scaled_read,
                "remaining": read_remaining,
            },
            "writes_per_minute": {
                "base": base_write,
                "effective": scaled_write,
                "remaining": write_remaining,
            },
        },
        "trust_scaling_applied": trust_score is not None and trust_score > 0,
    }
