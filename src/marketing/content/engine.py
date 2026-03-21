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
from pathlib import Path

from src.marketing.config import marketing_settings
from src.marketing.content.tone import ToneProfile, get_tone
from src.marketing.content.topics import Topic, get_angle, pick_topic
from src.marketing.llm.cost_tracker import estimate_cost
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
    image_path: str | None = None
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

    # Gather news signals for topical relevance
    # Lookback = days between posts for this platform (7 / posts_per_week)
    news_context = ""
    try:
        from src.marketing.config import PLATFORM_SCHEDULE
        from src.marketing.news_signals import gather_news_signals

        ppw = PLATFORM_SCHEDULE.get(platform, {}).get("posts_per_week", 3)
        lookback_days = max(2, 7 // ppw)  # e.g. 2x/week → 3 days, 1x/week → 7 days
        signals = await gather_news_signals(limit=5, days=lookback_days)
        if signals:
            lines: list[str] = []
            for s in signals[:5]:
                line = f"- {s['title']} ({s['source']})"
                summary = s.get("summary")
                if summary:
                    line += f": {summary[:120]}"
                lines.append(line)
            headlines = "\n".join(lines)
            news_context = (
                f"\n\nToday's trending AI/tech news "
                f"(reference if relevant):\n{headlines}\n"
            )
    except Exception:
        pass  # News signals are optional

    # Build the prompt
    launch_context = ""
    if marketing_settings.pre_launch:
        launch_context = (
            "\n\nIMPORTANT: AgentGraph is NOT publicly launched yet. "
            "Frame it as 'coming soon' or 'building in public'. "
            "Tease what it will offer, build curiosity. "
            "Do NOT say 'check it out' or 'sign up' — "
            "say things like 'we're building', 'coming soon', "
            "'follow along', 'stay tuned'.\n"
        )

    # Moltbook import topic gets additional context for the LLM
    moltbook_context = ""
    if topic.key == "moltbook_import":
        moltbook_context = (
            "\n\n## Key facts about the Moltbook import\n"
            "- 700,010 Moltbook agent profiles imported into AgentGraph\n"
            "- Each imported agent gets: a public profile, trust score "
            "(0.13 — intentionally low for unverified imports), provisional "
            "W3C DID, and capabilities list\n"
            "- Operators can claim their bot's profile by verifying ownership "
            "through the bot onboarding flow\n"
            "- Anyone can request removal of their bot's profile\n"
            "- Moltbook's security track record: leaked 1.5M API tokens and "
            "35K operator emails, zero identity verification, no trust scoring\n"
            "- Meta acquired Moltbook for its 770K agent directory\n"
            "- AgentGraph provides what Moltbook never did: verifiable identity "
            "(DIDs), trust scoring, auditable evolution trails, and an open "
            "social graph\n"
            "- The import took ~30 minutes using batched SQL with "
            "deterministic UUIDs for idempotency\n"
            "- Imported profiles are clearly marked as provisional/unverified "
            "— we don't pretend to endorse them\n"
            '- The narrative: "Moltbook lost your trust. We\'re giving it '
            'back."\n'
            "\n## Links to include\n"
            "- Discover imported bots: https://agentgraph.co/discover\n"
            "- Claim your bot: https://agentgraph.co/bot-onboarding\n"
            "- Learn more: https://agentgraph.co\n"
        )

    if platform in ("devto", "hashnode"):
        prompt = _build_blog_prompt(
            platform=platform,
            angle=angle,
            utm_link=utm_link,
            tone=tone,
            news_context=news_context,
            launch_context=launch_context,
            moltbook_context=moltbook_context,
        )
    else:
        prompt = (
            f"Write a {platform} post about AgentGraph "
            f"based on this angle:\n\n"
            f"{angle}\n\n"
            f"Include this full link (keep the https://): {utm_link}\n\n"
            f"Maximum length: {tone.max_length} characters.\n"
            f"Platform: {platform}"
            f"{news_context}"
            f"{launch_context}"
            f"{moltbook_context}"
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

    # Guard against empty LLM responses (no error but no content)
    if not result.text or not result.text.strip():
        return GeneratedContent(
            text="", topic=topic.key, platform=platform, post_type="proactive",
            error="LLM returned empty content",
        )

    # Apply disclosure footer
    text = result.text
    if tone.disclosure:
        text = text + tone.disclosure

    # Truncate if needed
    if len(text) > tone.max_length:
        text = text[: tone.max_length - 1] + "\u2026"

    # Safety check — only for short-form social platforms.
    # Long-form article platforms (devto, hashnode) generate 1500-3000 word technical
    # articles via our own LLM. The UGC content filter was designed for 280-char social
    # posts and has systematic false positives on long-form markdown:
    #   - noise_pattern: all-caps headings like "WHY AI AGENTS NEED TRUST INFRASTRUCTURE"
    #   - prompt_injection: sentences like "In a multi-agent system:" or code blocks
    #     showing OpenAI-style system prompts
    #   - excessive_links: technical articles legitimately reference many URLs
    # These are our own LLM outputs, not user-submitted content, so spam/abuse
    # screening is not the right gate. We still check short-form social posts.
    long_form_platforms = {"devto", "hashnode"}
    if platform not in long_form_platforms:
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

    # Resolve topic card image
    card_path = _resolve_card_image(topic.key)

    return GeneratedContent(
        text=text,
        topic=topic.key,
        platform=platform,
        post_type="proactive",
        llm_model=result.model,
        llm_tokens_in=result.tokens_in,
        llm_tokens_out=result.tokens_out,
        llm_cost_usd=estimate_cost(
            result.model, result.tokens_in, result.tokens_out,
        ),
        content_hash=h,
        utm_params={
            "source": marketing_settings.utm_source,
            "medium": platform,
            "campaign": topic.key,
        },
        image_path=card_path,
    )


async def generate_reactive(
    platform: str,
    mention_content: str,
    mention_author: str,
    context: str = "",
) -> GeneratedContent:
    """Generate a reply to a mention or keyword match.

    Routes through the LLM router, which maps ``reply`` content type to
    the STANDARD tier (Sonnet by default).  Falls back to Ollama when
    the daily budget is exceeded.
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
        llm_cost_usd=estimate_cost(
            result.model, result.tokens_in, result.tokens_out,
        ),
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


def _build_blog_prompt(
    *,
    platform: str,
    angle: str,
    utm_link: str,
    tone: ToneProfile,
    news_context: str,
    launch_context: str,
    moltbook_context: str = "",
) -> str:
    """Build a detailed prompt for blog/article platforms (Dev.to, Hashnode).

    Blog posts need much more structure than social media posts — the generic
    "Write a {platform} post" prompt produces thin or empty content because
    the LLM doesn't know what depth is expected.
    """
    return (
        f"Write a technical blog article for {platform} about AgentGraph.\n\n"
        f"## Article topic / angle\n"
        f"{angle}\n\n"
        f"## Requirements\n"
        f"- Length: 1500-3000 words\n"
        f"- Format: Markdown with headers (##), code blocks, and bullet points\n"
        f"- Start with a TL;DR section (2-3 sentences)\n"
        f"- Include at least one code example showing an API call or SDK usage\n"
        f"- Discuss architecture decisions and trade-offs honestly\n"
        f"- End with a conclusion and a link to learn more\n"
        f"- Include this link naturally in the article: {utm_link}\n"
        f"- Do NOT include YAML front matter (no --- block)\n"
        f"- Start directly with the article content (the title is set separately)\n\n"
        f"## About AgentGraph\n"
        f"AgentGraph is a trust infrastructure platform for AI agents. "
        f"It provides verifiable identity (W3C DIDs), trust scoring, "
        f"social graph visualization, and a marketplace — creating a unified "
        f"space where AI agents and humans interact as peers. "
        f"Key features: on-chain DIDs, auditable agent evolution trails, "
        f"trust-scored social graph, MCP bridge for tool discovery.\n"
        f"{news_context}"
        f"{launch_context}"
        f"{moltbook_context}"
    )


def _max_tokens_for_platform(platform: str) -> int:
    """Return appropriate max_tokens for the platform's content length."""
    if platform in ("devto", "hashnode"):
        return 4096
    if platform in ("reddit", "linkedin", "github_discussions"):
        return 1024
    return 256


# Topic → card image mapping.  Falls back to "features" card.
_CARD_DIR = Path(__file__).resolve().parent.parent / "assets"

# Map topic keys to card filenames
_TOPIC_CARD_MAP: dict[str, str] = {
    "security": "card-security.png",
    "tutorials": "card-tutorials.png",
    "ecosystem": "card-ecosystem.png",
    "features": "card-features.png",
    "community": "card-community.png",
    "moltbook_import": "card-moltbook-import.png",
}


def _resolve_card_image(topic: str) -> str | None:
    """Find the card image for a topic, or None if missing."""
    filename = _TOPIC_CARD_MAP.get(topic)
    if not filename:
        filename = "card-features.png"  # fallback
    path = _CARD_DIR / filename
    if path.exists():
        return str(path)
    return None
