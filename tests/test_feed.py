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

USER = {
    "email": "feeder@example.com",
    "password": "Str0ngP@ss",
    "display_name": "Feeder",
}


async def _get_token(client: AsyncClient, user: dict | None = None) -> str:
    user = user or USER
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL,
        json={"email": user["email"], "password": user["password"]},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Post creation ---


@pytest.mark.asyncio
async def test_create_post(client: AsyncClient):
    token = await _get_token(client)
    resp = await client.post(
        POSTS_URL,
        json={"content": "Hello world!"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "Hello world!"
    assert data["vote_count"] == 0
    assert data["author"]["display_name"] == "Feeder"


@pytest.mark.asyncio
async def test_create_post_unauthenticated(client: AsyncClient):
    resp = await client.post(POSTS_URL, json={"content": "Nope"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_reply(client: AsyncClient):
    token = await _get_token(client)
    post_resp = await client.post(
        POSTS_URL,
        json={"content": "Parent"},
        headers=_auth(token),
    )
    post_id = post_resp.json()["id"]

    reply_resp = await client.post(
        POSTS_URL,
        json={"content": "Reply!", "parent_post_id": post_id},
        headers=_auth(token),
    )
    assert reply_resp.status_code == 201
    assert reply_resp.json()["parent_post_id"] == post_id


# --- Feed listing ---


@pytest.mark.asyncio
async def test_get_feed(client: AsyncClient):
    token = await _get_token(client)
    for i in range(5):
        await client.post(
            POSTS_URL,
            json={"content": f"Post {i}"},
            headers=_auth(token),
        )

    resp = await client.get(POSTS_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["posts"]) >= 5
    # All 5 posts should be present (other tests may add more)
    contents = {p["content"] for p in data["posts"]}
    assert {"Post 0", "Post 1", "Post 2", "Post 3", "Post 4"} <= contents


@pytest.mark.asyncio
async def test_feed_excludes_replies(client: AsyncClient):
    token = await _get_token(client)
    post_resp = await client.post(
        POSTS_URL,
        json={"content": "Parent"},
        headers=_auth(token),
    )
    post_id = post_resp.json()["id"]

    await client.post(
        POSTS_URL,
        json={"content": "Reply", "parent_post_id": post_id},
        headers=_auth(token),
    )

    resp = await client.get(POSTS_URL)
    posts = resp.json()["posts"]
    assert len(posts) >= 1  # At least the parent (other tests may add more)
    parent = next(p for p in posts if p["id"] == post_id)
    assert parent["reply_count"] == 1


@pytest.mark.asyncio
async def test_feed_pagination(client: AsyncClient):
    token = await _get_token(client)
    for i in range(25):
        await client.post(
            POSTS_URL,
            json={"content": f"Post {i}"},
            headers=_auth(token),
        )

    # First page
    resp = await client.get(f"{POSTS_URL}?limit=10")
    data = resp.json()
    assert len(data["posts"]) == 10
    assert data["next_cursor"] is not None

    # Second page
    resp2 = await client.get(f"{POSTS_URL}?limit=10&cursor={data['next_cursor']}")
    data2 = resp2.json()
    assert len(data2["posts"]) == 10

    # No overlap
    page1_ids = {p["id"] for p in data["posts"]}
    page2_ids = {p["id"] for p in data2["posts"]}
    assert page1_ids.isdisjoint(page2_ids)


# --- Get single post ---


@pytest.mark.asyncio
async def test_get_post(client: AsyncClient):
    token = await _get_token(client)
    create_resp = await client.post(
        POSTS_URL,
        json={"content": "Specific post"},
        headers=_auth(token),
    )
    post_id = create_resp.json()["id"]

    resp = await client.get(f"{POSTS_URL}/{post_id}")
    assert resp.status_code == 200
    assert resp.json()["content"] == "Specific post"


# --- Replies ---


@pytest.mark.asyncio
async def test_get_replies(client: AsyncClient):
    token = await _get_token(client)
    post_resp = await client.post(
        POSTS_URL,
        json={"content": "Parent"},
        headers=_auth(token),
    )
    post_id = post_resp.json()["id"]

    for i in range(3):
        await client.post(
            POSTS_URL,
            json={"content": f"Reply {i}", "parent_post_id": post_id},
            headers=_auth(token),
        )

    resp = await client.get(f"{POSTS_URL}/{post_id}/replies")
    assert resp.status_code == 200
    assert len(resp.json()["posts"]) == 3


# --- Voting ---


@pytest.mark.asyncio
async def test_upvote(client: AsyncClient):
    token = await _get_token(client)
    post_resp = await client.post(
        POSTS_URL,
        json={"content": "Vote me!"},
        headers=_auth(token),
    )
    post_id = post_resp.json()["id"]

    resp = await client.post(
        f"{POSTS_URL}/{post_id}/vote",
        json={"direction": "up"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["direction"] == "up"
    assert resp.json()["new_vote_count"] == 1


@pytest.mark.asyncio
async def test_downvote(client: AsyncClient):
    token = await _get_token(client)
    post_resp = await client.post(
        POSTS_URL,
        json={"content": "Downvote me"},
        headers=_auth(token),
    )
    post_id = post_resp.json()["id"]

    resp = await client.post(
        f"{POSTS_URL}/{post_id}/vote",
        json={"direction": "down"},
        headers=_auth(token),
    )
    assert resp.json()["new_vote_count"] == -1


@pytest.mark.asyncio
async def test_toggle_vote_off(client: AsyncClient):
    token = await _get_token(client)
    post_resp = await client.post(
        POSTS_URL,
        json={"content": "Toggle me"},
        headers=_auth(token),
    )
    post_id = post_resp.json()["id"]

    # Upvote
    await client.post(
        f"{POSTS_URL}/{post_id}/vote",
        json={"direction": "up"},
        headers=_auth(token),
    )
    # Upvote again = toggle off
    resp = await client.post(
        f"{POSTS_URL}/{post_id}/vote",
        json={"direction": "up"},
        headers=_auth(token),
    )
    assert resp.json()["direction"] == "none"
    assert resp.json()["new_vote_count"] == 0


@pytest.mark.asyncio
async def test_change_vote_direction(client: AsyncClient):
    token = await _get_token(client)
    post_resp = await client.post(
        POSTS_URL,
        json={"content": "Change vote"},
        headers=_auth(token),
    )
    post_id = post_resp.json()["id"]

    # Upvote
    await client.post(
        f"{POSTS_URL}/{post_id}/vote",
        json={"direction": "up"},
        headers=_auth(token),
    )
    # Change to downvote
    resp = await client.post(
        f"{POSTS_URL}/{post_id}/vote",
        json={"direction": "down"},
        headers=_auth(token),
    )
    assert resp.json()["direction"] == "down"
    assert resp.json()["new_vote_count"] == -1


@pytest.mark.asyncio
async def test_feed_shows_user_vote(client: AsyncClient):
    token = await _get_token(client)
    post_resp = await client.post(
        POSTS_URL,
        json={"content": "Voted post"},
        headers=_auth(token),
    )
    post_id = post_resp.json()["id"]

    await client.post(
        f"{POSTS_URL}/{post_id}/vote",
        json={"direction": "up"},
        headers=_auth(token),
    )

    resp = await client.get(POSTS_URL, headers=_auth(token))
    post = resp.json()["posts"][0]
    assert post["user_vote"] == "up"


# --- Delete ---


@pytest.mark.asyncio
async def test_delete_post(client: AsyncClient):
    token = await _get_token(client)
    post_resp = await client.post(
        POSTS_URL,
        json={"content": "Delete me"},
        headers=_auth(token),
    )
    post_id = post_resp.json()["id"]

    resp = await client.delete(f"{POSTS_URL}/{post_id}", headers=_auth(token))
    assert resp.status_code == 200

    # Should not appear in feed
    feed_resp = await client.get(POSTS_URL)
    assert all(p["id"] != post_id for p in feed_resp.json()["posts"])


@pytest.mark.asyncio
async def test_delete_other_user_post_fails(client: AsyncClient):
    token = await _get_token(client)
    post_resp = await client.post(
        POSTS_URL,
        json={"content": "Not yours"},
        headers=_auth(token),
    )
    post_id = post_resp.json()["id"]

    other = {
        "email": "other@feed.com",
        "password": "Str0ngP@ss",
        "display_name": "Other",
    }
    other_token = await _get_token(client, other)

    resp = await client.delete(
        f"{POSTS_URL}/{post_id}", headers=_auth(other_token)
    )
    assert resp.status_code == 403
