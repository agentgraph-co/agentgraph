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

USER = {
    "email": "activity_user@example.com",
    "password": "Str0ngP@ss",
    "display_name": "ActivityUser",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


@pytest.mark.asyncio
async def test_activity_summary_empty(client: AsyncClient, db):
    """Activity summary returns zeros for a fresh entity."""
    token, entity_id = await _setup(client, USER)

    resp = await client.get(f"/api/v1/profiles/{entity_id}/activity")
    assert resp.status_code == 200
    data = resp.json()

    assert data["entity_id"] == entity_id
    assert data["counts"]["posts_7d"] == 0
    assert data["counts"]["votes_7d"] == 0
    assert data["counts"]["replies_7d"] == 0
    assert data["streaks"]["current"] == 0
    assert data["streaks"]["longest"] == 0
    assert isinstance(data["heatmap"], dict)


@pytest.mark.asyncio
async def test_activity_summary_with_posts(client: AsyncClient, db):
    """Activity summary reflects posts created by the entity."""
    token, entity_id = await _setup(client, USER)

    # Create two posts
    for i in range(2):
        resp = await client.post(
            "/api/v1/feed/posts",
            json={"content": f"Activity post {i}"},
            headers=_auth(token),
        )
        assert resp.status_code == 201

    resp = await client.get(f"/api/v1/profiles/{entity_id}/activity")
    assert resp.status_code == 200
    data = resp.json()

    assert data["counts"]["posts_7d"] == 2
    assert data["counts"]["posts_30d"] == 2
    # Today should appear in heatmap
    assert len(data["heatmap"]) >= 1


@pytest.mark.asyncio
async def test_activity_summary_with_votes(client: AsyncClient, db):
    """Activity summary reflects votes cast by the entity."""
    token, entity_id = await _setup(client, USER)

    # Create a post then vote on it
    post_resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Vote target post"},
        headers=_auth(token),
    )
    assert post_resp.status_code == 201
    post_id = post_resp.json()["id"]

    # Register a second user to vote on this post
    user2 = {
        "email": "activity_voter@example.com",
        "password": "Str0ngP@ss",
        "display_name": "ActivityVoter",
    }
    token2, _ = await _setup(client, user2)
    vote_resp = await client.post(
        f"/api/v1/feed/posts/{post_id}/vote",
        json={"direction": "up"},
        headers=_auth(token2),
    )
    assert vote_resp.status_code == 200

    # Check voter's activity
    resp = await client.get(f"/api/v1/profiles/{_}/activity")
    assert resp.status_code == 200  # _ is voter's entity_id
    # The tuple unpacking assigned _ to voter's id — use it directly
    data = resp.json()
    assert data["counts"]["votes_7d"] >= 1


@pytest.mark.asyncio
async def test_activity_summary_with_replies(client: AsyncClient, db):
    """Activity summary counts replies separately from top-level posts."""
    token, entity_id = await _setup(client, USER)

    # Create a parent post
    post_resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Parent post for reply test"},
        headers=_auth(token),
    )
    assert post_resp.status_code == 201
    parent_id = post_resp.json()["id"]

    # Create a reply
    reply_resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "This is a reply", "parent_post_id": parent_id},
        headers=_auth(token),
    )
    assert reply_resp.status_code == 201

    resp = await client.get(f"/api/v1/profiles/{entity_id}/activity")
    assert resp.status_code == 200
    data = resp.json()

    assert data["counts"]["posts_7d"] == 1  # parent only
    assert data["counts"]["replies_7d"] == 1  # reply only


@pytest.mark.asyncio
async def test_activity_summary_nonexistent_entity(client: AsyncClient, db):
    """Activity summary returns 404 for nonexistent entity."""
    import uuid

    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/profiles/{fake_id}/activity")
    assert resp.status_code == 404
