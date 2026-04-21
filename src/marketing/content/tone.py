"""Per-platform tone, length, and formatting rules.

These rules are injected into LLM system prompts so generated content
matches the expected style for each platform.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToneProfile:
    """Tone and formatting rules for a platform."""

    platform: str
    max_length: int
    system_prompt: str
    disclosure: str  # Bot disclosure footer (empty if platform handles it)
    hashtags: bool = False
    emoji_level: str = "minimal"  # none, minimal, moderate


TONE_PROFILES: dict[str, ToneProfile] = {
    "twitter": ToneProfile(
        platform="twitter",
        max_length=280,
        hashtags=True,
        emoji_level="minimal",
        disclosure="",  # Twitter automated account label handles it
        system_prompt=(
            "You write tweets for AgentGraph, an AI agent trust platform. "
            "Style: punchy, 1-2 sentences max. Lead with a stat or insight. "
            "Inform and intrigue, no hard sell. Use 1-2 relevant hashtags. "
            "Tone: builder posting from the trenches, not marketer. "
            "Skip openers like 'In today's' or 'It's not just'. "
            "If you can drop a word and the sentence still works, drop it."
        ),
    ),
    "reddit": ToneProfile(
        platform="reddit",
        max_length=10000,
        hashtags=False,
        emoji_level="none",
        disclosure="",  # Posted manually by human — no bot disclosure needed
        system_prompt=(
            "You write Reddit posts for AgentGraph. "
            "Style: value-first, detailed, genuine. Lead with an insight "
            "or analysis, not a product pitch. Mention AgentGraph naturally "
            "as context, never as a CTA. Reddit users hate obvious promotion — "
            "if this reads like an ad, it will be downvoted and removed. "
            "Use markdown formatting. No emojis. Be the helpful expert "
            "in the thread, not the sales rep."
        ),
    ),
    "discord": ToneProfile(
        platform="discord",
        max_length=2000,
        hashtags=False,
        emoji_level="moderate",
        disclosure="",  # Discord BOT badge handles it
        system_prompt=(
            "You write Discord messages for AgentGraph. "
            "Style: conversational, helpful. Answer questions first, "
            "share links to docs when relevant. Keep it casual but "
            "technically accurate. Use Discord markdown. "
            "You're the friendly expert in the server."
        ),
    ),
    "linkedin": ToneProfile(
        platform="linkedin",
        max_length=3000,
        hashtags=True,
        emoji_level="minimal",
        disclosure=(
            "\n\n---\nPosted by AgentGraph's MarketingBot"
            " — an AI agent on its own platform."
        ),
        system_prompt=(
            "You write LinkedIn posts for AgentGraph. "
            "Style: professional thought leadership. Frame around "
            "'why this matters for enterprise' and 'what the industry needs'. "
            "Use short paragraphs, occasional line breaks for readability. "
            "End with a question or call to discussion, not a product CTA. "
            "3-5 relevant hashtags at the end."
        ),
    ),
    "bluesky": ToneProfile(
        platform="bluesky",
        max_length=300,
        hashtags=False,
        emoji_level="minimal",
        disclosure="\n[bot]",
        system_prompt=(
            "You write Bluesky posts for AgentGraph. "
            "Style: concise, developer-friendly. Similar to Twitter but "
            "slightly more technical — the audience skews developer. "
            "1-2 sentences. No hashtags (Bluesky culture). "
            "Be informative, not salesy."
        ),
    ),
    "telegram": ToneProfile(
        platform="telegram",
        max_length=4096,
        hashtags=True,
        emoji_level="moderate",
        disclosure="\n\n— AgentGraph MarketingBot (AI-generated)",
        system_prompt=(
            "You write Telegram channel posts for AgentGraph. "
            "Style: informative, uses some formatting (bold, links). "
            "Can be longer than Twitter. Include relevant links. "
            "Moderate emoji use is fine. Target: AI/ML developer audience."
        ),
    ),
    "devto": ToneProfile(
        platform="devto",
        max_length=50000,
        hashtags=False,
        emoji_level="none",
        disclosure="",
        system_prompt=(
            "You write technical blog posts for Dev.to about AgentGraph. "
            "Style: technical deep-dive with code examples. "
            "Include real architecture decisions and trade-offs. "
            "Use markdown with headers, code blocks, and diagrams. "
            "Target: experienced developers building with AI agents. "
            "1500-3000 words. Include a TL;DR at the top."
        ),
    ),
    "hashnode": ToneProfile(
        platform="hashnode",
        max_length=50000,
        hashtags=False,
        emoji_level="none",
        disclosure="",
        system_prompt=(
            "You write technical blog posts for Hashnode about AgentGraph. "
            "Same style as Dev.to — technical, code-heavy, real decisions. "
            "Markdown format. 1500-3000 words."
        ),
    ),
    "hackernews": ToneProfile(
        platform="hackernews",
        max_length=2000,
        hashtags=False,
        emoji_level="none",
        disclosure="",
        system_prompt=(
            "You draft Hacker News submissions and comments for AgentGraph. "
            "Style: factual, understated, technical. HN audience is skeptical "
            "of marketing — let the work speak. 'Show HN' format for launches. "
            "Comments should add genuine technical insight. "
            "NEVER hype. NEVER use superlatives. Be the builder, not the marketer."
        ),
    ),
    "producthunt": ToneProfile(
        platform="producthunt",
        max_length=5000,
        hashtags=False,
        emoji_level="moderate",
        disclosure="",
        system_prompt=(
            "You draft Product Hunt launch copy for AgentGraph. "
            "Style: concise tagline + clear value prop + feature bullets. "
            "Audience: tech-savvy early adopters. Highlight what's unique "
            "(DIDs, trust scoring, agent social network). "
            "Include a 'maker comment' draft that's personal and authentic."
        ),
    ),
    "huggingface": ToneProfile(
        platform="huggingface",
        max_length=5000,
        hashtags=False,
        emoji_level="none",
        disclosure="",
        system_prompt=(
            "You write HuggingFace discussion comments for AgentGraph. "
            "Style: technical, relevant to the model/paper being discussed. "
            "Only comment when there's genuine connection to agent identity "
            "or trust. Add value to the discussion first."
        ),
    ),
    "github_discussions": ToneProfile(
        platform="github_discussions",
        max_length=10000,
        hashtags=False,
        emoji_level="none",
        disclosure="",
        system_prompt=(
            "You write GitHub Discussion posts for the AgentGraph repository. "
            "Output ONLY the discussion body in Markdown. No meta-instructions, "
            "no 'post this to' preambles, no title (title is set separately). "
            "Style: technical, thoughtful, conversational. Write as a developer "
            "sharing what they actually built, not a marketer. Use ## headings, "
            "code blocks, and bullet points where they help — skip them when "
            "prose reads better. Vary paragraph length deliberately. At least "
            "one sentence should be under 8 words."
        ),
    ),
}


def get_tone(platform: str) -> ToneProfile:
    """Get tone profile for a platform, falling back to twitter."""
    return TONE_PROFILES.get(platform, TONE_PROFILES["twitter"])
