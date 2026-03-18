"""LLM router — picks the right model based on content type and budget.

Hierarchy:
- Templates (Jinja2) — $0, used for stats/recurring formats
- Ollama (Qwen 3.5 9B) — $0, used for engagement replies
- Haiku — ~$0.002/post, used for social posts
- Sonnet — ~$0.50/post, used for blog posts and important drafts
- Opus — ~$1.50/post, used for high-stakes content (HN, launches)

When daily budget is exceeded, falls back to templates-only mode.
"""
from __future__ import annotations

import logging
from enum import Enum

from src.marketing.llm.anthropic_client import LLMResponse
from src.marketing.llm.cost_tracker import (
    is_over_daily_budget,
    is_over_monthly_budget,
    record_usage,
)

logger = logging.getLogger(__name__)


class ContentTier(str, Enum):
    """Content importance tier — determines which model to use."""

    TEMPLATE = "template"          # Zero cost, Jinja2
    LOCAL = "local"                # Ollama (replies, simple engagement)
    STANDARD = "standard"          # Haiku (social posts)
    PREMIUM = "premium"            # Sonnet (blog posts, key threads)
    HIGH_STAKES = "high_stakes"    # Opus (HN drafts, launch copy, critical)


# Map content types to default tiers
CONTENT_TYPE_TIERS: dict[str, ContentTier] = {
    # Social posts
    "twitter_post": ContentTier.STANDARD,
    "reddit_post": ContentTier.STANDARD,
    "bluesky_post": ContentTier.STANDARD,
    "linkedin_post": ContentTier.STANDARD,
    "telegram_post": ContentTier.STANDARD,
    "discord_post": ContentTier.STANDARD,
    # Replies / engagement
    "reply": ContentTier.LOCAL,
    "engagement_reply": ContentTier.LOCAL,
    "onboarding_dm": ContentTier.LOCAL,
    # Blog / long-form
    "devto_article": ContentTier.PREMIUM,
    "hashnode_article": ContentTier.PREMIUM,
    # High-stakes
    "hackernews_draft": ContentTier.HIGH_STAKES,
    "producthunt_draft": ContentTier.HIGH_STAKES,
    "launch_announcement": ContentTier.HIGH_STAKES,
    # Data-driven (templates)
    "stats_post": ContentTier.TEMPLATE,
    "weekly_digest": ContentTier.TEMPLATE,
    "agent_announcement": ContentTier.TEMPLATE,
}


async def generate(
    prompt: str,
    *,
    content_type: str = "twitter_post",
    tier_override: ContentTier | None = None,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> LLMResponse:
    """Route a generation request to the appropriate LLM.

    Checks budget before using paid models.  Falls back gracefully:
    Opus → Sonnet → Haiku → Ollama → error.
    """
    tier = tier_override or CONTENT_TYPE_TIERS.get(content_type, ContentTier.STANDARD)

    # Template tier — caller should use templates directly, not this function
    if tier == ContentTier.TEMPLATE:
        return LLMResponse(
            text="", model="template", tokens_in=0, tokens_out=0,
            error="Use templates directly for TEMPLATE tier content",
        )

    # Check budget for paid tiers
    over_daily = await is_over_daily_budget()
    over_monthly = await is_over_monthly_budget()

    if tier == ContentTier.LOCAL or (over_daily and tier == ContentTier.STANDARD):
        return await _generate_local(prompt, system=system, max_tokens=max_tokens,
                                     temperature=temperature)

    if over_daily or over_monthly:
        logger.warning(
            "LLM budget exceeded (daily=%s, monthly=%s) — falling back to local",
            over_daily, over_monthly,
        )
        result = await _generate_local(prompt, system=system, max_tokens=max_tokens,
                                       temperature=temperature)
        if not result.error:
            return result
        # If local also fails, return budget error
        return LLMResponse(
            text="", model="budget_exceeded", tokens_in=0, tokens_out=0,
            error="Daily LLM budget exceeded and local model unavailable",
        )

    # Route to the right Anthropic model
    return await _generate_anthropic(
        prompt, tier=tier, system=system, max_tokens=max_tokens,
        temperature=temperature,
    )


async def _generate_local(
    prompt: str, *, system: str | None = None,
    max_tokens: int = 1024, temperature: float = 0.7,
) -> LLMResponse:
    """Generate using local Ollama."""
    from src.marketing.llm.ollama_client import generate as ollama_generate

    result = await ollama_generate(
        prompt, system=system, max_tokens=max_tokens, temperature=temperature,
    )
    if not result.error:
        await record_usage(result.model, result.tokens_in, result.tokens_out)
    return result


async def _generate_anthropic(
    prompt: str, *, tier: ContentTier,
    system: str | None = None, max_tokens: int = 1024,
    temperature: float = 0.7,
) -> LLMResponse:
    """Generate using the Anthropic API with the tier-appropriate model."""
    from src.marketing.config import marketing_settings
    from src.marketing.llm.anthropic_client import generate as anthropic_generate

    model_map = {
        ContentTier.STANDARD: marketing_settings.anthropic_haiku_model,
        ContentTier.PREMIUM: marketing_settings.anthropic_sonnet_model,
        ContentTier.HIGH_STAKES: marketing_settings.anthropic_opus_model,
    }
    model = model_map.get(tier, marketing_settings.anthropic_haiku_model)

    result = await anthropic_generate(
        prompt, model=model, system=system, max_tokens=max_tokens,
        temperature=temperature,
    )

    if not result.error:
        cost = await record_usage(result.model, result.tokens_in, result.tokens_out)
        logger.info(
            "LLM generation: model=%s tokens_in=%d tokens_out=%d cost=$%.4f",
            result.model, result.tokens_in, result.tokens_out, cost,
        )

    return result
