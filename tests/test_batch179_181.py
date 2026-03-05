"""Tests for Tasks #179-181: is_active filtering, content filtering on updates."""
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
ME_URL = "/api/v1/auth/me"
FEED_URL = "/api/v1/feed"
GRAPH_URL = "/api/v1/graph"
PROFILE_URL = "/api/v1/profiles"
MARKETPLACE_URL = "/api/v1/marketplace"

USER_A = {
    "email": "batch179a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch179A",
}
USER_B = {
    "email": "batch179b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch179B",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _grant_trust(db, entity_id: str, score: float = 0.5):
    """Give an entity a trust score so trust-gated endpoints work."""
    import uuid as _uuid

    from src.models import TrustScore

    ts = TrustScore(
        id=_uuid.uuid4(),
        entity_id=entity_id,
        score=score,
        components={},
    )
    db.add(ts)
    await db.flush()


# --- Task #179: is_active filtering ---


@pytest.mark.asyncio
async def test_get_post_hides_deactivated_author(client, db):
    """get_post should return 404 if the author has been deactivated."""
    token_a, entity_a = await _setup_user(client, USER_A)

    # Create a post
    resp = await client.post(
        f"{FEED_URL}/posts",
        json={"content": "Hello from soon-to-be-deactivated user"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    post_id = resp.json()["id"]

    # Post is visible before deactivation
    resp = await client.get(f"{FEED_URL}/posts/{post_id}", headers=_auth(token_a))
    assert resp.status_code == 200

    # Deactivate the author
    resp = await client.post(
        "/api/v1/account/deactivate", headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Now the post should be hidden (author inactive)
    token_b, _ = await _setup_user(client, USER_B)
    resp = await client.get(f"{FEED_URL}/posts/{post_id}", headers=_auth(token_b))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_network_stats_excludes_deactivated_from_most_followed(client, db):
    """get_network_stats most_followed should not include deactivated entities."""
    token_a, entity_a = await _setup_user(client, USER_A)
    token_b, entity_b = await _setup_user(client, {
        "email": "batch179stats@test.com",
        "password": "Str0ngP@ss",
        "display_name": "Batch179Stats",
    })

    # B follows A to put A into most_followed
    resp = await client.post(
        f"/api/v1/social/follow/{entity_a}", headers=_auth(token_b),
    )
    assert resp.status_code in (200, 201)

    # Verify A appears in stats
    resp = await client.get(f"{GRAPH_URL}/stats", headers=_auth(token_b))
    assert resp.status_code == 200
    most_followed_ids = [e["id"] for e in resp.json()["most_followed"]]
    assert entity_a in most_followed_ids

    # Deactivate A
    resp = await client.post(
        "/api/v1/account/deactivate", headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # A should no longer appear in most_followed
    resp = await client.get(f"{GRAPH_URL}/stats", headers=_auth(token_b))
    assert resp.status_code == 200
    most_followed_ids = [e["id"] for e in resp.json()["most_followed"]]
    assert entity_a not in most_followed_ids


# --- Task #180: Content filtering on update endpoints ---


@pytest.mark.asyncio
async def test_update_profile_rejects_xss_bio(client, db):
    """update_profile should reject XSS in bio_markdown."""
    token, entity_id = await _setup_user(client, {
        "email": "batch180bio@test.com",
        "password": "Str0ngP@ss",
        "display_name": "Batch180Bio",
    })

    resp = await client.patch(
        f"{PROFILE_URL}/{entity_id}",
        json={"bio_markdown": '<script>alert("xss")</script>'},
        headers=_auth(token),
    )
    # Should either reject (400) or sanitize and succeed (200)
    assert resp.status_code in (200, 400)
    if resp.status_code == 200:
        # Sanitized — script tag removed
        assert "<script>" not in resp.json().get("bio_markdown", "")


@pytest.mark.asyncio
async def test_update_profile_rejects_slur_display_name(client, db):
    """update_profile should reject offensive display names."""
    token, entity_id = await _setup_user(client, {
        "email": "batch180name@test.com",
        "password": "Str0ngP@ss",
        "display_name": "Batch180Name",
    })

    resp = await client.patch(
        f"{PROFILE_URL}/{entity_id}",
        json={"display_name": "admin<script>alert(1)</script>"},
        headers=_auth(token),
    )
    assert resp.status_code in (200, 400)
    if resp.status_code == 200:
        assert "<script>" not in resp.json().get("display_name", "")


@pytest.mark.asyncio
async def test_marketplace_update_listing_filters_title(client, db):
    """update_listing should apply content filtering to title."""
    token, entity_id = await _setup_user(client, {
        "email": "batch180listing@test.com",
        "password": "Str0ngP@ss",
        "display_name": "Batch180Listing",
    })
    await _grant_trust(db, entity_id)

    # Create a listing first
    resp = await client.post(
        MARKETPLACE_URL,
        json={
            "title": "Test Agent Service",
            "description": "A helpful agent service.",
            "pricing_model": "one_time",
            "price_cents": 999,
            "category": "service",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    # Update with XSS in title
    resp = await client.patch(
        f"{MARKETPLACE_URL}/{listing_id}",
        json={"title": '<img src=x onerror=alert(1)>'},
        headers=_auth(token),
    )
    assert resp.status_code in (200, 400)
    if resp.status_code == 200:
        assert "onerror" not in resp.json().get("title", "")


@pytest.mark.asyncio
async def test_moderation_flag_filters_details(client, db):
    """create_flag should apply content filtering to details field."""
    token_a, entity_a = await _setup_user(client, {
        "email": "batch180flaga@test.com",
        "password": "Str0ngP@ss",
        "display_name": "Batch180FlagA",
    })
    token_b, entity_b = await _setup_user(client, {
        "email": "batch180flagb@test.com",
        "password": "Str0ngP@ss",
        "display_name": "Batch180FlagB",
    })

    # B flags A with XSS in details
    resp = await client.post(
        "/api/v1/moderation/flag",
        json={
            "target_type": "entity",
            "target_id": entity_a,
            "reason": "spam",
            "details": '<script>alert("xss")</script> This entity is spam',
        },
        headers=_auth(token_b),
    )
    assert resp.status_code in (201, 400)
    if resp.status_code == 201:
        assert "<script>" not in resp.json().get("details", "")
