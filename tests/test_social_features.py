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
SOCIAL_URL = "/api/v1/social"
SUBMOLTS_URL = "/api/v1/submolts"

USER_A = {
    "email": "social_feat_a@example.com",
    "password": "Str0ngP@ss",
    "display_name": "SocialFeatA",
}
USER_B = {
    "email": "social_feat_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "SocialFeatB",
}
USER_C = {
    "email": "social_feat_c@example.com",
    "password": "Str0ngP@ss",
    "display_name": "SocialFeatC",
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


# --- Suggested Follows ---


@pytest.mark.asyncio
async def test_suggested_follows(client: AsyncClient):
    """Suggested follows returns entities not already followed."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)
    token_c, id_c = await _setup_user(client, USER_C)

    # A follows B
    await client.post(
        f"{SOCIAL_URL}/follow/{id_b}", headers=_auth(token_a),
    )

    # A asks for suggestions — should get C but not B or self
    resp = await client.get(
        f"{SOCIAL_URL}/suggested", headers=_auth(token_a),
    )
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]
    suggestion_ids = {s["id"] for s in suggestions}
    assert id_c in suggestion_ids
    assert id_b not in suggestion_ids
    assert id_a not in suggestion_ids


@pytest.mark.asyncio
async def test_suggested_follows_excludes_blocked(
    client: AsyncClient,
):
    """Suggested follows excludes blocked entities."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)
    token_c, id_c = await _setup_user(client, USER_C)

    # A blocks C
    await client.post(
        f"{SOCIAL_URL}/block/{id_c}", headers=_auth(token_a),
    )

    resp = await client.get(
        f"{SOCIAL_URL}/suggested", headers=_auth(token_a),
    )
    suggestion_ids = {s["id"] for s in resp.json()["suggestions"]}
    assert id_c not in suggestion_ids


# --- Post Flair ---


@pytest.mark.asyncio
async def test_create_post_with_flair(client: AsyncClient):
    """Posts can be created with flair."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        POSTS_URL,
        json={
            "content": "Is this a good approach?",
            "flair": "question",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert resp.json()["flair"] == "question"


@pytest.mark.asyncio
async def test_create_post_no_flair(client: AsyncClient):
    """Posts without flair have None."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        POSTS_URL,
        json={"content": "Regular post"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert resp.json()["flair"] is None


# --- Pin Posts ---


@pytest.mark.asyncio
async def test_pin_post_in_submolt(client: AsyncClient):
    """Submolt owner can pin a post."""
    token_a, _ = await _setup_user(client, USER_A)

    # Create submolt
    resp = await client.post(
        SUBMOLTS_URL,
        json={
            "name": "pin-test",
            "display_name": "Pin Test",
            "description": "Testing pinning",
        },
        headers=_auth(token_a),
    )
    submolt_id = resp.json()["id"]

    # Create a post in the submolt
    resp = await client.post(
        POSTS_URL,
        json={
            "content": "Pin this!",
            "submolt_id": submolt_id,
        },
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    # Pin it
    resp = await client.post(
        f"{SOCIAL_URL}/pin/{post_id}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert resp.json()["is_pinned"] is True

    # Unpin (toggle)
    resp = await client.post(
        f"{SOCIAL_URL}/pin/{post_id}",
        headers=_auth(token_a),
    )
    assert resp.json()["is_pinned"] is False


@pytest.mark.asyncio
async def test_pin_non_submolt_post_fails(client: AsyncClient):
    """Cannot pin a post that isn't in a submolt."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        POSTS_URL,
        json={"content": "Not in a submolt"},
        headers=_auth(token),
    )
    post_id = resp.json()["id"]

    resp = await client.post(
        f"{SOCIAL_URL}/pin/{post_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_pin_requires_moderator(client: AsyncClient):
    """Non-moderator cannot pin posts in a submolt."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # A creates submolt
    resp = await client.post(
        SUBMOLTS_URL,
        json={
            "name": "pin-mod-test",
            "display_name": "Pin Mod Test",
            "description": "Testing mod pinning",
        },
        headers=_auth(token_a),
    )
    submolt_id = resp.json()["id"]

    # B joins
    await client.post(
        f"{SUBMOLTS_URL}/pin-mod-test/join",
        headers=_auth(token_b),
    )

    # A posts
    resp = await client.post(
        POSTS_URL,
        json={
            "content": "Mod only pin",
            "submolt_id": submolt_id,
        },
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    # B (regular member) tries to pin — should fail
    resp = await client.post(
        f"{SOCIAL_URL}/pin/{post_id}",
        headers=_auth(token_b),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pinned_posts_appear_first_in_feed(
    client: AsyncClient,
):
    """Pinned posts appear before non-pinned in submolt feed."""
    token, _ = await _setup_user(client, USER_A)

    # Create submolt
    resp = await client.post(
        SUBMOLTS_URL,
        json={
            "name": "pin-order-test",
            "display_name": "Pin Order",
            "description": "Test ordering",
        },
        headers=_auth(token),
    )
    submolt_id = resp.json()["id"]

    # Create posts
    resp1 = await client.post(
        POSTS_URL,
        json={"content": "First post", "submolt_id": submolt_id},
        headers=_auth(token),
    )
    post_id1 = resp1.json()["id"]

    await client.post(
        POSTS_URL,
        json={"content": "Second post", "submolt_id": submolt_id},
        headers=_auth(token),
    )

    # Pin the first (older) post
    await client.post(
        f"{SOCIAL_URL}/pin/{post_id1}",
        headers=_auth(token),
    )

    # Check feed — pinned post should be first
    resp = await client.get(
        f"{SUBMOLTS_URL}/pin-order-test/feed",
        headers=_auth(token),
    )
    posts = resp.json()["posts"]
    assert len(posts) == 2
    assert posts[0]["id"] == post_id1  # pinned comes first
    assert posts[0]["is_pinned"] is True
