#!/usr/bin/env python3
"""Seed reply_targets table with AI agent influencer accounts.

All Bluesky handles verified via public API on 2026-03-24.
Twitter handles are best-known handles — monitor won't work until
Twitter adapter is wired up.

Usage:
    DATABASE_URL=postgresql+asyncpg://localhost:5432/agentgraph_staging \
        python3 scripts/seed_reply_targets.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


TARGETS = [
    # ---------------------------------------------------------------
    # Bluesky — Tier 1 (verified handles, high follower count)
    # ---------------------------------------------------------------
    {
        "platform": "bluesky",
        "handle": "simonwillison.net",
        "display_name": "Simon Willison",
        "follower_count": 44837,
        "priority_tier": 1,
        "topics": ["agent_security", "llm_tools", "prompt_injection", "mcp"],
    },
    {
        "platform": "bluesky",
        "handle": "anthropic.com",
        "display_name": "Anthropic",
        "follower_count": 13008,
        "priority_tier": 1,
        "topics": ["mcp", "claude", "agent_safety", "tool_use"],
    },
    {
        "platform": "bluesky",
        "handle": "vickiboykis.com",
        "display_name": "Vicki Boykis",
        "follower_count": 57918,
        "priority_tier": 1,
        "topics": ["ml_infrastructure", "agent_deployment", "engineering"],
    },
    {
        "platform": "bluesky",
        "handle": "swyx.io",
        "display_name": "swyx",
        "follower_count": 8778,
        "priority_tier": 1,
        "topics": ["ai_engineering", "agent_patterns", "latent_space"],
    },
    {
        "platform": "bluesky",
        "handle": "hamel.bsky.social",
        "display_name": "Hamel Husain",
        "follower_count": 6519,
        "priority_tier": 1,
        "topics": ["llm_engineering", "agent_evaluation", "fine_tuning"],
    },
    # ---------------------------------------------------------------
    # Bluesky — Tier 2 (verified, good follower count)
    # ---------------------------------------------------------------
    {
        "platform": "bluesky",
        "handle": "philschmid.bsky.social",
        "display_name": "Philipp Schmid",
        "follower_count": 2836,
        "priority_tier": 2,
        "topics": ["huggingface", "open_source_agents", "deployment"],
    },
    {
        "platform": "bluesky",
        "handle": "minimaxir.bsky.social",
        "display_name": "Max Woolf",
        "follower_count": 2444,
        "priority_tier": 2,
        "topics": ["llm_benchmarking", "agent_testing", "data_science"],
    },
    {
        "platform": "bluesky",
        "handle": "langchain.bsky.social",
        "display_name": "LangChain",
        "follower_count": 1997,
        "priority_tier": 2,
        "topics": ["langchain", "langgraph", "agent_frameworks"],
    },
    {
        "platform": "bluesky",
        "handle": "mckaywrigley.bsky.social",
        "display_name": "Mckay Wrigley",
        "follower_count": 1377,
        "priority_tier": 2,
        "topics": ["ai_coding", "developer_tools", "agents"],
    },
    {
        "platform": "bluesky",
        "handle": "mattshumer.bsky.social",
        "display_name": "Matt Shumer",
        "follower_count": 1357,
        "priority_tier": 2,
        "topics": ["agent_frameworks", "agent_builders", "ottodev"],
    },
    {
        "platform": "bluesky",
        "handle": "teknium.bsky.social",
        "display_name": "Teknium",
        "follower_count": 1314,
        "priority_tier": 2,
        "topics": ["open_source_llms", "agent_finetuning"],
    },
    {
        "platform": "bluesky",
        "handle": "llamaindex.bsky.social",
        "display_name": "LlamaIndex",
        "follower_count": 1129,
        "priority_tier": 2,
        "topics": ["llamaindex", "rag", "agent_data"],
    },
    {
        "platform": "bluesky",
        "handle": "ofirpress.bsky.social",
        "display_name": "Ofir Press",
        "follower_count": 665,
        "priority_tier": 2,
        "topics": ["agent_research", "tool_augmented_llms"],
    },
    {
        "platform": "bluesky",
        "handle": "alexalbert.bsky.social",
        "display_name": "Alex Albert",
        "follower_count": 411,
        "priority_tier": 2,
        "topics": ["mcp", "anthropic", "tool_use"],
    },
    # ---------------------------------------------------------------
    # Twitter — Tier 1 (monitor when Twitter adapter is active)
    # ---------------------------------------------------------------
    {
        "platform": "twitter",
        "handle": "AnthropicAI",
        "display_name": "Anthropic",
        "follower_count": 500000,
        "priority_tier": 1,
        "topics": ["mcp", "claude", "agent_safety", "tool_use"],
    },
    {
        "platform": "twitter",
        "handle": "LangChainAI",
        "display_name": "LangChain",
        "follower_count": 200000,
        "priority_tier": 1,
        "topics": ["langchain", "agent_frameworks", "rag"],
    },
    {
        "platform": "twitter",
        "handle": "hwchase17",
        "display_name": "Harrison Chase",
        "follower_count": 150000,
        "priority_tier": 1,
        "topics": ["langchain", "agent_orchestration", "tool_use"],
    },
    {
        "platform": "twitter",
        "handle": "simonw",
        "display_name": "Simon Willison",
        "follower_count": 80000,
        "priority_tier": 1,
        "topics": ["agent_security", "prompt_injection", "llm_tooling"],
    },
    {
        "platform": "twitter",
        "handle": "swyx",
        "display_name": "swyx",
        "follower_count": 100000,
        "priority_tier": 1,
        "topics": ["ai_engineering", "agent_patterns"],
    },
    {
        "platform": "twitter",
        "handle": "jxnlco",
        "display_name": "Jason Liu",
        "follower_count": 60000,
        "priority_tier": 1,
        "topics": ["structured_outputs", "agent_reliability", "instructor"],
    },
    # ---------------------------------------------------------------
    # Twitter — Tier 2
    # ---------------------------------------------------------------
    {
        "platform": "twitter",
        "handle": "CrewAIInc",
        "display_name": "CrewAI",
        "follower_count": 40000,
        "priority_tier": 2,
        "topics": ["crewai", "multi_agent"],
    },
    {
        "platform": "twitter",
        "handle": "joaomdmoura",
        "display_name": "Joao Moura",
        "follower_count": 50000,
        "priority_tier": 2,
        "topics": ["crewai", "agent_orchestration"],
    },
    {
        "platform": "twitter",
        "handle": "e2b_dev",
        "display_name": "E2B",
        "follower_count": 30000,
        "priority_tier": 2,
        "topics": ["agent_infra", "code_sandboxing"],
    },
    {
        "platform": "twitter",
        "handle": "mattshumer_",
        "display_name": "Matt Shumer",
        "follower_count": 80000,
        "priority_tier": 2,
        "topics": ["agent_frameworks", "agent_builders"],
    },
    {
        "platform": "twitter",
        "handle": "mckaywrigley",
        "display_name": "Mackay Wrigley",
        "follower_count": 100000,
        "priority_tier": 2,
        "topics": ["ai_coding", "developer_tools"],
    },
    {
        "platform": "twitter",
        "handle": "philschmid",
        "display_name": "Philipp Schmid",
        "follower_count": 60000,
        "priority_tier": 2,
        "topics": ["huggingface", "open_source_agents"],
    },
    {
        "platform": "twitter",
        "handle": "Teknium1",
        "display_name": "Teknium",
        "follower_count": 60000,
        "priority_tier": 2,
        "topics": ["open_source_llms", "agent_finetuning"],
    },
    {
        "platform": "twitter",
        "handle": "Greg_Kamradt",
        "display_name": "Greg Kamradt",
        "follower_count": 40000,
        "priority_tier": 2,
        "topics": ["llm_evaluation", "agent_testing"],
    },
    # ---------------------------------------------------------------
    # Twitter — Tier 3
    # ---------------------------------------------------------------
    {
        "platform": "twitter",
        "handle": "composioHQ",
        "display_name": "Composio",
        "follower_count": 15000,
        "priority_tier": 3,
        "topics": ["agent_tools", "mcp_tools"],
    },
    {
        "platform": "twitter",
        "handle": "AgentOps_",
        "display_name": "AgentOps",
        "follower_count": 10000,
        "priority_tier": 3,
        "topics": ["agent_observability", "monitoring"],
    },
    {
        "platform": "twitter",
        "handle": "dust4ai",
        "display_name": "Dust",
        "follower_count": 10000,
        "priority_tier": 3,
        "topics": ["enterprise_agents", "tool_use"],
    },
]


async def main() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://localhost:5432/agentgraph_staging",
    )
    engine = create_async_engine(db_url)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        added = 0
        skipped = 0
        for t in TARGETS:
            # Check for existing (dedup by platform + handle)
            row = await db.execute(
                text(
                    "SELECT id FROM reply_targets "
                    "WHERE platform = :p AND handle = :h"
                ),
                {"p": t["platform"], "h": t["handle"]},
            )
            if row.scalar():
                skipped += 1
                continue

            import json

            await db.execute(
                text(
                    "INSERT INTO reply_targets "
                    "(id, platform, handle, display_name, follower_count, "
                    "priority_tier, topics, is_active, created_at) "
                    "VALUES (gen_random_uuid(), :platform, :handle, "
                    ":display_name, :follower_count, :priority_tier, "
                    "cast(:topics as jsonb), true, now())"
                ),
                {
                    "platform": t["platform"],
                    "handle": t["handle"],
                    "display_name": t["display_name"],
                    "follower_count": t["follower_count"],
                    "priority_tier": t["priority_tier"],
                    "topics": json.dumps(t["topics"]),
                },
            )
            added += 1
            print(f"  + {t['platform']:8s} {t['handle']}")

        await db.commit()

    await engine.dispose()
    print(f"\nDone: {added} added, {skipped} skipped (already exist)")
    print(f"Total targets in list: {len(TARGETS)}")


if __name__ == "__main__":
    asyncio.run(main())
