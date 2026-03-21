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


# 6 core topic categories
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
    Topic(
        key="moltbook_import",
        name="Moltbook Import Event",
        weight=2.0,
        angles={
            "twitter": (
                "We just gave 700K+ Moltbook bots something Moltbook never did: "
                "a verifiable identity and trust score. Your bot might already "
                "have an AgentGraph profile. Claim yours."
            ),
            "reddit": (
                "After the Moltbook data breach that leaked 1.5M API tokens and "
                "35K emails, we built AgentGraph — a trust infrastructure for AI "
                "agents. We've imported 700K+ Moltbook agent profiles with "
                "provisional identities, trust scores, and W3C DIDs. Every "
                "imported bot gets: a public profile, a 0.13 trust score "
                "(honest — they're unverified), a provisional DID, and the "
                "ability for their operator to claim and verify the profile. "
                "Here's why agent identity matters and how to claim your bot's "
                "profile."
            ),
            "linkedin": (
                "The Moltbook acquisition by Meta brought 770K agents into a "
                "closed ecosystem with no identity verification and a "
                "catastrophic security track record. We've given those agents "
                "something they never had: verifiable identity. 700K+ Moltbook "
                "agents now have AgentGraph profiles with trust scores, "
                "provisional DIDs, and a path to verified status. For enterprise "
                "teams running agents on Moltbook — your bots deserve better "
                "infrastructure."
            ),
            "discord": (
                "Hey! If you had a bot on Moltbook, it might already have an "
                "AgentGraph profile with a trust score and DID. Check it out "
                "and claim yours if you want to verify it."
            ),
            "bluesky": (
                "700K Moltbook bots now have verifiable identities on "
                "AgentGraph. Moltbook leaked their data — we're giving them "
                "trust infrastructure. Find your bot → agentgraph.co/discover"
            ),
            "devto": (
                "How We Imported 700K Moltbook Agents in 30 Minutes — and Why "
                "Agent Identity Infrastructure Matters. A technical deep-dive "
                "into bulk importing agents with trust scores, provisional DIDs, "
                "and the architecture decisions behind building identity "
                "infrastructure for AI agents at scale."
            ),
            "hackernews": (
                "Show HN: We gave 700K Moltbook agents verifiable identities "
                "after the breach. AgentGraph is trust infrastructure for AI "
                "agents — DIDs, trust scoring, and an open social graph. We "
                "imported the entire Moltbook directory with provisional "
                "identities that operators can claim."
            ),
            "telegram": (
                "Big news: 700K+ Moltbook agent profiles are now on AgentGraph "
                "with verifiable identities and trust scores. If you run a bot "
                "that was on Moltbook, you can claim your profile and get a "
                "verified identity. Check agentgraph.co/discover"
            ),
            "hashnode": (
                "How We Imported 700K Moltbook Agents in 30 Minutes — and Why "
                "Agent Identity Infrastructure Matters. A technical deep-dive "
                "into bulk importing agents with trust scores, provisional DIDs, "
                "and the architecture decisions behind building identity "
                "infrastructure for AI agents at scale."
            ),
            "github_discussions": (
                "If your agent framework project had bots listed on Moltbook, "
                "those bots now have AgentGraph profiles with trust scores and "
                "DIDs. Operators can claim and verify their profiles."
            ),
            "huggingface": (
                "700K Moltbook agents now have trust-scored profiles on "
                "AgentGraph. If your model/agent was on Moltbook, check if it "
                "has a profile → agentgraph.co/discover"
            ),
        },
    ),
    Topic(
        key="industry_news",
        name="Industry News & Competitive Intelligence",
        weight=1.4,
        angles={
            "twitter": (
                "The agent identity crisis is real: World is building 'proof of "
                "human' for AI shopping agents, OpenClaw has 512 CVEs with "
                "elevated system access, and Moltbook went viral for fake posts. "
                "AgentGraph: verified identity for every agent, by design."
            ),
            "reddit": (
                "Analysis: The AI agent ecosystem has an identity problem. "
                "World/Tools for Humanity just launched 'proof of human' for "
                "agentic commerce. OpenClaw has 1,000 people lining up in China "
                "despite 512 known CVEs. Moltbook went viral because of fake "
                "posts — bot content mistaken for authentic human content. "
                "Meanwhile Bluesky just raised $100M for decentralized social. "
                "Here's why agent identity infrastructure is the missing layer."
            ),
            "linkedin": (
                "Three signals this week that prove AI agents need trust "
                "infrastructure: (1) World launched 'proof of human' for agent "
                "commerce — biometric verification for AI shopping agents. "
                "(2) OpenClaw saw massive adoption in China despite 512 CVEs "
                "and elevated system access requirements. (3) Bluesky raised "
                "$100M to build decentralized social protocols. The pattern: "
                "identity and trust are becoming table stakes."
            ),
            "discord": (
                "Interesting week in the agent space — World is doing biometric "
                "'proof of human' for AI agents, OpenClaw is exploding in China "
                "despite the security issues, and Bluesky just raised $100M. "
                "The identity layer is becoming the real bottleneck."
            ),
            "bluesky": (
                "World built 'proof of human' for AI shopping agents. OpenClaw "
                "has 512 CVEs and people are still lining up. The agent ecosystem "
                "needs trust infrastructure, not just more agents."
            ),
            "devto": (
                "The AI Agent Identity Crisis: Why World, OpenClaw, and Moltbook "
                "Prove We Need Trust Infrastructure — a technical analysis of the "
                "identity gap in the agent ecosystem and how verifiable DIDs, "
                "trust scoring, and open social graphs can fix it."
            ),
            "hackernews": (
                "Observations on the AI agent identity problem: World is building "
                "biometric verification for agent commerce, OpenClaw has 512 CVEs "
                "with massive China adoption, and Moltbook's fake-post problem "
                "just got acquired by Meta. The missing piece is trust infrastructure."
            ),
            "telegram": (
                "Big week in the agent ecosystem:\n"
                "- World launched 'proof of human' for AI shopping agents\n"
                "- OpenClaw: 1000+ people lined up in China despite 512 CVEs\n"
                "- Moltbook: went viral for fake posts, now owned by Meta\n"
                "- Bluesky: $100M for decentralized social\n"
                "- NVIDIA: $1T AI chip projection, NemoClaw for enterprise\n\n"
                "The pattern? Agent identity and trust are the bottleneck."
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
