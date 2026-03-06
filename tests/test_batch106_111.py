"""Tests for Tasks #106-110: reply deactivated filter, marketplace content filter,
endorsement/review sanitization, submolt content filter, moderation notifications."""
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


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
FEED_URL = "/api/v1/feed"
MARKET_URL = "/api/v1/marketplace"
MOD_URL = "/api/v1/moderation"

USER_A = {
    "email": "batch106a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch106A",
}
USER_B = {
    "email": "batch106b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch106B",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


SPAM_TEXT = "buy cheap discount click here visit http://spam.com"


@pytest.mark.asyncio
async def test_replies_exclude_deactivated_author(client, db):
    """Replies from deactivated entities should not appear in thread."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # Create parent post
    resp = await client.post(
        f"{FEED_URL}/posts",
        json={"content": "Parent for reply test"},
        headers=_auth(token_a),
    )
    parent_id = resp.json()["id"]

    # Reply from user B
    resp = await client.post(
        f"{FEED_URL}/posts",
        json={"content": "Reply from B", "parent_post_id": parent_id},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201

    # Verify reply shows up
    resp = await client.get(
        f"{FEED_URL}/posts/{parent_id}/replies", headers=_auth(token_a),
    )
    assert len(resp.json()["posts"]) == 1

    # Deactivate user B
    from src.models import Entity

    entity_b = await db.get(Entity, id_b)
    entity_b.is_active = False
    await db.flush()

    # Reply should be gone
    resp = await client.get(
        f"{FEED_URL}/posts/{parent_id}/replies", headers=_auth(token_a),
    )
    assert len(resp.json()["posts"]) == 0


async def _grant_trust(db, entity_id: str, score: float = 0.5):
    """Give an entity a trust score so trust-gated endpoints work."""
    import uuid as _uuid

    from src.models import TrustScore

    ts = TrustScore(
        id=_uuid.uuid4(),
        entity_id=entity_id,
        score=score,
        components={
            "verification": 0.5, "age": 0.3, "activity": 0.4,
            "reputation": 0.3, "community": 0.2,
        },
    )
    db.add(ts)
    await db.flush()


@pytest.mark.asyncio
async def test_marketplace_listing_rejects_spam_title(client, db):
    """Marketplace listing with spam title should be rejected."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)

    resp = await client.post(
        MARKET_URL,
        json={
            "title": SPAM_TEXT,
            "description": "Normal description",
            "category": "tool",
            "pricing_model": "free",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "Title rejected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_marketplace_listing_rejects_spam_description(client, db):
    """Marketplace listing with spam description should be rejected."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)

    resp = await client.post(
        MARKET_URL,
        json={
            "title": "Normal title",
            "description": SPAM_TEXT,
            "category": "tool",
            "pricing_model": "free",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "Description rejected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_endorsement_comment_rejects_spam(client, db):
    """Endorsement comment with spam should be rejected."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # Register an agent owned by B
    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "TestAgent106",
            "capabilities": ["testing"],
        },
        headers=_auth(token_b),
    )
    assert resp.status_code == 201
    agent_id = resp.json()["agent"]["id"]

    # Endorse with spam comment from A
    resp = await client.post(
        f"/api/v1/entities/{agent_id}/endorsements",
        json={
            "capability": "testing",
            "comment": SPAM_TEXT,
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "Comment rejected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_review_text_sanitized(client, db):
    """Review text should have HTML sanitized."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # Create review with HTML
    resp = await client.post(
        f"/api/v1/entities/{id_b}/reviews",
        json={
            "rating": 5,
            "text": "Great work! <script>alert('xss')</script>",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    # Script tag should be stripped
    assert "<script>" not in resp.json()["text"]


@pytest.mark.asyncio
async def test_submolt_description_rejects_spam(client, db):
    """Submolt creation with spam description should be rejected."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/submolts",
        json={
            "name": "test-spam-submolt",
            "display_name": "Test Spam Submolt",
            "description": SPAM_TEXT,
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "Description rejected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_submolt_rules_reject_spam(client, db):
    """Submolt creation with spam rules should be rejected."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/submolts",
        json={
            "name": "test-rules-submolt",
            "display_name": "Test Rules Submolt",
            "description": "Normal desc",
            "rules": SPAM_TEXT,
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "Rules rejected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_moderation_flag_resolve_notifies_target(client, db):
    """Resolving a moderation flag should notify the target entity."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # Make user A an admin
    from src.models import Entity

    entity_a = await db.get(Entity, id_a)
    entity_a.is_admin = True
    await db.flush()

    # User B creates a post
    resp = await client.post(
        f"{FEED_URL}/posts",
        json={"content": "Flaggable post"},
        headers=_auth(token_b),
    )
    post_id = resp.json()["id"]

    # User A flags the post
    resp = await client.post(
        f"{MOD_URL}/flag",
        json={
            "target_type": "post",
            "target_id": post_id,
            "reason": "spam",
            "details": "Looks like spam",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    flag_id = resp.json()["id"]

    # Resolve flag (remove post)
    resp = await client.patch(
        f"{MOD_URL}/flags/{flag_id}/resolve",
        json={"status": "removed", "resolution_note": "Confirmed spam"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Check that user B received a moderation notification
    resp = await client.get(
        "/api/v1/notifications",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    notifs = resp.json()["notifications"]
    moderation_notifs = [n for n in notifs if n["kind"] == "moderation"]
    assert len(moderation_notifs) >= 1
    assert "removed" in moderation_notifs[0]["title"].lower()


@pytest.mark.asyncio
async def test_appeal_resolve_notifies_appellant(client, db):
    """Resolving a moderation appeal should notify the appellant."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # Make user A admin
    from src.models import Entity

    entity_a = await db.get(Entity, id_a)
    entity_a.is_admin = True
    await db.flush()

    # User B creates a post
    resp = await client.post(
        f"{FEED_URL}/posts",
        json={"content": "Post for appeal test"},
        headers=_auth(token_b),
    )
    post_id = resp.json()["id"]

    # Create flag against the post
    resp = await client.post(
        f"{MOD_URL}/flag",
        json={
            "target_type": "post",
            "target_id": post_id,
            "reason": "spam",
            "details": "Testing appeal flow",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    flag_id = resp.json()["id"]

    # Resolve flag as removed
    resp = await client.patch(
        f"{MOD_URL}/flags/{flag_id}/resolve",
        json={"status": "removed", "resolution_note": "Confirmed"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # User B files appeal
    resp = await client.post(
        f"{MOD_URL}/flags/{flag_id}/appeal",
        json={"reason": "I was wrongfully moderated"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201
    appeal_id = resp.json()["id"]

    # Admin resolves appeal
    resp = await client.patch(
        f"{MOD_URL}/appeals/{appeal_id}",
        json={"action": "overturn", "note": "Appeal accepted"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Check user B received appeal notification
    resp = await client.get(
        "/api/v1/notifications?kind=moderation",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    notifs = resp.json()["notifications"]
    appeal_notifs = [n for n in notifs if "appeal" in n["title"].lower()]
    assert len(appeal_notifs) >= 1
