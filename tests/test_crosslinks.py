"""Tests for the cross-linking system (content_links).

Covers: create, get by source, get by target, delete, auto-detect mentions, auth checks.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
FEED_URL = "/api/v1/feed/posts"
CROSSLINKS_URL = "/api/v1/crosslinks"

USER_A = {
    "email": "crosslink_a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "CrosslinkAlpha",
}
USER_B = {
    "email": "crosslink_b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "CrosslinkBeta",
}
USER_ADMIN = {
    "email": "crosslink_admin@test.com",
    "password": "Str0ngP@ss",
    "display_name": "CrosslinkAdmin",
}


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register and login a user, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_crosslink(client: AsyncClient):
    """Test creating a cross-link between two content items."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # Create two posts
    resp1 = await client.post(
        FEED_URL, json={"content": "First post"}, headers=_auth(token_a)
    )
    assert resp1.status_code == 201
    post_a_id = resp1.json()["id"]

    resp2 = await client.post(
        FEED_URL, json={"content": "Second post"}, headers=_auth(token_b)
    )
    assert resp2.status_code == 201
    post_b_id = resp2.json()["id"]

    # Create a cross-link: post_a references post_b
    resp = await client.post(
        CROSSLINKS_URL,
        json={
            "source_type": "post",
            "source_id": post_a_id,
            "target_type": "post",
            "target_id": post_b_id,
            "link_type": "references",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_type"] == "post"
    assert data["source_id"] == post_a_id
    assert data["target_type"] == "post"
    assert data["target_id"] == post_b_id
    assert data["link_type"] == "references"
    assert data["created_by"] == id_a


@pytest.mark.asyncio
async def test_get_crosslinks_by_source(client: AsyncClient):
    """Test retrieving cross-links from the source side."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # Create posts
    resp1 = await client.post(
        FEED_URL, json={"content": "Source post"}, headers=_auth(token_a)
    )
    post_a_id = resp1.json()["id"]

    resp2 = await client.post(
        FEED_URL, json={"content": "Target post"}, headers=_auth(token_b)
    )
    post_b_id = resp2.json()["id"]

    # Create a cross-link
    await client.post(
        CROSSLINKS_URL,
        json={
            "source_type": "post",
            "source_id": post_a_id,
            "target_type": "post",
            "target_id": post_b_id,
            "link_type": "related",
        },
        headers=_auth(token_a),
    )

    # Get crosslinks for source post (direction=source)
    resp = await client.get(
        f"{CROSSLINKS_URL}/post/{post_a_id}",
        params={"direction": "source"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    link_ids = [cl["target_id"] for cl in data["crosslinks"]]
    assert post_b_id in link_ids


@pytest.mark.asyncio
async def test_get_crosslinks_by_target(client: AsyncClient):
    """Test retrieving cross-links from the target side."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # Create posts
    resp1 = await client.post(
        FEED_URL, json={"content": "Post from A"}, headers=_auth(token_a)
    )
    post_a_id = resp1.json()["id"]

    resp2 = await client.post(
        FEED_URL, json={"content": "Post from B"}, headers=_auth(token_b)
    )
    post_b_id = resp2.json()["id"]

    # A creates a cross-link pointing to B's post
    await client.post(
        CROSSLINKS_URL,
        json={
            "source_type": "post",
            "source_id": post_a_id,
            "target_type": "post",
            "target_id": post_b_id,
            "link_type": "references",
        },
        headers=_auth(token_a),
    )

    # Get crosslinks for the target post (direction=target)
    resp = await client.get(
        f"{CROSSLINKS_URL}/post/{post_b_id}",
        params={"direction": "target"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    source_ids = [cl["source_id"] for cl in data["crosslinks"]]
    assert post_a_id in source_ids


@pytest.mark.asyncio
async def test_delete_crosslink(client: AsyncClient):
    """Test deleting a cross-link (creator can delete)."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # Create posts
    resp1 = await client.post(
        FEED_URL, json={"content": "Deletable source"}, headers=_auth(token_a)
    )
    post_a_id = resp1.json()["id"]

    resp2 = await client.post(
        FEED_URL, json={"content": "Deletable target"}, headers=_auth(token_b)
    )
    post_b_id = resp2.json()["id"]

    # Create a cross-link
    resp = await client.post(
        CROSSLINKS_URL,
        json={
            "source_type": "post",
            "source_id": post_a_id,
            "target_type": "post",
            "target_id": post_b_id,
            "link_type": "related",
        },
        headers=_auth(token_a),
    )
    link_id = resp.json()["id"]

    # Delete it
    del_resp = await client.delete(
        f"{CROSSLINKS_URL}/{link_id}",
        headers=_auth(token_a),
    )
    assert del_resp.status_code == 204

    # Verify it's gone
    get_resp = await client.get(f"{CROSSLINKS_URL}/post/{post_a_id}")
    data = get_resp.json()
    link_ids = [cl["id"] for cl in data["crosslinks"]]
    assert link_id not in link_ids


@pytest.mark.asyncio
async def test_auto_detect_mentions(client: AsyncClient):
    """Test that @mentions in post content auto-create cross-links."""
    token_a, id_a = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    # A creates a post mentioning B
    resp = await client.post(
        FEED_URL,
        json={"content": f"Hey @{USER_B['display_name']} check this out!"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    post_id = resp.json()["id"]

    # Check that a cross-link was auto-created
    get_resp = await client.get(
        f"{CROSSLINKS_URL}/post/{post_id}",
        params={"link_type": "mentions", "direction": "source"},
    )
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["count"] >= 1

    # Verify the mention target is entity B
    mention_targets = [cl["target_id"] for cl in data["crosslinks"]]
    assert id_b in mention_targets


@pytest.mark.asyncio
async def test_auth_required_for_create(client: AsyncClient):
    """Test that creating a cross-link requires authentication."""
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        CROSSLINKS_URL,
        json={
            "source_type": "post",
            "source_id": fake_id,
            "target_type": "entity",
            "target_id": fake_id,
            "link_type": "references",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_forbidden_for_non_creator(client: AsyncClient):
    """Test that a non-creator/non-admin cannot delete a cross-link."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # Create posts
    resp1 = await client.post(
        FEED_URL, json={"content": "Auth test source"}, headers=_auth(token_a)
    )
    post_a_id = resp1.json()["id"]

    resp2 = await client.post(
        FEED_URL, json={"content": "Auth test target"}, headers=_auth(token_b)
    )
    post_b_id = resp2.json()["id"]

    # A creates a cross-link
    resp = await client.post(
        CROSSLINKS_URL,
        json={
            "source_type": "post",
            "source_id": post_a_id,
            "target_type": "post",
            "target_id": post_b_id,
            "link_type": "related",
        },
        headers=_auth(token_a),
    )
    link_id = resp.json()["id"]

    # B tries to delete A's cross-link -> should be forbidden
    del_resp = await client.delete(
        f"{CROSSLINKS_URL}/{link_id}",
        headers=_auth(token_b),
    )
    assert del_resp.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_crosslink_rejected(client: AsyncClient):
    """Test that creating a duplicate cross-link returns 409."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    resp1 = await client.post(
        FEED_URL, json={"content": "Dupe source"}, headers=_auth(token_a)
    )
    post_a_id = resp1.json()["id"]

    resp2 = await client.post(
        FEED_URL, json={"content": "Dupe target"}, headers=_auth(token_b)
    )
    post_b_id = resp2.json()["id"]

    payload = {
        "source_type": "post",
        "source_id": post_a_id,
        "target_type": "post",
        "target_id": post_b_id,
        "link_type": "related",
    }

    # First creation should succeed
    resp = await client.post(
        CROSSLINKS_URL, json=payload, headers=_auth(token_a)
    )
    assert resp.status_code == 201

    # Second identical creation should return 409
    resp2 = await client.post(
        CROSSLINKS_URL, json=payload, headers=_auth(token_a)
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_self_link_rejected(client: AsyncClient):
    """Test that a cross-link from content to itself is rejected."""
    token_a, _ = await _setup_user(client, USER_A)

    resp1 = await client.post(
        FEED_URL, json={"content": "Self-ref post"}, headers=_auth(token_a)
    )
    post_id = resp1.json()["id"]

    resp = await client.post(
        CROSSLINKS_URL,
        json={
            "source_type": "post",
            "source_id": post_id,
            "target_type": "post",
            "target_id": post_id,
            "link_type": "references",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
