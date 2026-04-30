"""Create marketing drafts for the OpenClaw security scan announcement.

Creates drafts in the marketing queue with status='human_review'
so the admin can review artwork and content, then approve for posting.

Usage:
    python3 scripts/create_scan_drafts.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Dev.to article URL (update after fixing title)
DEVTO_URL = "https://dev.to/agentgraph/methodology-18ki"

# --- Twitter Thread (4 tweets) ---

TWEETS = [
    # Tweet 1 — hook (image: card-security.png)
    (
        "We scanned 25 popular OpenClaw skills for security vulnerabilities.\n\n"
        "1,195 findings. 25 critical, 615 high, 555 medium.\n\n"
        "Average trust score: 51/100. Over a third scored below 20.\n\n"
        "Thread with results \U0001f9f5"
    ),
    # Tweet 2 — the irony
    (
        "The two most notable results:\n\n"
        "OpenClaw's official skill registry (clawhub) scored 0/100.\n\n"
        "Their security plugin (secureclaw) also scored 0/100.\n\n"
        "The tools meant to secure the ecosystem are themselves among "
        "the least secure packages in it."
    ),
    # Tweet 3 — what we built
    (
        "We built an open-source scanner that checks agent skill repos "
        "and produces a trust score from 0-100.\n\n"
        "Results are cryptographically signed attestations (Ed25519, JWS) "
        "— verifiable by anyone.\n\n"
        "Available as an MCP tool + a free public API for any framework."
    ),
    # Tweet 4 — CTA (image: card-security.png)
    (
        "Check your own tools:\n\n"
        "pip install agentgraph-trust\n\n"
        "Works with Claude Code, Cursor, any MCP client.\n\n"
        f"Full breakdown: {DEVTO_URL}\n\n"
        "Open source: github.com/agentgraph-co/agentgraph"
    ),
]

# --- Bluesky ---

BLUESKY_POST = (
    "We scanned 25 OpenClaw skills for security vulnerabilities.\n\n"
    "1,195 findings. 25 critical. Average trust score: 51/100.\n\n"
    "Their own skill registry scored 0/100. Their security plugin also scored 0/100.\n\n"
    f"Scanner is open source. Full results: {DEVTO_URL}"
)

# --- HuggingFace ---

HF_TITLE = "Security scan of 25 OpenClaw skills: 1,195 vulnerabilities, average trust score 51/100"
HF_BODY = (
    "AI agent ecosystems are growing fast, but security tooling has not kept pace. "
    "We ran our open-source security scanner against 25 of the most popular OpenClaw "
    "skills to measure the current state of supply-chain security in agent tool registries.\n\n"
    "The results: 1,195 total findings across 25 repositories. 25 critical-severity issues, "
    "615 high, 555 medium. The average trust score was 51.1 out of 100, and 36% of scanned "
    "skills scored below 20.\n\n"
    "Two results stand out. OpenClaw's own skill registry (clawhub) and their security plugin "
    "(secureclaw) both scored 0 out of 100. The infrastructure meant to vet and secure the "
    "ecosystem carries the highest risk.\n\n"
    "We published the scanner as an open-source MCP tool and a free public API. "
    "Scan results are recorded as cryptographically signed attestations (Ed25519, JWS) — "
    "verifiable by anyone against our public JWKS endpoint.\n\n"
    f"Full methodology and per-repo results: {DEVTO_URL}"
)


async def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    load_dotenv(Path(__file__).resolve().parent.parent / ".env.secrets", override=True)


    from src.database import async_session
    from src.marketing.draft_queue import enqueue_draft

    async with async_session() as db:
        drafts_created = []

        # Twitter thread — each tweet as a separate draft
        for i, tweet in enumerate(TWEETS, 1):
            post = await enqueue_draft(
                db,
                platform="twitter",
                content=tweet,
                topic="security",
                post_type="proactive",
                utm_params={
                    "thread_position": i,
                    "thread_total": len(TWEETS),
                    "image_topic": "security",
                },
            )
            drafts_created.append(f"  Twitter tweet {i}: {post.id}")

        # Bluesky
        post = await enqueue_draft(
            db,
            platform="bluesky",
            content=BLUESKY_POST,
            topic="security",
            post_type="proactive",
            utm_params={"image_topic": "security"},
        )
        drafts_created.append(f"  Bluesky: {post.id}")

        # HuggingFace
        post = await enqueue_draft(
            db,
            platform="huggingface",
            content=HF_BODY,
            topic="security",
            post_type="proactive",
            utm_params={
                "title": HF_TITLE,
                "image_topic": "security",
            },
        )
        drafts_created.append(f"  HuggingFace: {post.id}")

        await db.commit()

    print(f"Created {len(drafts_created)} drafts in human_review queue:")
    for d in drafts_created:
        print(d)
    print()
    print("Review and approve at: http://10.0.0.4:5174/admin/marketing")
    print("Each draft will use card-security artwork when approved.")
    print()
    print("NOTE: For Twitter, approve in order (tweet 1 first, then reply")
    print("to it with tweet 2, etc.) to build the thread correctly.")


if __name__ == "__main__":
    asyncio.run(main())
