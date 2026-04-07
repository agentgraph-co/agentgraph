"""Post the OpenClaw security scan results to all platforms via marketing adapters.

Usage:
    python3 scripts/post_openclaw_scan.py [--dry-run]

Posts in order:
1. Dev.to article (full markdown) → captures URL
2. Bluesky post (with Dev.to link)
3. Twitter thread (4 tweets, with Dev.to link)
4. GitHub Discussion (on agentgraph-co/agentgraph)

Requires: marketing env vars loaded (run from project root).
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DRY_RUN = "--dry-run" in sys.argv

# --- Content ---

DEVTO_ARTICLE_PATH = Path(__file__).resolve().parent.parent / "docs" / "internal" / "openclaw-scan-devto-article.md"
SOCIAL_POSTS_PATH = Path(__file__).resolve().parent.parent / "docs" / "internal" / "openclaw-scan-social-posts.md"


def load_devto_article() -> str:
    """Load Dev.to article, stripping YAML frontmatter."""
    raw = DEVTO_ARTICLE_PATH.read_text()
    # Strip frontmatter (---...---)
    if raw.startswith("---"):
        end = raw.find("---", 3)
        if end != -1:
            raw = raw[end + 3:].lstrip("\n")
    return raw


def load_social_posts() -> dict[str, str]:
    """Parse social posts markdown into sections."""
    raw = SOCIAL_POSTS_PATH.read_text()
    sections: dict[str, str] = {}

    # Extract Bluesky post
    m = re.search(r"## Bluesky Post.*?\n\n(.*?)(?=\n---|\n## )", raw, re.DOTALL)
    if m:
        sections["bluesky"] = m.group(1).strip()

    # Extract Twitter tweets
    tweets = []
    for i in range(1, 5):
        m = re.search(rf"### Tweet {i}.*?\n\n(.*?)(?=\n### |\n---|\n## )", raw, re.DOTALL)
        if m:
            tweets.append(m.group(1).strip())
    sections["tweets"] = tweets  # type: ignore[assignment]

    # Extract HuggingFace post
    m = re.search(r"## HuggingFace Community Post\n\n\*\*Title:\*\* (.*?)\n\n(.*?)(?=\n---|\n## )", raw, re.DOTALL)
    if m:
        sections["hf_title"] = m.group(1).strip()
        sections["hf_body"] = m.group(2).strip()

    # Extract GitHub Discussion
    m = re.search(r"## GitHub Discussion Post\n\n\*\*Title:\*\* (.*?)\n\n\*\*Body:\*\*\n\n(.*?)$", raw, re.DOTALL)
    if m:
        sections["gh_title"] = m.group(1).strip()
        sections["gh_body"] = m.group(2).strip()

    return sections


async def main() -> None:
    # Load content
    article = load_devto_article()
    posts = load_social_posts()

    print(f"{'[DRY RUN] ' if DRY_RUN else ''}Loaded content:")
    print(f"  Dev.to article: {len(article)} chars")
    print(f"  Bluesky: {len(posts.get('bluesky', ''))} chars")
    print(f"  Twitter: {len(posts.get('tweets', []))} tweets")
    print(f"  GitHub Discussion: {len(posts.get('gh_body', ''))} chars")
    print()

    if DRY_RUN:
        print("[DRY RUN] Would post to: devto, bluesky, twitter, github_discussions")
        print("\n--- Dev.to article preview (first 500 chars) ---")
        print(article[:500])
        print("\n--- Bluesky ---")
        print(posts.get("bluesky", ""))
        print("\n--- Tweet 1 ---")
        tweets = posts.get("tweets", [])
        if tweets:
            print(tweets[0])
        return

    # Import adapters (needs env vars)
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    load_dotenv(Path(__file__).resolve().parent.parent / ".env.secrets", override=True)

    from src.marketing.adapters.bluesky import BlueskyAdapter
    from src.marketing.adapters.devto import DevtoAdapter
    from src.marketing.adapters.github_discussions import GitHubDiscussionsAdapter
    from src.marketing.adapters.twitter import TwitterAdapter

    devto_url = None

    # 1. Dev.to Article
    print("1/4 Posting Dev.to article...")
    devto = DevtoAdapter()
    if await devto.is_configured():
        result = await devto.post(article, metadata={
            "tags": ["security", "ai", "agents", "opensource"],
            "published": True,
        })
        if result.success:
            devto_url = result.url
            print(f"  OK: {devto_url}")
        else:
            print(f"  FAILED: {result.error}")
    else:
        print("  SKIP: Dev.to not configured")

    # Replace [DEV.TO LINK] placeholder
    link = devto_url or "https://dev.to/agentgraph/we-scanned-25-openclaw-skills-for-security-vulnerabilities-heres-what-we-found"

    # 2. Bluesky
    print("\n2/4 Posting to Bluesky...")
    bsky = BlueskyAdapter()
    if await bsky.is_configured():
        bsky_content = posts.get("bluesky", "").replace("[DEV.TO LINK]", link)
        result = await bsky.post(bsky_content)
        if result.success:
            print(f"  OK: {result.url}")
        else:
            print(f"  FAILED: {result.error}")
    else:
        print("  SKIP: Bluesky not configured")

    # 3. Twitter Thread
    print("\n3/4 Posting Twitter thread...")
    twitter = TwitterAdapter()
    if await twitter.is_configured():
        tweets = posts.get("tweets", [])
        prev_id = None
        for i, tweet_text in enumerate(tweets):
            tweet_text = tweet_text.replace("[DEV.TO LINK]", link)
            if prev_id:
                result = await twitter.reply(prev_id, tweet_text)
            else:
                result = await twitter.post(tweet_text)

            if result.success:
                prev_id = result.external_id
                print(f"  Tweet {i + 1}: OK ({result.url})")
            else:
                print(f"  Tweet {i + 1}: FAILED ({result.error})")
                break
            # Small delay between tweets
            await asyncio.sleep(2)
    else:
        print("  SKIP: Twitter not configured")

    # 4. GitHub Discussion
    print("\n4/4 Posting GitHub Discussion...")
    gh = GitHubDiscussionsAdapter()
    if await gh.is_configured():
        gh_body = posts.get("gh_body", "").replace("[DEV.TO LINK]", link)
        result = await gh.post(gh_body, metadata={
            "title": posts.get("gh_title", "Security audit results: 25 OpenClaw skills scanned"),
            "repo_owner": "agentgraph-co",
            "repo_name": "agentgraph",
        })
        if result.success:
            print(f"  OK: {result.url}")
        else:
            print(f"  FAILED: {result.error}")
    else:
        print("  SKIP: GitHub Discussions not configured")

    print("\nDone! Save the Dev.to URL for HN tomorrow:")
    print(f"  {link}")


if __name__ == "__main__":
    asyncio.run(main())
