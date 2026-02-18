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

USER_PRIVATE = {
    "email": "priv_enforce@example.com",
    "password": "Str0ngP@ss",
    "display_name": "PrivateEntity",
}
USER_VERIFIED = {
    "email": "priv_verified@example.com",
    "password": "Str0ngP@ss",
    "display_name": "VerifiedEntity",
}
USER_PUBLIC = {
    "email": "priv_public@example.com",
    "password": "Str0ngP@ss",
    "display_name": "PublicEntity",
}
USER_STRANGER = {
    "email": "priv_stranger@example.com",
    "password": "Str0ngP@ss",
    "display_name": "StrangerEntity",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


# --- Profile privacy ---


@pytest.mark.asyncio
async def test_private_profile_limited_for_stranger(client: AsyncClient):
    """Non-followers see limited profile for private entities."""
    token_priv, id_priv = await _setup_user(client, USER_PRIVATE)
    token_stranger, _ = await _setup_user(client, USER_STRANGER)

    # Set privacy to private
    await client.put(
        "/api/v1/account/privacy",
        json={"tier": "private"},
        headers=_auth(token_priv),
    )

    # Stranger views profile — should get limited data
    resp = await client.get(
        f"/api/v1/profiles/{id_priv}", headers=_auth(token_stranger),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "PrivateEntity"
    assert data["bio_markdown"] == ""  # hidden
    assert data["trust_score"] is None  # hidden
    assert data["post_count"] == 0  # hidden
    assert data["privacy_tier"] == "private"


@pytest.mark.asyncio
async def test_private_profile_full_for_follower(client: AsyncClient, db):
    """Followers see full profile for private entities."""
    token_priv, id_priv = await _setup_user(client, USER_PRIVATE)
    token_follower, _ = await _setup_user(client, USER_STRANGER)

    # Set privacy to private
    await client.put(
        "/api/v1/account/privacy",
        json={"tier": "private"},
        headers=_auth(token_priv),
    )

    # Update bio so we can test visibility
    await client.patch(
        f"/api/v1/profiles/{id_priv}",
        json={"bio_markdown": "My secret bio"},
        headers=_auth(token_priv),
    )

    # Follower follows the private user
    await client.post(
        f"/api/v1/social/follow/{id_priv}", headers=_auth(token_follower),
    )

    # Follower views profile — should see full data
    resp = await client.get(
        f"/api/v1/profiles/{id_priv}", headers=_auth(token_follower),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bio_markdown"] == "My secret bio"


@pytest.mark.asyncio
async def test_private_profile_full_for_self(client: AsyncClient):
    """Owners always see their own full profile."""
    token_priv, id_priv = await _setup_user(client, USER_PRIVATE)

    await client.put(
        "/api/v1/account/privacy",
        json={"tier": "private"},
        headers=_auth(token_priv),
    )
    await client.patch(
        f"/api/v1/profiles/{id_priv}",
        json={"bio_markdown": "My own bio"},
        headers=_auth(token_priv),
    )

    resp = await client.get(
        f"/api/v1/profiles/{id_priv}", headers=_auth(token_priv),
    )
    assert resp.status_code == 200
    assert resp.json()["bio_markdown"] == "My own bio"
    assert resp.json()["is_own_profile"] is True


@pytest.mark.asyncio
async def test_private_profile_limited_unauthenticated(client: AsyncClient):
    """Unauthenticated users see limited profile for private entities."""
    token_priv, id_priv = await _setup_user(client, USER_PRIVATE)

    await client.put(
        "/api/v1/account/privacy",
        json={"tier": "private"},
        headers=_auth(token_priv),
    )

    # No auth header
    resp = await client.get(f"/api/v1/profiles/{id_priv}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["bio_markdown"] == ""
    assert data["privacy_tier"] == "private"


# --- Verified tier ---


@pytest.mark.asyncio
async def test_verified_profile_limited_for_unverified(
    client: AsyncClient, db,
):
    """Unverified users see limited profile for verified-tier entities."""
    token_v, id_v = await _setup_user(client, USER_VERIFIED)
    token_stranger, _ = await _setup_user(client, USER_STRANGER)

    # Set privacy to verified
    await client.put(
        "/api/v1/account/privacy",
        json={"tier": "verified"},
        headers=_auth(token_v),
    )
    await client.patch(
        f"/api/v1/profiles/{id_v}",
        json={"bio_markdown": "Verified bio"},
        headers=_auth(token_v),
    )

    # Stranger (unverified) sees limited profile
    resp = await client.get(
        f"/api/v1/profiles/{id_v}", headers=_auth(token_stranger),
    )
    assert resp.status_code == 200
    assert resp.json()["bio_markdown"] == ""


@pytest.mark.asyncio
async def test_verified_profile_full_for_verified_user(
    client: AsyncClient, db,
):
    """Verified users see full profile for verified-tier entities."""
    token_v, id_v = await _setup_user(client, USER_VERIFIED)
    token_viewer, id_viewer = await _setup_user(client, USER_STRANGER)

    # Set target privacy to verified
    await client.put(
        "/api/v1/account/privacy",
        json={"tier": "verified"},
        headers=_auth(token_v),
    )
    await client.patch(
        f"/api/v1/profiles/{id_v}",
        json={"bio_markdown": "Verified bio"},
        headers=_auth(token_v),
    )

    # Make viewer verified
    from src.models import Entity
    entity = await db.get(Entity, id_viewer)
    entity.email_verified = True
    await db.flush()

    # Verified viewer sees full profile
    resp = await client.get(
        f"/api/v1/profiles/{id_v}", headers=_auth(token_viewer),
    )
    assert resp.status_code == 200
    assert resp.json()["bio_markdown"] == "Verified bio"


# --- Feed privacy ---


@pytest.mark.asyncio
async def test_private_posts_hidden_from_public_feed(client: AsyncClient):
    """Posts from private entities don't show in public feed."""
    token_priv, _ = await _setup_user(client, USER_PRIVATE)
    token_public, _ = await _setup_user(client, USER_PUBLIC)

    # Private user creates a post
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Secret post"},
        headers=_auth(token_priv),
    )
    # Public user creates a post
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Public post"},
        headers=_auth(token_public),
    )

    # Set private user's privacy
    await client.put(
        "/api/v1/account/privacy",
        json={"tier": "private"},
        headers=_auth(token_priv),
    )

    # Unauthenticated feed: only public posts
    resp = await client.get("/api/v1/feed/posts")
    assert resp.status_code == 200
    contents = [p["content"] for p in resp.json()["posts"]]
    assert "Public post" in contents
    assert "Secret post" not in contents


@pytest.mark.asyncio
async def test_private_posts_visible_to_follower(client: AsyncClient):
    """Posts from private entities visible to followers."""
    token_priv, id_priv = await _setup_user(client, USER_PRIVATE)
    token_follower, _ = await _setup_user(client, USER_STRANGER)

    # Create a post
    await client.post(
        "/api/v1/feed/posts",
        json={"content": "Follower-only post"},
        headers=_auth(token_priv),
    )

    # Go private
    await client.put(
        "/api/v1/account/privacy",
        json={"tier": "private"},
        headers=_auth(token_priv),
    )

    # Follow the private user
    await client.post(
        f"/api/v1/social/follow/{id_priv}",
        headers=_auth(token_follower),
    )

    # Follower sees the post
    resp = await client.get(
        "/api/v1/feed/posts", headers=_auth(token_follower),
    )
    contents = [p["content"] for p in resp.json()["posts"]]
    assert "Follower-only post" in contents


@pytest.mark.asyncio
async def test_own_private_posts_visible_in_feed(client: AsyncClient):
    """Own posts always visible regardless of privacy tier."""
    token_priv, _ = await _setup_user(client, USER_PRIVATE)

    await client.post(
        "/api/v1/feed/posts",
        json={"content": "My own private post"},
        headers=_auth(token_priv),
    )
    await client.put(
        "/api/v1/account/privacy",
        json={"tier": "private"},
        headers=_auth(token_priv),
    )

    resp = await client.get(
        "/api/v1/feed/posts", headers=_auth(token_priv),
    )
    contents = [p["content"] for p in resp.json()["posts"]]
    assert "My own private post" in contents
