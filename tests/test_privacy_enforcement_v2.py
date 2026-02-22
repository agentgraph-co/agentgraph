"""Privacy tier enforcement tests for feed, evolution, trust, graph, and notifications.

Tests that PRIVATE entities' content is hidden from non-followers,
visible to followers and self, and that PUBLIC entities are unaffected.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import Entity


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

# Unique emails per test module to avoid collisions
_SUFFIX = uuid.uuid4().hex[:6]

USER_PRIVATE = {
    "email": f"pv2_priv_{_SUFFIX}@example.com",
    "password": "Str0ngP@ss",
    "display_name": f"PrivUser{_SUFFIX}",
}
USER_PUBLIC = {
    "email": f"pv2_pub_{_SUFFIX}@example.com",
    "password": "Str0ngP@ss",
    "display_name": f"PubUser{_SUFFIX}",
}
USER_FOLLOWER = {
    "email": f"pv2_fol_{_SUFFIX}@example.com",
    "password": "Str0ngP@ss",
    "display_name": f"FollowerUser{_SUFFIX}",
}
USER_STRANGER = {
    "email": f"pv2_str_{_SUFFIX}@example.com",
    "password": "Str0ngP@ss",
    "display_name": f"StrangerUser{_SUFFIX}",
}
USER_VERIFIED = {
    "email": f"pv2_ver_{_SUFFIX}@example.com",
    "password": "Str0ngP@ss",
    "display_name": f"VerifiedUser{_SUFFIX}",
}
USER_VERIFIED_TARGET = {
    "email": f"pv2_vtgt_{_SUFFIX}@example.com",
    "password": "Str0ngP@ss",
    "display_name": f"VTgtUser{_SUFFIX}",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register, login, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


async def _set_privacy(client: AsyncClient, token: str, tier: str):
    """Set an entity's privacy tier."""
    resp = await client.put(
        "/api/v1/account/privacy",
        json={"tier": tier},
        headers=_auth(token),
    )
    assert resp.status_code == 200


async def _follow(client: AsyncClient, token: str, target_id: str):
    """Follow a target entity."""
    resp = await client.post(
        f"/api/v1/social/follow/{target_id}",
        headers=_auth(token),
    )
    assert resp.status_code in (200, 201, 409)  # 409 = already following


async def _create_post(client: AsyncClient, token: str, content: str) -> str:
    """Create a post and return its ID."""
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": content},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# --- Feed: posts list ---


@pytest.mark.asyncio
async def test_private_posts_excluded_from_feed_unauthenticated(client: AsyncClient):
    """Posts from PRIVATE entities should not appear for unauthenticated users."""
    token_priv, _ = await _setup_user(client, USER_PRIVATE)
    token_pub, _ = await _setup_user(client, USER_PUBLIC)

    await _create_post(client, token_priv, "Private secret content")
    await _create_post(client, token_pub, "Public visible content")

    await _set_privacy(client, token_priv, "private")

    resp = await client.get("/api/v1/feed/posts")
    assert resp.status_code == 200
    contents = [p["content"] for p in resp.json()["posts"]]
    assert "Public visible content" in contents
    assert "Private secret content" not in contents


@pytest.mark.asyncio
async def test_private_posts_excluded_from_feed_non_follower(client: AsyncClient):
    """Posts from PRIVATE entities should not appear for non-followers."""
    token_priv, _ = await _setup_user(client, USER_PRIVATE)
    token_stranger, _ = await _setup_user(client, USER_STRANGER)

    await _create_post(client, token_priv, "Non-follower hidden post")
    await _set_privacy(client, token_priv, "private")

    resp = await client.get(
        "/api/v1/feed/posts", headers=_auth(token_stranger),
    )
    assert resp.status_code == 200
    contents = [p["content"] for p in resp.json()["posts"]]
    assert "Non-follower hidden post" not in contents


@pytest.mark.asyncio
async def test_private_posts_visible_in_feed_for_follower(client: AsyncClient):
    """Posts from PRIVATE entities should be visible to followers."""
    token_priv, id_priv = await _setup_user(client, USER_PRIVATE)
    token_fol, _ = await _setup_user(client, USER_FOLLOWER)

    await _create_post(client, token_priv, "Follower can see this")
    await _set_privacy(client, token_priv, "private")
    await _follow(client, token_fol, id_priv)

    resp = await client.get(
        "/api/v1/feed/posts", headers=_auth(token_fol),
    )
    assert resp.status_code == 200
    contents = [p["content"] for p in resp.json()["posts"]]
    assert "Follower can see this" in contents


# --- Feed: direct post access ---


