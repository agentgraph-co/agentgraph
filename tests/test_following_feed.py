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
POSTS_URL = "/api/v1/feed/posts"
FOLLOWING_FEED_URL = "/api/v1/feed/following"
SOCIAL_URL = "/api/v1/social"
NOTIF_URL = "/api/v1/notifications"

USER_A = {
    "email": "feedfollowa@test.com",
    "password": "Str0ngP@ss",
    "display_name": "FeedFollowA",
}
USER_B = {
    "email": "feedfollowb@test.com",
    "password": "Str0ngP@ss",
    "display_name": "FeedFollowB",
}
USER_C = {
    "email": "feedfollowc@test.com",
    "password": "Str0ngP@ss",
    "display_name": "FeedFollowC",
}


async def _setup_user(
    client: AsyncClient, user: dict,
) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL,
        json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Following Feed ---


@pytest.mark.asyncio
async def test_following_feed_empty(client: AsyncClient):
    """Following feed returns empty when not following anyone."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.get(FOLLOWING_FEED_URL, headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()["posts"]) == 0


@pytest.mark.asyncio
async def test_following_feed_shows_followed_posts(
    client: AsyncClient,
):
    """Following feed shows posts from followed entities."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)
    token_c, _ = await _setup_user(client, USER_C)

    # A follows B but not C
    await client.post(
        f"{SOCIAL_URL}/follow/{id_b}", headers=_auth(token_a),
    )

    # B and C both post
    await client.post(
        POSTS_URL,
        json={"content": "Post from B"},
        headers=_auth(token_b),
    )
    await client.post(
        POSTS_URL,
        json={"content": "Post from C"},
        headers=_auth(token_c),
    )

    # A's following feed should only have B's post
    resp = await client.get(FOLLOWING_FEED_URL, headers=_auth(token_a))
    assert resp.status_code == 200
    posts = resp.json()["posts"]
    assert len(posts) == 1
    assert posts[0]["content"] == "Post from B"


@pytest.mark.asyncio
async def test_following_feed_requires_auth(client: AsyncClient):
    """Following feed requires authentication."""
    resp = await client.get(FOLLOWING_FEED_URL)
    assert resp.status_code in (401, 403)


# --- Notification Triggers ---


@pytest.mark.asyncio
async def test_follow_creates_notification(client: AsyncClient):
    """Following someone sends them a notification."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    await client.post(
        f"{SOCIAL_URL}/follow/{id_b}", headers=_auth(token_a),
    )

    # B should have a follow notification
    resp = await client.get(NOTIF_URL, headers=_auth(token_b))
    assert resp.status_code == 200
    notifs = resp.json()["notifications"]
    follow_notifs = [n for n in notifs if n["kind"] == "follow"]
    assert len(follow_notifs) >= 1
    assert "FeedFollowA" in follow_notifs[0]["body"]


@pytest.mark.asyncio
async def test_reply_creates_notification(client: AsyncClient):
    """Replying to a post notifies the original author."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # A creates a post
    resp = await client.post(
        POSTS_URL,
        json={"content": "Original post by A"},
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    # B replies
    await client.post(
        POSTS_URL,
        json={
            "content": "Great post!",
            "parent_post_id": post_id,
        },
        headers=_auth(token_b),
    )

    # A should have a reply notification
    resp = await client.get(NOTIF_URL, headers=_auth(token_a))
    notifs = resp.json()["notifications"]
    reply_notifs = [n for n in notifs if n["kind"] == "reply"]
    assert len(reply_notifs) >= 1
    assert "FeedFollowB" in reply_notifs[0]["body"]


@pytest.mark.asyncio
async def test_upvote_creates_notification(client: AsyncClient):
    """Upvoting a post notifies the author."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # A creates a post
    resp = await client.post(
        POSTS_URL,
        json={"content": "Voteable post"},
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    # B upvotes
    await client.post(
        f"{POSTS_URL}/{post_id}/vote",
        json={"direction": "up"},
        headers=_auth(token_b),
    )

    # A should have a vote notification
    resp = await client.get(NOTIF_URL, headers=_auth(token_a))
    notifs = resp.json()["notifications"]
    vote_notifs = [n for n in notifs if n["kind"] == "vote"]
    assert len(vote_notifs) >= 1
    assert "FeedFollowB" in vote_notifs[0]["body"]


@pytest.mark.asyncio
async def test_self_reply_no_notification(client: AsyncClient):
    """Replying to your own post doesn't create a notification."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        POSTS_URL,
        json={"content": "My post"},
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    # Reply to own post
    await client.post(
        POSTS_URL,
        json={
            "content": "My own reply",
            "parent_post_id": post_id,
        },
        headers=_auth(token_a),
    )

    # Should have no reply notifications
    resp = await client.get(NOTIF_URL, headers=_auth(token_a))
    notifs = resp.json()["notifications"]
    reply_notifs = [n for n in notifs if n["kind"] == "reply"]
    assert len(reply_notifs) == 0
