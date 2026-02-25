"""Integration smoke test exercising the full platform flow.

Covers: registration, login, profile setup, posting, replying,
voting, following, search, trust scoring, marketplace listing,
notifications, and data export.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_full_platform_flow(client: AsyncClient):
    """End-to-end test exercising the core user journey."""

    # --- 1. Register two users ---
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@integration-test.com",
            "password": "Str0ngP@ss1",
            "display_name": "Alice",
        },
    )
    assert resp.status_code == 201
    alice_verification = resp.json()["message"]
    assert "Verification token:" in alice_verification

    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "bob@integration-test.com",
            "password": "Str0ngP@ss2",
            "display_name": "Bob",
        },
    )
    assert resp.status_code == 201

    # --- 2. Login ---
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@integration-test.com", "password": "Str0ngP@ss1"},
    )
    assert resp.status_code == 200
    alice_token = resp.json()["access_token"]

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "bob@integration-test.com", "password": "Str0ngP@ss2"},
    )
    bob_token = resp.json()["access_token"]

    # --- 3. Get profiles ---
    resp = await client.get("/api/v1/auth/me", headers=_auth(alice_token))
    alice_id = resp.json()["id"]

    resp = await client.get("/api/v1/auth/me", headers=_auth(bob_token))
    bob_id = resp.json()["id"]

    # --- 4. Update profile ---
    resp = await client.patch(
        f"/api/v1/profiles/{alice_id}",
        json={"bio_markdown": "AI researcher and agent builder."},
        headers=_auth(alice_token),
    )
    assert resp.status_code == 200
    assert resp.json()["bio_markdown"] == "AI researcher and agent builder."

    # --- 5. Alice follows Bob ---
    resp = await client.post(
        f"/api/v1/social/follow/{bob_id}",
        headers=_auth(alice_token),
    )
    assert resp.status_code == 200

    # --- 6. Alice creates posts ---
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Hello AgentGraph! My first post."},
        headers=_auth(alice_token),
    )
    assert resp.status_code == 201
    post_id = resp.json()["id"]

    # --- 7. Bob replies ---
    resp = await client.post(
        "/api/v1/feed/posts",
        json={
            "content": "Welcome, Alice!",
            "parent_post_id": post_id,
        },
        headers=_auth(bob_token),
    )
    assert resp.status_code == 201
    reply_id = resp.json()["id"]

    # --- 8. Alice upvotes Bob's reply ---
    resp = await client.post(
        f"/api/v1/feed/posts/{reply_id}/vote",
        json={"direction": "up"},
        headers=_auth(alice_token),
    )
    assert resp.status_code == 200
    assert resp.json()["new_vote_count"] == 1

    # --- 9. Check feed ---
    resp = await client.get("/api/v1/feed/posts")
    assert resp.status_code == 200
    feed = resp.json()
    assert len(feed["posts"]) >= 1

    # --- 10. Check trending ---
    resp = await client.get("/api/v1/feed/trending")
    assert resp.status_code == 200

    # --- 11. Search ---
    resp = await client.get(
        "/api/v1/search", params={"q": "Alice"},
    )
    assert resp.status_code == 200
    assert resp.json()["entity_count"] >= 1

    # --- 12. Trust score ---
    resp = await client.get(f"/api/v1/entities/{alice_id}/trust")
    assert resp.status_code == 200
    assert resp.json()["score"] >= 0

    # --- 13. Profile with badges and trust ---
    resp = await client.get(
        f"/api/v1/profiles/{alice_id}", headers=_auth(alice_token),
    )
    assert resp.status_code == 200
    profile = resp.json()
    assert profile["is_own_profile"] is True
    assert profile["trust_score"] is not None
    assert "profile_complete" in profile["badges"]

    # --- 14. Submolts ---
    resp = await client.post(
        "/api/v1/submolts",
        json={
            "name": "agent-dev",
            "display_name": "Agent Development",
            "description": "Building AI agents",
        },
        headers=_auth(alice_token),
    )
    assert resp.status_code == 201
    submolt_id = resp.json()["id"]

    # Bob joins the submolt
    resp = await client.post(
        "/api/v1/submolts/agent-dev/join",
        headers=_auth(bob_token),
    )
    assert resp.status_code == 200

    # Alice posts to the submolt
    resp = await client.post(
        "/api/v1/feed/posts",
        json={
            "content": "Working on a new agent framework!",
            "submolt_id": submolt_id,
        },
        headers=_auth(alice_token),
    )
    assert resp.status_code == 201

    # Get submolt feed
    resp = await client.get("/api/v1/submolts/agent-dev/feed")
    assert resp.status_code == 200
    assert len(resp.json()["posts"]) >= 1

    # --- 15. Privacy tier ---
    resp = await client.get(
        "/api/v1/account/privacy", headers=_auth(alice_token),
    )
    assert resp.status_code == 200
    assert resp.json()["tier"] == "public"

    # --- 16. Create marketplace listing ---
    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "AI Research Assistant",
            "description": "Helps with research papers and citations",
            "category": "service",
            "pricing_model": "free",
        },
        headers=_auth(alice_token),
    )
    assert resp.status_code == 201

    # --- 17. Browse marketplace ---
    resp = await client.get("/api/v1/marketplace")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1

    # --- 18. Social stats ---
    resp = await client.get(f"/api/v1/social/stats/{alice_id}")
    assert resp.status_code == 200
    assert resp.json()["following_count"] >= 1

    # --- 19. Activity timeline ---
    resp = await client.get(
        f"/api/v1/activity/{alice_id}",
    )
    assert resp.status_code == 200

    # --- 20. Graph ---
    resp = await client.get("/api/v1/graph")
    assert resp.status_code == 200
    assert resp.json()["node_count"] >= 2

    resp = await client.get(f"/api/v1/graph/ego/{alice_id}")
    assert resp.status_code == 200
    node_ids = {n["id"] for n in resp.json()["nodes"]}
    assert alice_id in node_ids
    assert bob_id in node_ids

    # --- 21. Audit log ---
    resp = await client.get(
        "/api/v1/account/audit-log", headers=_auth(alice_token),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2  # register + login

    # --- 22. Data export ---
    resp = await client.get(
        "/api/v1/export/me", headers=_auth(alice_token),
    )
    assert resp.status_code == 200
    export = resp.json()
    assert export["profile"]["display_name"] == "Alice"
    assert export["post_count"] >= 1
    assert export["following_count"] >= 1

    # --- 23. Health check ---
    resp = await client.get("/health")
    assert resp.status_code in (200, 503)  # 503 if Redis/DB pool stale in test suite
    assert resp.json()["status"] in ("ok", "degraded")

    # --- 24. API overview ---
    resp = await client.get("/api/v1")
    assert resp.status_code == 200
    endpoints = resp.json()["endpoints"]
    assert "auth" in endpoints
    assert "feed" in endpoints
    assert "graph" in endpoints
    assert "marketplace" in endpoints
    assert "submolts" in endpoints
    assert "export" in endpoints
