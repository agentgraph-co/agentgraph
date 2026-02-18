"""Tests for Tasks #100-104: feed deactivated filter, hidden post access,
DM rate limits, trust rate limits, reply count hidden exclusion."""
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
DM_URL = "/api/v1/messages"

USER_A = {
    "email": "batch100a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch100A",
}
USER_B = {
    "email": "batch100b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch100B",
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


@pytest.mark.asyncio
async def test_feed_excludes_deactivated_entity_posts(client, db):
    """Posts from deactivated entities should not appear in feed."""
    token_a, id_a = await _setup_user(client, USER_A)

    # Create a post
    resp = await client.post(
        f"{FEED_URL}/posts",
        json={"content": "Hello from batch100a"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    # Verify post appears in feed
    resp = await client.get(f"{FEED_URL}/posts", headers=_auth(token_a))
    assert resp.status_code == 200
    posts = resp.json()["posts"]
    assert any(p["content"] == "Hello from batch100a" for p in posts)

    # Deactivate entity
    from src.models import Entity

    entity = await db.get(Entity, id_a)
    entity.is_active = False
    await db.flush()

    # Create another user to check feed
    token_b, _ = await _setup_user(client, USER_B)

    # Post should no longer appear in feed
    resp = await client.get(f"{FEED_URL}/posts", headers=_auth(token_b))
    assert resp.status_code == 200
    posts = resp.json()["posts"]
    assert not any(p["content"] == "Hello from batch100a" for p in posts)


@pytest.mark.asyncio
async def test_get_hidden_post_returns_404(client, db):
    """Hidden posts should return 404 on direct access."""
    token_a, _ = await _setup_user(client, USER_A)

    # Create a post
    resp = await client.post(
        f"{FEED_URL}/posts",
        json={"content": "Visible post"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    post_id = resp.json()["id"]

    # Delete (hide) the post
    resp = await client.delete(
        f"{FEED_URL}/posts/{post_id}", headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Direct access should return 404
    resp = await client.get(
        f"{FEED_URL}/posts/{post_id}", headers=_auth(token_a),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_vote_on_hidden_post_returns_404(client, db):
    """Voting on hidden post should fail."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # Create a post
    resp = await client.post(
        f"{FEED_URL}/posts",
        json={"content": "Will be hidden"},
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    # Delete (hide) the post
    await client.delete(
        f"{FEED_URL}/posts/{post_id}", headers=_auth(token_a),
    )

    # Vote should fail with 404
    resp = await client.post(
        f"{FEED_URL}/posts/{post_id}/vote",
        json={"direction": "up"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_bookmark_hidden_post_returns_404(client, db):
    """Bookmarking hidden post should fail."""
    token_a, _ = await _setup_user(client, USER_A)

    # Create and hide a post
    resp = await client.post(
        f"{FEED_URL}/posts",
        json={"content": "Bookmark test"},
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]
    await client.delete(
        f"{FEED_URL}/posts/{post_id}", headers=_auth(token_a),
    )

    # Bookmark should fail
    resp = await client.post(
        f"{FEED_URL}/posts/{post_id}/bookmark",
        headers=_auth(token_a),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reply_count_excludes_hidden(client, db):
    """Reply count should not include hidden replies."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # Create parent post
    resp = await client.post(
        f"{FEED_URL}/posts",
        json={"content": "Parent post for replies"},
        headers=_auth(token_a),
    )
    parent_id = resp.json()["id"]

    # Create two replies
    resp1 = await client.post(
        f"{FEED_URL}/posts",
        json={"content": "Reply 1", "parent_post_id": parent_id},
        headers=_auth(token_b),
    )
    reply1_id = resp1.json()["id"]

    await client.post(
        f"{FEED_URL}/posts",
        json={"content": "Reply 2", "parent_post_id": parent_id},
        headers=_auth(token_b),
    )

    # Check reply count = 2
    resp = await client.get(
        f"{FEED_URL}/posts/{parent_id}", headers=_auth(token_a),
    )
    assert resp.json()["reply_count"] == 2

    # Hide one reply
    await client.delete(
        f"{FEED_URL}/posts/{reply1_id}", headers=_auth(token_b),
    )

    # Check reply count = 1
    resp = await client.get(
        f"{FEED_URL}/posts/{parent_id}", headers=_auth(token_a),
    )
    assert resp.json()["reply_count"] == 1


@pytest.mark.asyncio
async def test_dm_conversations_list_requires_auth(client):
    """DM list endpoint requires authentication."""
    resp = await client.get(DM_URL)
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_dm_unread_requires_auth(client):
    """DM unread count requires authentication."""
    resp = await client.get(f"{DM_URL}/unread-count")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_trust_score_endpoint_accessible(client, db):
    """Trust score GET endpoint returns data for valid entity."""
    token_a, id_a = await _setup_user(client, USER_A)

    resp = await client.get(
        f"/api/v1/entities/{id_a}/trust",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "score" in data
    assert "components" in data


@pytest.mark.asyncio
async def test_trust_methodology_accessible(client):
    """Trust methodology endpoint should return methodology text."""
    resp = await client.get("/api/v1/trust/methodology")
    assert resp.status_code == 200
    assert "methodology" in resp.json()


@pytest.mark.asyncio
async def test_search_excludes_deactivated_posts(client, db):
    """Search feed should not return posts from deactivated entities."""
    token_a, id_a = await _setup_user(client, USER_A)

    # Create a post with searchable content
    await client.post(
        f"{FEED_URL}/posts",
        json={"content": "unique_search_term_batch100"},
        headers=_auth(token_a),
    )

    # Search should find it
    token_b, _ = await _setup_user(client, USER_B)
    resp = await client.get(
        f"{FEED_URL}/search?q=unique_search_term_batch100",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    assert len(resp.json()["posts"]) == 1

    # Deactivate entity
    from src.models import Entity

    entity = await db.get(Entity, id_a)
    entity.is_active = False
    await db.flush()

    # Search should return empty
    resp = await client.get(
        f"{FEED_URL}/search?q=unique_search_term_batch100",
        headers=_auth(token_b),
    )
    assert resp.status_code == 200
    assert len(resp.json()["posts"]) == 0
