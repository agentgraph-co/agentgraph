"""Jetstream subscriber — filters AI agent posts from the Bluesky firehose.

Uses Bluesky's Jetstream (JSON WebSocket) rather than the full CBOR firehose
for simplicity and reduced bandwidth.  Matched posts are stored in a Redis
sorted set keyed by timestamp for fast retrieval by the feed skeleton endpoint.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import websockets  # type: ignore[import-untyped]

from src.feeds.bluesky.keywords import matches_keywords

logger = logging.getLogger(__name__)

# Jetstream endpoint — filter to only post creates
JETSTREAM_URL = (
    "wss://jetstream2.us-east.bsky.network/subscribe"
    "?wantedCollections=app.bsky.feed.post"
)

# Redis key for the feed sorted set (score = timestamp_us)
FEED_KEY = "bluesky:feed:ai-agent-news"

# Max posts to keep in the feed
MAX_FEED_SIZE = 2000

# How often to log stats (seconds)
STATS_INTERVAL = 300


async def run_subscriber() -> None:
    """Connect to Jetstream and filter posts into Redis.  Reconnects on failure."""
    while True:
        try:
            await _subscribe()
        except asyncio.CancelledError:
            logger.info("Jetstream subscriber cancelled")
            return
        except Exception:
            logger.exception("Jetstream subscriber error — reconnecting in 5s")
            await asyncio.sleep(5)


async def _subscribe() -> None:
    """Single subscription session."""
    from src.redis_client import get_redis

    r = get_redis()

    # Resume from last cursor if available
    cursor = await r.get("bluesky:feed:jetstream_cursor")
    url = JETSTREAM_URL
    if cursor:
        url += f"&cursor={cursor.decode()}"
        logger.info("Resuming Jetstream from cursor %s", cursor.decode())

    processed = 0
    matched = 0
    last_stats = time.monotonic()

    async with websockets.connect(url, ping_interval=30, ping_timeout=10) as ws:
        logger.info("Connected to Jetstream")
        async for raw in ws:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue

            # Only process post creates
            if event.get("kind") != "commit":
                continue
            commit = event.get("commit", {})
            if commit.get("operation") != "create":
                continue
            if commit.get("collection") != "app.bsky.feed.post":
                continue

            record = commit.get("record", {})
            text = record.get("text", "")
            if not text:
                continue

            processed += 1

            # Check keyword match
            kw_matches = matches_keywords(text)
            if not kw_matches:
                continue

            # Build AT-URI
            did = event.get("did", "")
            rkey = commit.get("rkey", "")
            if not did or not rkey:
                continue
            at_uri = f"at://{did}/app.bsky.feed.post/{rkey}"
            timestamp_us = event.get("time_us", int(time.time() * 1_000_000))

            # Store in Redis sorted set
            await r.zadd(FEED_KEY, {at_uri: timestamp_us})
            matched += 1

            # Trim to max size (remove oldest)
            count = await r.zcard(FEED_KEY)
            if count > MAX_FEED_SIZE:
                await r.zremrangebyrank(FEED_KEY, 0, count - MAX_FEED_SIZE - 1)

            # Save cursor periodically (every 1000 events)
            if processed % 1000 == 0:
                cursor_val = str(timestamp_us)
                await r.set("bluesky:feed:jetstream_cursor", cursor_val)

            # Log stats periodically
            now = time.monotonic()
            if now - last_stats > STATS_INTERVAL:
                logger.info(
                    "Jetstream stats: processed=%d matched=%d feed_size=%d",
                    processed, matched, await r.zcard(FEED_KEY),
                )
                last_stats = now
