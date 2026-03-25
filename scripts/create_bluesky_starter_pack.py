#!/usr/bin/env python3
"""Create a Bluesky Starter Pack for AI Agent builders.

Run once to create the starter pack, then share the link.

Usage:
    BLUESKY_HANDLE=agentgraph.bsky.social BLUESKY_PASSWORD=xxx python3 scripts/create_bluesky_starter_pack.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone


# Curated list of AI agent builders / MCP authors / framework maintainers on Bluesky
# Update this list as you discover more accounts
CURATED_ACCOUNTS = [
    # Tier 1 — verified handles, high follower count
    "simonwillison.net",          # Simon Willison — agent security, LLM tools, MCP
    "anthropic.com",              # Anthropic — MCP, Claude, agent safety
    "vickiboykis.com",            # Vicki Boykis — ML infrastructure, engineering
    "swyx.io",                    # swyx — AI engineering, agent patterns
    "hamel.bsky.social",          # Hamel Husain — LLM engineering, agent evaluation
    # Tier 2 — verified, good follower count
    "philschmid.bsky.social",     # Philipp Schmid — HuggingFace, open-source agents
    "minimaxir.bsky.social",      # Max Woolf — LLM benchmarking, agent testing
    "langchain.bsky.social",      # LangChain — agent frameworks
    "mckaywrigley.bsky.social",   # Mckay Wrigley — AI coding, developer tools
    "mattshumer.bsky.social",     # Matt Shumer — agent frameworks, OttoDev
    "teknium.bsky.social",        # Teknium — open-source LLMs, agent fine-tuning
    "llamaindex.bsky.social",     # LlamaIndex — RAG, agent data
    "ofirpress.bsky.social",      # Ofir Press — agent research, tool-augmented LLMs
    "alexalbert.bsky.social",     # Alex Albert — MCP, Anthropic, tool use
]


def main() -> None:
    try:
        from atproto import Client, models  # type: ignore[import-untyped]
    except ImportError:
        print("Install atproto: pip install atproto")
        sys.exit(1)

    if not CURATED_ACCOUNTS:
        print("No accounts in CURATED_ACCOUNTS list!")
        print("Edit this script to add Bluesky handles first.")
        sys.exit(1)

    handle = os.environ.get("BLUESKY_HANDLE", "agentgraph.bsky.social")
    password = os.environ.get("BLUESKY_PASSWORD")
    if not password:
        print("Set BLUESKY_PASSWORD env var")
        sys.exit(1)

    client = Client()
    client.login(handle, password)
    print(f"Logged in as {handle}")

    # Step 1: Create a list to hold the accounts
    list_record = client.com.atproto.repo.create_record(
        models.ComAtprotoRepoCreateRecord.Data(
            repo=client.me.did,
            collection="app.bsky.graph.list",
            record={
                "$type": "app.bsky.graph.list",
                "purpose": "app.bsky.graph.defs#curatelist",
                "name": "AI Agent Builders & Researchers",
                "description": (
                    "People building AI agents, MCP servers, agent frameworks, "
                    "and trust infrastructure."
                ),
                "createdAt": datetime.now(timezone.utc).isoformat(),
            },
        )
    )
    list_uri = list_record.uri
    print(f"List created: {list_uri}")

    # Step 2: Add accounts to the list
    added = 0
    for acct in CURATED_ACCOUNTS:
        try:
            profile = client.get_profile(acct)
            client.com.atproto.repo.create_record(
                models.ComAtprotoRepoCreateRecord.Data(
                    repo=client.me.did,
                    collection="app.bsky.graph.listitem",
                    record={
                        "$type": "app.bsky.graph.listitem",
                        "subject": profile.did,
                        "list": list_uri,
                        "createdAt": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )
            added += 1
            print(f"  Added: {acct} ({profile.display_name})")
        except Exception as exc:
            print(f"  SKIP: {acct} — {exc}")

    print(f"\nAdded {added}/{len(CURATED_ACCOUNTS)} accounts to list")

    # Step 3: Create the starter pack
    starter_pack = client.com.atproto.repo.create_record(
        models.ComAtprotoRepoCreateRecord.Data(
            repo=client.me.did,
            collection="app.bsky.graph.starterpack",
            record={
                "$type": "app.bsky.graph.starterpack",
                "name": "AI Agent Builders & Researchers",
                "description": (
                    "Essential follows for anyone building AI agents, "
                    "MCP servers, or working on agent trust infrastructure. "
                    "Curated by AgentGraph."
                ),
                "list": list_uri,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            },
        )
    )

    rkey = starter_pack.uri.split("/")[-1]
    pack_url = f"https://bsky.app/starter-pack/{client.me.did}/{rkey}"
    print(f"\nStarter Pack created!")
    print(f"  URI: {starter_pack.uri}")
    print(f"  URL: {pack_url}")
    print(f"\nShare this URL in posts and onboarding flows.")


if __name__ == "__main__":
    main()