@pytest.mark.asyncio
async def test_direct_post_access_returns_403_non_follower(client: AsyncClient):
    """Accessing a PRIVATE entity's post directly should return 403 for non-followers."""
    token_priv, _ = await _setup_user(client, USER_PRIVATE)
    token_stranger, _ = await _setup_user(client, USER_STRANGER)

    post_id = await _create_post(client, token_priv, "Direct access test")
    await _set_privacy(client, token_priv, "private")

    resp = await client.get(
        f"/api/v1/feed/posts/{post_id}", headers=_auth(token_stranger),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_direct_post_access_returns_200_for_follower(client: AsyncClient):
    """Accessing a PRIVATE entity's post directly should return 200 for followers."""
    token_priv, id_priv = await _setup_user(client, USER_PRIVATE)
    token_fol, _ = await _setup_user(client, USER_FOLLOWER)

    post_id = await _create_post(client, token_priv, "Follower direct access")
    await _set_privacy(client, token_priv, "private")
    await _follow(client, token_fol, id_priv)

    resp = await client.get(
        f"/api/v1/feed/posts/{post_id}", headers=_auth(token_fol),
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "Follower direct access"


# --- Feed: replies ---


@pytest.mark.asyncio
async def test_private_replies_filtered_for_non_follower(client: AsyncClient):
    """Replies from PRIVATE entities should be hidden from non-followers."""
    token_pub, _ = await _setup_user(client, USER_PUBLIC)
    token_priv, _ = await _setup_user(client, USER_PRIVATE)
    token_stranger, _ = await _setup_user(client, USER_STRANGER)

    # Public user creates a top-level post
    parent_id = await _create_post(client, token_pub, "Parent post")

    # Private user replies
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Private reply here", "parent_post_id": parent_id},
        headers=_auth(token_priv),
    )
    assert resp.status_code == 201

    # Public user also replies
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Public reply here", "parent_post_id": parent_id},
        headers=_auth(token_pub),
    )
    assert resp.status_code == 201

    await _set_privacy(client, token_priv, "private")

    # Stranger fetches replies - should not see private reply
    resp = await client.get(
        f"/api/v1/feed/posts/{parent_id}/replies",
        headers=_auth(token_stranger),
    )
    assert resp.status_code == 200
    contents = [p["content"] for p in resp.json()["posts"]]
    assert "Public reply here" in contents
    assert "Private reply here" not in contents


# --- Evolution ---


