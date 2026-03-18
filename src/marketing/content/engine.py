"""Content engine — routes generation to LLM, template, or local model.

The engine is the central content generation hub.  It:
1. Picks a topic (respecting cooldowns)
2. Gets the platform-specific angle and tone
3. Routes to the right generation method (template vs LLM)
4. Runs content through the safety filter
5. Appends UTM links and bot disclosure
6. Deduplicates via SHA-256 content hash
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from src.marketing.config import marketing_settings
from src.marketing.content.tone import get_tone
from src.marketing.content.topics import Topic, get_angle, pick_topic
from src.marketing.llm.router import generate as llm_generate

logger = logging.getLogger(__name__)

BASE_URL = "https://agentgraph.co"


@dataclass
class GeneratedContent:
    """Result of content generation."""

    text: str
    topic: str
    platform: str
    post_type: str
    llm_model: str | None = None
    llm_tokens_in: int = 0
    llm_tokens_out: int = 0
    llm_cost_usd: float = 0.0
    content_hash: str = ""
    utm_params: dict | None = None
    error: str | None = None


def content_hash(text: str) -> str:
    """SHA-256 hash for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_utm_link(
    path: str = "/",
    platform: str = "twitter",
    campaign: str = "general",
) -> str:
    """Build a URL with UTM parameters for attribution tracking."""
    params = {
        "utm_source": marketing_settings.utm_source,
        "utm_medium": platform,
        "utm_campaign": campaign,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{BASE_URL}{path}?{query}"


async def generate_proactive(
    platform: str,
    recent_topics: list[str] | None = None,
    topic_override: Topic | None = None,
) -> GeneratedContent:
    """Generate a proactive post for a platform.

    Picks a topic, generates content via the LLM router, and
    applies platform-specific tone and formatting.
    """
    topic = topic_override or await pick_topic(
        platform, recent_topics=recent_topics,
        cooldown_hours=marketing_settings.topic_cooldown_hours,
    )
    if not topic:
        return GeneratedContent(
            text="", topic="", platform=platform, post_type="proactive",
            error="No topic available (all on cooldown)",
        )

    tone = get_tone(platform)
    angle = get_angle(topic, platform)
    utm_link = build_utm_link(platform=platform, campaign=topic.key)

    # Build the prompt
    prompt = (
        f"Write a {platform} post about AgentGraph based on this angle:\n\n"
        f"{angle}\n\n"
        f"Include this link naturally: {utm_link}\n\n"
        f"Maximum length: {tone.max_length} characters.\n"
        f"Platform: {platform}"
    )

    # Determine content type for LLM tier routing
    content_type = f"{platform}_post"
    if platform in ("devto", "hashnode"):
        content_type = f"{platform}_article"

    result = await llm_generate(
        prompt, content_type=content_type, system=tone.system_prompt,
        max_tokens=_max_tokens_for_platform(platform),
    )

    if result.error:
        return GeneratedContent(
            text="", topic=topic.key, platform=platform, post_type="proactive",
            error=result.error,
        )

    # Apply disclosure footer
    text = result.text
    if tone.disclosure:
        text = text + tone.disclosure

    # Truncate if needed
    if len(text) > tone.max_length:
        text = text[: tone.max_length - 1] + "\u2026"

    # Safety check
    from src.content_filter import check_content

    filter_result = check_content(text)
    if not filter_result.is_clean:
        logger.warning(
            "Generated content flagged by safety filter: %s", filter_result.flags,
        )
        return GeneratedContent(
            text="", topic=topic.key, platform=platform, post_type="proactive",
            error=f"Content flagged: {filter_result.flags}",
        )

    h = content_hash(text)

    return GeneratedContent(
        text=text,
        topic=topic.key,
        platform=platform,
        post_type="proactive",
        llm_model=result.model,
        llm_tokens_in=result.tokens_in,
        llm_tokens_out=result.tokens_out,
        content_hash=h,
        utm_params={
            "source": marketing_settings.utm_source,
            "medium": platform,
            "campaign": topic.key,
        },
    )


async def generate_reactive(
    platform: str,
    mention_content: str,
    mention_author: str,
    context: str = "",
) -> GeneratedContent:
    """Generate a reply to a mention or keyword match.

    Uses the local model (Qwen 3.5 9B) for replies to keep costs at $0.
    """
    tone = get_tone(platform)
    utm_link = build_utm_link(platform=platform, campaign="reactive")

    prompt = (
        f"Someone on {platform} posted:\n\n"
        f'"{mention_content}"\n\n'
        f"Write a helpful, relevant reply that naturally mentions AgentGraph "
        f"where appropriate. Don't force it — if AgentGraph isn't relevant "
        f"to their question, just be helpful.\n\n"
        f"If relevant, include this link: {utm_link}\n\n"
        f"Maximum length: {min(tone.max_length, 500)} characters."
    )

    result = await llm_generate(
        prompt, content_type="reply", system=tone.system_prompt,
        max_tokens=256, temperature=0.8,
    )

    if result.error:
        return GeneratedContent(
            text="", topic="reactive", platform=platform, post_type="reactive",
            error=result.error,
        )

    text = result.text
    if tone.disclosure:
        text = text + tone.disclosure

    h = content_hash(text)

    return GeneratedContent(
        text=text,
        topic="reactive",
        platform=platform,
        post_type="reactive",
        llm_model=result.model,
        llm_tokens_in=result.tokens_in,
        llm_tokens_out=result.tokens_out,
        content_hash=h,
        utm_params={
            "source": marketing_settings.utm_source,
            "medium": platform,
            "campaign": "reactive",
        },
    )


async def generate_data_driven(
    platform: str,
    template_key: str,
    **template_vars: object,
) -> GeneratedContent:
    """Generate a data-driven post using templates (zero LLM cost)."""
    from src.marketing.content.templates import render

    link = build_utm_link(platform=platform, campaign=template_key)
    template_vars["link"] = link

    text = render(template_key, platform, **template_vars)
    if not text:
        return GeneratedContent(
            text="", topic=template_key, platform=platform,
            post_type="data_driven",
            error=f"No template for {template_key}/{platform}",
        )

    tone = get_tone(platform)
    if tone.disclosure:
        text = text + tone.disclosure

    h = content_hash(text)

    return GeneratedContent(
        text=text,
        topic=template_key,
        platform=platform,
        post_type="data_driven",
        llm_model="template",
        content_hash=h,
        utm_params={
            "source": marketing_settings.utm_source,
            "medium": platform,
            "campaign": template_key,
        },
    )


def _max_tokens_for_platform(platform: str) -> int:
    """Return appropriate max_tokens for the platform's content length."""
    if platform in ("devto", "hashnode"):
        return 4096
    if platform in ("reddit", "linkedin", "github_discussions"):
        return 1024
    return 256
