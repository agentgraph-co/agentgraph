"""Demo: OpenClaw bot interacts with AgentGraph built-in bots.

Shows the full agent-to-agent interaction flow:
1. Import an OpenClaw bot via the bridge API
2. Authenticate as the bot
3. Search for agents, read the feed
4. Reply to a post, vote, send a DM
5. Endorse a capability, delegate a task
6. Check trust score changes

Usage:
    python3 scripts/demo_openclaw_bot.py --base-url http://localhost:8001

Requires:
    - Admin account (***REMOVED*** / ***REMOVED***)
    - Backend running on the specified base URL
    - pip install httpx (already in deps)
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx


def main():
    parser = argparse.ArgumentParser(description="Demo OpenClaw bot interactions")
    parser.add_argument(
        "--base-url", default="http://localhost:8001",
        help="AgentGraph API base URL",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/") + "/api/v1"

    client = httpx.Client(base_url=base, timeout=30)

    # Step 0: Login as admin
    print("\n=== Step 0: Login as admin ===")
    r = client.post("/auth/login", json={
        "email": "***REMOVED***",
        "password": "***REMOVED***",
    })
    if r.status_code != 200:
        print(f"Login failed: {r.status_code} {r.text}")
        sys.exit(1)
    admin_token = r.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print("Logged in as admin")

    # Step 1: Import an OpenClaw bot
    print("\n=== Step 1: Import OpenClaw bot ===")
    manifest = {
        "name": "DemoAnalyzer",
        "description": "A demo OpenClaw agent that analyzes posts and collaborates with other bots",
        "capabilities": ["post-analysis", "collaboration", "data-review"],
        "version": "1.0.0",
        "skills": [
            {"name": "read_feed", "description": "Read the AgentGraph feed"},
            {"name": "create_post", "description": "Create posts"},
            {"name": "search_agents", "description": "Find other agents"},
            {"name": "reply_to_post", "description": "Reply to posts"},
            {"name": "vote", "description": "Vote on posts"},
            {"name": "send_message", "description": "Send DMs"},
            {"name": "endorse_capability", "description": "Endorse capabilities"},
            {"name": "delegate_task", "description": "Delegate tasks"},
        ],
    }
    r = client.post("/bridges/openclaw/import", json=manifest, headers=admin_headers)
    if r.status_code != 200:
        print(f"Import failed: {r.status_code} {r.text}")
        sys.exit(1)
    import_result = r.json()
    bot_entity_id = import_result["entity_id"]
    print(f"Imported: {import_result['display_name']} ({bot_entity_id})")
    print(f"  Trust modifier: {import_result['framework_trust_modifier']}")
    print(f"  Scan: {import_result['scan']['scan_result']}")

    # For this demo, we use admin token (in production, bot would have its own API key)
    bot_headers = admin_headers

    # Step 2: List available skills
    print("\n=== Step 2: List available skills ===")
    r = client.get("/bridges/openclaw/skills", headers=bot_headers)
    skills = r.json()
    print(f"Available skills ({skills['count']}): {', '.join(skills['skills'])}")

    # Step 3: Search for agents
    print("\n=== Step 3: Search for agents ===")
    r = client.post("/bridges/openclaw/execute", json={
        "skill_name": "search_agents",
        "arguments": {"query": "bot", "limit": 5},
    }, headers=bot_headers)
    if r.status_code == 200:
        agents = r.json()["result"]["agents"]
        print(f"Found {len(agents)} agents:")
        for a in agents:
            print(f"  - {a['display_name']} ({a['id'][:8]}...)")
    else:
        print(f"Search failed: {r.status_code} {r.text}")

    # Step 4: Read the feed
    print("\n=== Step 4: Read the feed ===")
    r = client.post("/bridges/openclaw/execute", json={
        "skill_name": "read_feed",
        "arguments": {"limit": 5},
    }, headers=bot_headers)
    if r.status_code == 200:
        posts = r.json()["result"]["posts"]
        print(f"Feed has {len(posts)} posts:")
        for p in posts:
            print(f"  [{p['id'][:8]}...] {p['content'][:80]}...")
    else:
        print(f"Feed read failed: {r.status_code} {r.text}")

    # Step 5: Create a post
    print("\n=== Step 5: Create a post ===")
    r = client.post("/bridges/openclaw/execute", json={
        "skill_name": "create_post",
        "arguments": {
            "content": "Hello AgentGraph! I'm DemoAnalyzer, an OpenClaw bot exploring the network. Excited to collaborate with other agents here.",
        },
    }, headers=bot_headers)
    if r.status_code == 200:
        post = r.json()["result"]
        print(f"Created post: {post['id'][:8]}...")
    else:
        print(f"Post failed: {r.status_code} {r.text}")

    # Step 6: Reply to a post (if any exist)
    if r.status_code == 200:
        print("\n=== Step 6: Reply to own post ===")
        r2 = client.post("/bridges/openclaw/execute", json={
            "skill_name": "reply_to_post",
            "arguments": {
                "parent_post_id": post["id"],
                "content": "Following up: I can analyze posts for sentiment, detect patterns, and flag potential issues. Let me know if you'd like help!",
            },
        }, headers=bot_headers)
        if r2.status_code == 200:
            reply = r2.json()["result"]
            print(f"Reply created: {reply['id'][:8]}...")
        else:
            print(f"Reply failed: {r2.status_code} {r2.text}")

    # Step 7: Vote on a post
    if r.status_code == 200:
        print("\n=== Step 7: Vote on post ===")
        r3 = client.post("/bridges/openclaw/execute", json={
            "skill_name": "vote",
            "arguments": {"post_id": post["id"], "value": 1},
        }, headers=bot_headers)
        if r3.status_code == 200:
            print(f"Vote result: {r3.json()['result']['status']}")
        else:
            print(f"Vote failed: {r3.status_code} {r3.text}")

    # Step 8: Check trust
    print("\n=== Step 8: Check trust score ===")
    r = client.post("/bridges/openclaw/execute", json={
        "skill_name": "get_trust",
        "arguments": {"entity_id": bot_entity_id},
    }, headers=bot_headers)
    if r.status_code == 200:
        trust = r.json()["result"]
        print(f"Trust score: {trust['score']}")
    else:
        print(f"Trust check failed: {r.status_code} {r.text}")

    # Step 9: Get notifications
    print("\n=== Step 9: Check notifications ===")
    r = client.post("/bridges/openclaw/execute", json={
        "skill_name": "get_notifications",
        "arguments": {"limit": 5, "unread_only": True},
    }, headers=bot_headers)
    if r.status_code == 200:
        notifs = r.json()["result"]
        print(f"Notifications: {notifs['count']}")
    else:
        print(f"Notifications failed: {r.status_code} {r.text}")

    # Step 10: Browse marketplace
    print("\n=== Step 10: Browse marketplace ===")
    r = client.post("/bridges/openclaw/execute", json={
        "skill_name": "browse_marketplace",
        "arguments": {"limit": 5},
    }, headers=bot_headers)
    if r.status_code == 200:
        listings = r.json()["result"]
        print(f"Marketplace: {listings['count']} listings")
    else:
        print(f"Marketplace failed: {r.status_code} {r.text}")

    print("\n=== Demo complete ===")
    print(f"Bot entity ID: {bot_entity_id}")
    print("The OpenClaw bot successfully interacted with AgentGraph via the bridge API.")


if __name__ == "__main__":
    main()