@pytest.mark.asyncio
async def test_evolution_returns_403_for_private_entity_non_follower(
    client: AsyncClient,
):
    """Evolution timeline should return 403 for PRIVATE entity when requester is not a follower."""
    token_priv, id_priv = await _setup_user(client, USER_PRIVATE)
    token_stranger, _ = await _setup_user(client, USER_STRANGER)

    await _set_privacy(client, token_priv, "private")

    resp = await client.get(
        f"/api/v1/evolution/{id_priv}",
        headers=_auth(token_stranger),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_evolution_returns_200_for_private_entity_follower(
    client: AsyncClient,
):
    """Evolution timeline should return 200 for PRIVATE entity when requester follows."""
    token_priv, id_priv = await _setup_user(client, USER_PRIVATE)
    token_fol, _ = await _setup_user(client, USER_FOLLOWER)

    await _set_privacy(client, token_priv, "private")
    await _follow(client, token_fol, id_priv)

    resp = await client.get(
        f"/api/v1/evolution/{id_priv}",
        headers=_auth(token_fol),
    )
    assert resp.status_code == 200


# --- Trust ---


@pytest.mark.asyncio
async def test_trust_returns_403_for_private_entity_non_follower(
    client: AsyncClient,
):
    """Trust score should return 403 for PRIVATE entity when requester is not a follower."""
    token_priv, id_priv = await _setup_user(client, USER_PRIVATE)
    token_stranger, _ = await _setup_user(client, USER_STRANGER)

    await _set_privacy(client, token_priv, "private")

    resp = await client.get(
        f"/api/v1/entities/{id_priv}/trust",
        headers=_auth(token_stranger),
    )
    assert resp.status_code == 403


# --- Graph ---


@pytest.mark.asyncio
async def test_graph_export_excludes_private_entities(client: AsyncClient):
    """Full graph export should not include PRIVATE entities for unauthenticated users."""
    token_priv, id_priv = await _setup_user(client, USER_PRIVATE)
    token_pub, id_pub = await _setup_user(client, USER_PUBLIC)

    await _set_privacy(client, token_priv, "private")

    resp = await client.get("/api/v1/graph")
    assert resp.status_code == 200
    node_ids = [n["id"] for n in resp.json()["nodes"]]
    assert id_pub in node_ids
    assert id_priv not in node_ids


@pytest.mark.asyncio
async def test_ego_graph_returns_403_for_private_entity_non_follower(
    client: AsyncClient,
):
    """Ego graph of PRIVATE entity should return 403 for non-followers."""
    token_priv, id_priv = await _setup_user(client, USER_PRIVATE)
    token_stranger, _ = await _setup_user(client, USER_STRANGER)

    await _set_privacy(client, token_priv, "private")

    resp = await client.get(
        f"/api/v1/graph/ego/{id_priv}",
        headers=_auth(token_stranger),
    )
    assert resp.status_code == 403


# --- Notification masking ---


@pytest.mark.asyncio
async def test_notification_masks_private_entity_name(client: AsyncClient, db):
    """Notifications should mask PRIVATE entity display names for non-followers."""
    token_pub, id_pub = await _setup_user(client, USER_PUBLIC)
    token_priv, id_priv = await _setup_user(client, USER_PRIVATE)

    await _set_privacy(client, token_priv, "private")

    # Private user follows the public user -> creates a notification for public user
    await _follow(client, token_priv, id_pub)

    # Public user checks notifications
    resp = await client.get(
        "/api/v1/notifications",
        headers=_auth(token_pub),
    )
    assert resp.status_code == 200
    notifications = resp.json()["notifications"]

    # Look for the follow notification
    follow_notifs = [
        n for n in notifications
        if n["kind"] == "follow"
    ]
    if follow_notifs:
        # The private entity's name should be masked since public user
        # does NOT follow the private entity back
        body = follow_notifs[0]["body"]
        assert USER_PRIVATE["display_name"] not in body
        assert "Someone" in body


# --- PUBLIC entity unaffected ---


@pytest.mark.asyncio
async def test_public_entity_unaffected_by_all_filters(client: AsyncClient):
    """PUBLIC entities should be fully visible to everyone, always."""
    token_pub, id_pub = await _setup_user(client, USER_PUBLIC)

    post_id = await _create_post(client, token_pub, "Always visible post")

    # Unauthenticated feed
    resp = await client.get("/api/v1/feed/posts")
    assert resp.status_code == 200
    contents = [p["content"] for p in resp.json()["posts"]]
    assert "Always visible post" in contents

    # Direct post access
    resp = await client.get(f"/api/v1/feed/posts/{post_id}")
    assert resp.status_code == 200

    # Trust score
    resp = await client.get(f"/api/v1/entities/{id_pub}/trust")
    assert resp.status_code == 200

    # Evolution timeline
    resp = await client.get(f"/api/v1/evolution/{id_pub}")
    assert resp.status_code == 200

    # Graph export
    resp = await client.get("/api/v1/graph")
    assert resp.status_code == 200
    node_ids = [n["id"] for n in resp.json()["nodes"]]
    assert id_pub in node_ids


# --- VERIFIED tier ---


@pytest.mark.asyncio
async def test_verified_entity_accessible_to_verified_requester(
    client: AsyncClient, db,
):
    """VERIFIED-tier entity should be accessible to a verified (email_verified) requester."""
    token_tgt, id_tgt = await _setup_user(client, USER_VERIFIED_TARGET)
    token_viewer, id_viewer = await _setup_user(client, USER_VERIFIED)

    await _set_privacy(client, token_tgt, "verified")

    # Make the viewer verified
    entity = await db.get(Entity, id_viewer)
    entity.email_verified = True
    await db.flush()

    # Verified viewer can access trust score
    resp = await client.get(
        f"/api/v1/entities/{id_tgt}/trust",
        headers=_auth(token_viewer),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_verified_entity_blocked_for_unverified(client: AsyncClient):
    """VERIFIED-tier entity should be blocked for an unverified requester."""
    token_tgt, id_tgt = await _setup_user(client, USER_VERIFIED_TARGET)
    token_stranger, _ = await _setup_user(client, USER_STRANGER)

    await _set_privacy(client, token_tgt, "verified")

    # Unverified viewer cannot access trust score
    resp = await client.get(
        f"/api/v1/entities/{id_tgt}/trust",
        headers=_auth(token_stranger),
    )
    assert resp.status_code == 403


# --- Own data always accessible ---


@pytest.mark.asyncio
async def test_own_data_accessible_regardless_of_privacy_tier(client: AsyncClient):
    """Entities should always be able to access their own data, even when PRIVATE."""
    token_priv, id_priv = await _setup_user(client, USER_PRIVATE)

    post_id = await _create_post(client, token_priv, "My private post")
    await _set_privacy(client, token_priv, "private")

    # Own feed
    resp = await client.get(
        "/api/v1/feed/posts", headers=_auth(token_priv),
    )
    assert resp.status_code == 200
    contents = [p["content"] for p in resp.json()["posts"]]
    assert "My private post" in contents

    # Own direct post
    resp = await client.get(
        f"/api/v1/feed/posts/{post_id}", headers=_auth(token_priv),
    )
    assert resp.status_code == 200

    # Own trust score
    resp = await client.get(
        f"/api/v1/entities/{id_priv}/trust", headers=_auth(token_priv),
    )
    assert resp.status_code == 200

    # Own evolution timeline
    resp = await client.get(
        f"/api/v1/evolution/{id_priv}", headers=_auth(token_priv),
    )
    assert resp.status_code == 200

    # Own ego graph
    resp = await client.get(
        f"/api/v1/graph/ego/{id_priv}", headers=_auth(token_priv),
    )
    assert resp.status_code == 200
