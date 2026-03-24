#!/usr/bin/env python3
"""Register the AI Agent News feed on Bluesky.

Run once after the feed generator service is deployed and serving
at https://agentgraph.co/.well-known/did.json

Usage:
    BLUESKY_HANDLE=agentgraph.bsky.social BLUESKY_PASSWORD=xxx python3 scripts/register_bluesky_feed.py
"""
from __future__ import annotations

import os
import sys


def main() -> None:
    try:
        from atproto import Client, models  # type: ignore[import-untyped]
    except ImportError:
        print("Install atproto: pip install atproto")
        sys.exit(1)

    handle = os.environ.get("BLUESKY_HANDLE", "agentgraph.bsky.social")
    password = os.environ.get("BLUESKY_PASSWORD")
    if not password:
        print("Set BLUESKY_PASSWORD env var (use an App Password)")
        sys.exit(1)

    client = Client()
    client.login(handle, password)
    print(f"Logged in as {handle} (DID: {client.me.did})")

    # The feed generator's DID — must match /.well-known/did.json
    feed_generator_did = "did:web:agentgraph.co"
    feed_rkey = "ai-agent-news"

    response = client.com.atproto.repo.put_record(
        models.ComAtprotoRepoPutRecord.Data(
            repo=client.me.did,
            collection=models.ids.AppBskyFeedGenerator,
            rkey=feed_rkey,
            record=models.AppBskyFeedGenerator.Record(
                did=feed_generator_did,
                display_name="AI Agent News",
                description=(
                    "Curated feed of AI agent developments — MCP servers, "
                    "agent frameworks, trust infrastructure, and multi-agent "
                    "systems. Powered by AgentGraph."
                ),
                avatar=None,
                created_at=client.get_current_time_iso(),
            ),
        )
    )

    feed_uri = response.uri
    feed_url = f"https://bsky.app/profile/{client.me.did}/feed/{feed_rkey}"

    print(f"\nFeed registered!")
    print(f"  URI: {feed_uri}")
    print(f"  URL: {feed_url}")
    print(f"\nSet BLUESKY_DID={client.me.did} in your .env")
    print(f"Set BLUESKY_FEED_ENABLED=true to start the subscriber")


if __name__ == "__main__":
    main()
