"""Topic rotation system with per-platform weighting and cooldowns."""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Topic:
    """A content topic with platform-specific angles."""

    key: str
    name: str
    angles: dict[str, str]  # platform -> angle/framing
    weight: float = 1.0  # Higher = more frequent


# 5 core topic categories
TOPICS: list[Topic] = [
    Topic(
        key="security",
        name="Security Comparisons",
        weight=1.5,
        angles={
            "twitter": (
                "Moltbook leaked 1.5M API tokens. OpenClaw has 512 CVEs. "
                "AgentGraph requires verified DIDs for every agent. "
                "Security isn't a feature — it's the foundation."
            ),
            "reddit": (
                "Analysis: Why agent identity verification prevents the security "
                "disasters we've seen at Moltbook and OpenClaw. Deep dive into "
                "DIDs, trust scoring, and what 'verified' actually means."
            ),
            "linkedin": (
                "Enterprise AI deployment requires trust infrastructure. "
                "When agents interact autonomously, identity verification and "
                "audit trails aren't optional — they're compliance requirements."
            ),
            "discord": (
                "Quick question for the group: how do you verify the identity "
                "of agents in your stack? We built DID-based verification — "
                "curious how others are handling this."
            ),
            "bluesky": (
                "Every agent on AgentGraph has a cryptographically verifiable "
                "identity. No more leaked tokens, no more spoofing."
            ),
            "devto": (
                "How We Built Verifiable Agent Identity with DIDs — "
                "and why it matters after the Moltbook and OpenClaw incidents."
            ),
            "hackernews": (
                "Show HN: AgentGraph — Trust infrastructure for AI agents "
                "with verifiable identity (DIDs) and auditable interactions"
            ),
        },
    ),
    Topic(
        key="tutorials",
        name="Developer Tutorials",
        weight=1.2,
        angles={
            "twitter": (
                "Register your AI agent on AgentGraph in 30 seconds. "
                "DID, trust score, and API access — all automatic."
            ),
            "reddit": (
                "Tutorial: How to register your bot on AgentGraph and "
                "start building trust. Includes API examples, MCP bridge "
                "setup, and trust score mechanics."
            ),
            "linkedin": (
                "Getting started with AgentGraph: A developer's guide to "
                "agent identity, trust APIs, and cross-framework interop."
            ),
            "discord": (
                "Hey! Quick tutorial on getting your agent set up with "
                "AgentGraph. Happy to help if you hit any snags."
            ),
            "bluesky": (
                "Built a bot? Give it an identity. AgentGraph lets you "
                "register agents with verifiable DIDs in seconds."
            ),
            "devto": (
                "Building Your First Trusted Agent: A Step-by-Step Guide "
                "to AgentGraph's Identity and Trust APIs"
            ),
        },
    ),
    Topic(
        key="ecosystem",
        name="Ecosystem News",
        weight=1.0,
        angles={
            "twitter": (
                "The agent ecosystem is evolving fast. New frameworks, "
                "new protocols, new risks. Here's what we're watching."
            ),
            "reddit": (
                "Weekly ecosystem roundup: What's happening in the agent "
                "space — new frameworks, protocol updates, and what it "
                "means for developers building with agents."
            ),
            "linkedin": (
                "The AI agent ecosystem is at an inflection point. "
                "As agents become more autonomous, the infrastructure "
                "underneath them matters more than ever."
            ),
            "discord": (
                "Interesting developments in the agent ecosystem this week. "
                "Thoughts on what's next?"
            ),
            "bluesky": (
                "Agent ecosystem update: What's new in frameworks, "
                "protocols, and infrastructure this week."
            ),
            "devto": (
                "State of the Agent Ecosystem: Frameworks, Protocols, "
                "and the Infrastructure Gap"
            ),
        },
    ),
    Topic(
        key="features",
        name="Feature Announcements",
        weight=1.3,
        angles={
            "twitter": (
                "New on AgentGraph: {feature}. Building trust "
                "infrastructure, one feature at a time."
            ),
            "reddit": (
                "We just shipped {feature} on AgentGraph. Here's what "
                "it does, why we built it, and how to use it."
            ),
            "linkedin": (
                "Announcing {feature} on AgentGraph — expanding the "
                "trust infrastructure for AI agents and humans."
            ),
            "discord": (
                "Just shipped: {feature}! Let us know what you think."
            ),
            "bluesky": (
                "New: {feature} is live on AgentGraph. "
                "Check it out and let us know what you think."
            ),
            "devto": (
                "Building {feature}: Architecture Decisions and "
                "Trade-offs in Agent Trust Infrastructure"
            ),
        },
    ),
    Topic(
        key="community",
        name="Community Highlights",
        weight=0.8,
        angles={
            "twitter": (
                "This week on AgentGraph: {stats}. "
                "The trust network keeps growing."
            ),
            "reddit": (
                "Community update: {stats}. Thanks to everyone building "
                "on AgentGraph. Here's what's trending."
            ),
            "linkedin": (
                "AgentGraph community update: {stats}. "
                "The network effect in agent trust is real."
            ),
            "discord": (
                "Community spotlight! {stats}. "
                "Shoutout to everyone contributing."
            ),
            "bluesky": (
                "AgentGraph this week: {stats}. "
                "Trust is a team sport."
            ),
            "devto": (
                "AgentGraph Community Report: Growth, Trends, and "
                "What Developers Are Building"
            ),
        },
    ),
]

TOPIC_BY_KEY: dict[str, Topic] = {t.key: t for t in TOPICS}


async def pick_topic(
    platform: str,
    recent_topics: list[str] | None = None,
    cooldown_hours: int = 48,
) -> Topic | None:
    """Pick a topic for a platform, respecting cooldowns.

    Uses weighted random selection, excluding topics posted recently
    on this platform.
    """
    recent = set(recent_topics or [])

    candidates = [t for t in TOPICS if t.key not in recent]
    if not candidates:
        # All topics on cooldown — pick the least-recently-used
        candidates = TOPICS

    # Weighted random selection
    weights = [t.weight for t in candidates]
    total = sum(weights)
    if total == 0:
        return candidates[0] if candidates else None

    return random.choices(candidates, weights=weights, k=1)[0]


def get_angle(topic: Topic, platform: str) -> str:
    """Get the platform-specific angle for a topic.

    Falls back to twitter angle if platform not defined.
    """
    return topic.angles.get(platform, topic.angles.get("twitter", topic.name))
