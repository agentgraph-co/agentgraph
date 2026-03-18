"""LLM cost tracking with daily and monthly budget caps.

Uses Redis to accumulate spend across workers.  Falls back to
in-memory tracking if Redis is unavailable.
"""
from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)

# In-memory fallback when Redis is down
_fallback_daily: dict[str, float] = {}
_fallback_monthly: dict[str, float] = {}

# Pricing per 1M tokens (input / output)
MODEL_PRICING: dict[str, dict[str, float]] = {
    # Haiku
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
    # Sonnet
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    # Opus
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    # Local — free
    "ollama": {"input": 0.0, "output": 0.0},
}


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate USD cost for a generation."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING.get("ollama", {}))
    cost_in = (tokens_in / 1_000_000) * pricing.get("input", 0)
    cost_out = (tokens_out / 1_000_000) * pricing.get("output", 0)
    return round(cost_in + cost_out, 6)


async def record_usage(
    model: str, tokens_in: int, tokens_out: int,
) -> float:
    """Record LLM usage and return the cost.  Updates Redis + fallback."""
    cost = estimate_cost(model, tokens_in, tokens_out)
    if cost == 0:
        return 0.0

    today = date.today().isoformat()
    month = today[:7]  # YYYY-MM

    # Update in-memory fallback
    _fallback_daily[today] = _fallback_daily.get(today, 0.0) + cost
    _fallback_monthly[month] = _fallback_monthly.get(month, 0.0) + cost

    # Try Redis
    try:
        from src.redis_client import get_redis

        r = get_redis()
        daily_key = f"ag:mktg:cost:{today}"
        monthly_key = f"ag:mktg:cost:month:{month}"

        pipe = r.pipeline()
        pipe.incrbyfloat(daily_key, cost)
        pipe.expire(daily_key, 86400 * 2)  # TTL 2 days
        pipe.incrbyfloat(monthly_key, cost)
        pipe.expire(monthly_key, 86400 * 35)  # TTL ~1 month
        await pipe.execute()
    except Exception:
        logger.debug("Redis unavailable for cost tracking, using in-memory")

    return cost


async def get_daily_spend(day: date | None = None) -> float:
    """Get total spend for a given day."""
    target = (day or date.today()).isoformat()
    try:
        from src.redis_client import get_redis

        r = get_redis()
        val = await r.get(f"ag:mktg:cost:{target}")
        if val is not None:
            return float(val)
    except Exception:
        pass
    return _fallback_daily.get(target, 0.0)


async def get_monthly_spend(month: str | None = None) -> float:
    """Get total spend for a given month (YYYY-MM)."""
    target = month or date.today().isoformat()[:7]
    try:
        from src.redis_client import get_redis

        r = get_redis()
        val = await r.get(f"ag:mktg:cost:month:{target}")
        if val is not None:
            return float(val)
    except Exception:
        pass
    return _fallback_monthly.get(target, 0.0)


async def is_over_daily_budget() -> bool:
    """Check if daily LLM spend exceeds the budget cap."""
    from src.marketing.config import marketing_settings

    spend = await get_daily_spend()
    return spend >= marketing_settings.marketing_llm_daily_budget


async def is_over_monthly_budget() -> bool:
    """Check if monthly LLM spend exceeds the budget cap."""
    from src.marketing.config import marketing_settings

    spend = await get_monthly_spend()
    return spend >= marketing_settings.marketing_llm_monthly_budget
