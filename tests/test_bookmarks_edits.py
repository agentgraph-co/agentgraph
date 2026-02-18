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
BOOKMARKS_URL = "/api/v1/feed/bookmarks"
LEADERBOARD_URL = "/api/v1/feed/leaderboard"
NOTIF_URL = "/api/v1/notifications"

USER_A = {
    "email": "bkedit_a@example.com",
    "password": "Str0ngP@ss",
    "display_name": "BkEditA",
}
USER_B = {
    "email": "bkedit_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "BkEditB",
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


# --- Bookmark Tests ---


@pytest.mark.asyncio
async def test_bookmark_toggle(client: AsyncClient):
    """Bookmarking a post toggles on and off."""
    token, _ = await _setup_user(client, USER_A)

    # Create a post
    resp = await client.post(
        POSTS_URL,
        json={"content": "Bookmark me"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    post_id = resp.json()["id"]

    # Bookmark it
    resp = await client.post(
        f"{POSTS_URL}/{post_id}/bookmark", headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["bookmarked"] is True

    # Unbookmark it
    resp = await client.post(
        f"{POSTS_URL}/{post_id}/bookmark", headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["bookmarked"] is False


@pytest.mark.asyncio
async def test_bookmarks_feed(client: AsyncClient):
    """Bookmarks feed returns bookmarked posts."""
    token, _ = await _setup_user(client, USER_A)

    # Create two posts
    await client.post(
        POSTS_URL,
        json={"content": "First post"},
        headers=_auth(token),
    )
    resp2 = await client.post(
        POSTS_URL,
        json={"content": "Second post"},
        headers=_auth(token),
    )
    post_id2 = resp2.json()["id"]

    # Bookmark only the second
    await client.post(
        f"{POSTS_URL}/{post_id2}/bookmark", headers=_auth(token),
    )

    # Bookmarks feed should have one post
    resp = await client.get(BOOKMARKS_URL, headers=_auth(token))
    assert resp.status_code == 200
    posts = resp.json()["posts"]
    assert len(posts) == 1
    assert posts[0]["id"] == post_id2
    assert posts[0]["is_bookmarked"] is True


@pytest.mark.asyncio
async def test_bookmark_nonexistent_post(client: AsyncClient):
    """Bookmarking a non-existent post returns 404."""
    token, _ = await _setup_user(client, USER_A)

    import uuid

    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"{POSTS_URL}/{fake_id}/bookmark", headers=_auth(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_bookmarks_feed_requires_auth(client: AsyncClient):
    """Bookmarks feed requires authentication."""
    resp = await client.get(BOOKMARKS_URL)
    assert resp.status_code in (401, 403)


# --- Post Editing Tests ---


@pytest.mark.asyncio
async def test_edit_post(client: AsyncClient):
    """Editing a post updates content and marks as edited."""
    token, _ = await _setup_user(client, USER_A)

    # Create
    resp = await client.post(
        POSTS_URL,
        json={"content": "Original content"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    post_id = resp.json()["id"]
    assert resp.json()["is_edited"] is False

    # Edit
    resp = await client.patch(
        f"{POSTS_URL}/{post_id}",
        json={"content": "Updated content"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "Updated content"
    assert resp.json()["is_edited"] is True


@pytest.mark.asyncio
async def test_edit_post_not_owner(client: AsyncClient):
    """Non-owner cannot edit a post."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # A creates
    resp = await client.post(
        POSTS_URL,
        json={"content": "A's post"},
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    # B tries to edit
    resp = await client.patch(
        f"{POSTS_URL}/{post_id}",
        json={"content": "Hacked!"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_edit_history(client: AsyncClient):
    """Edit history tracks all edits to a post."""
    token, _ = await _setup_user(client, USER_A)

    # Create
    resp = await client.post(
        POSTS_URL,
        json={"content": "Version 1"},
        headers=_auth(token),
    )
    post_id = resp.json()["id"]

    # Edit twice
    await client.patch(
        f"{POSTS_URL}/{post_id}",
        json={"content": "Version 2"},
        headers=_auth(token),
    )
    await client.patch(
        f"{POSTS_URL}/{post_id}",
        json={"content": "Version 3"},
        headers=_auth(token),
    )

    # Check edit history
    resp = await client.get(f"{POSTS_URL}/{post_id}/edits")
    assert resp.status_code == 200
    data = resp.json()
    assert data["edit_count"] == 2
    assert len(data["edits"]) == 2
    # Both edits should be present (order may vary in test transactions)
    prev_contents = {e["previous_content"] for e in data["edits"]}
    new_contents = {e["new_content"] for e in data["edits"]}
    assert "Version 1" in prev_contents
    assert "Version 2" in prev_contents | new_contents
    assert "Version 3" in new_contents


@pytest.mark.asyncio
async def test_edit_post_content_filter(client: AsyncClient):
    """Edited content is also checked by the content filter."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        POSTS_URL,
        json={"content": "Legit post"},
        headers=_auth(token),
    )
    post_id = resp.json()["id"]

    # Try to edit with spam
    resp = await client.patch(
        f"{POSTS_URL}/{post_id}",
        json={"content": "Buy cheap stuff click here http://spam.com"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "spam_pattern" in resp.json()["detail"]


# --- Mentions Tests ---


@pytest.mark.asyncio
async def test_mention_creates_notification(client: AsyncClient):
    """Mentioning another user sends them a notification."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # A mentions B by display_name
    resp = await client.post(
        POSTS_URL,
        json={"content": "Hey @BkEditB check this out!"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    # B should have a mention notification
    resp = await client.get(NOTIF_URL, headers=_auth(token_b))
    assert resp.status_code == 200
    notifs = resp.json()["notifications"]
    mention_notifs = [n for n in notifs if n["kind"] == "mention"]
    assert len(mention_notifs) >= 1
    assert "BkEditA" in mention_notifs[0]["body"]


@pytest.mark.asyncio
async def test_self_mention_no_notification(client: AsyncClient):
    """Mentioning yourself doesn't create a notification."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        POSTS_URL,
        json={"content": "Talking about @BkEditA (myself)"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    resp = await client.get(NOTIF_URL, headers=_auth(token_a))
    notifs = resp.json()["notifications"]
    mention_notifs = [n for n in notifs if n["kind"] == "mention"]
    assert len(mention_notifs) == 0


# --- Leaderboard Tests ---


@pytest.mark.asyncio
async def test_leaderboard_basic(client: AsyncClient):
    """Leaderboard returns contributors ordered by votes."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # A creates a post
    resp = await client.post(
        POSTS_URL,
        json={"content": "Popular post"},
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    # B upvotes A's post
    await client.post(
        f"{POSTS_URL}/{post_id}/vote",
        json={"direction": "up"},
        headers=_auth(token_b),
    )

    # Check leaderboard
    resp = await client.get(LEADERBOARD_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data["period"] == "all"
    assert len(data["leaders"]) >= 1
    # A should be ranked first (has 1 upvote)
    leader = data["leaders"][0]
    assert leader["display_name"] == "BkEditA"
    assert leader["total_votes"] >= 1


@pytest.mark.asyncio
async def test_leaderboard_period_filter(client: AsyncClient):
    """Leaderboard supports period filtering."""
    token_a, _ = await _setup_user(client, USER_A)

    await client.post(
        POSTS_URL,
        json={"content": "Recent post"},
        headers=_auth(token_a),
    )

    for period in ("day", "week", "month", "all"):
        resp = await client.get(
            LEADERBOARD_URL, params={"period": period},
        )
        assert resp.status_code == 200
        assert resp.json()["period"] == period


@pytest.mark.asyncio
async def test_leaderboard_limit(client: AsyncClient):
    """Leaderboard respects limit parameter."""
    resp = await client.get(
        LEADERBOARD_URL, params={"limit": 5},
    )
    assert resp.status_code == 200
    assert len(resp.json()["leaders"]) <= 5
