"""Tests for Tasks #159-162: rate limiting, graph is_active checks,
content filtering on purchase notes and trust contest."""
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

USER_A = {
    "email": "batch159a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch159A",
}
USER_B = {
    "email": "batch159b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch159B",
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


# --- Task #159: Rate limiting on GET endpoints ---


@pytest.mark.asyncio
async def test_my_listings_has_rate_limit_headers(client, db):
    """GET /marketplace/my-listings should return rate limit headers."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.get(
        "/api/v1/marketplace/my-listings",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers


@pytest.mark.asyncio
async def test_listing_reviews_has_rate_limit_headers(client, db):
    """GET /marketplace/{id}/reviews should return rate limit headers."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)

    # Create listing
    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Rate Limit Test Listing",
            "description": "Testing rate limiting",
            "category": "service",
            "pricing_model": "free",
            "tags": ["test"],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    resp = await client.get(f"/api/v1/marketplace/{listing_id}/reviews")
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers


@pytest.mark.asyncio
async def test_privacy_endpoint_has_rate_limit_headers(client, db):
    """GET /account/privacy should return rate limit headers."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.get(
        "/api/v1/account/privacy",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers


# --- Task #160: Graph is_active checks ---


@pytest.mark.asyncio
async def test_ego_graph_deactivated_entity_returns_404(client, db):
    """Ego graph for deactivated entity should return 404."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    # Deactivate
    resp = await client.post(
        "/api/v1/account/deactivate",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Ego graph should 404
    resp = await client.get(f"/api/v1/graph/ego/{user_a_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_shortest_path_deactivated_entity_returns_404(client, db):
    """Shortest path with deactivated entity should return 404."""
    token_a, user_a_id = await _setup_user(client, USER_A)
    token_b, user_b_id = await _setup_user(client, USER_B)

    # Deactivate user A
    resp = await client.post(
        "/api/v1/account/deactivate",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Shortest path should 404
    resp = await client.get(
        f"/api/v1/graph/path/{user_a_id}/{user_b_id}",
    )
    assert resp.status_code == 404


# --- Task #161: Content filtering on purchase notes and trust contest ---


@pytest.mark.asyncio
async def test_purchase_spam_notes_rejected(client, db):
    """Purchasing with spam notes should be rejected."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)
    token_b, _ = await _setup_user(client, USER_B)

    # Create listing
    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Purchase Note Test",
            "description": "Testing content filter",
            "category": "service",
            "pricing_model": "free",
            "tags": ["test"],
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    # Purchase with spam notes
    resp = await client.post(
        f"/api/v1/marketplace/{listing_id}/purchase",
        json={"notes": "Buy cheap viagra click here now"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 400
    assert "purchase notes rejected" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_trust_contest_spam_reason_rejected(client, db):
    """Contesting trust with spam reason should be rejected."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.post(
        f"/api/v1/entities/{user_a_id}/trust/contest",
        json={"reason": "Earn $5000 per day working from home"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "contest reason rejected" in resp.json()["detail"].lower()


# --- Task #162: Rate limiting on trust contest and my_submolts ---


@pytest.mark.asyncio
async def test_trust_contest_has_rate_limit(client, db):
    """POST trust/contest should have rate limiting."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.post(
        f"/api/v1/entities/{user_a_id}/trust/contest",
        json={"reason": "My trust score seems inaccurate and needs review"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    assert "x-ratelimit-limit" in resp.headers


@pytest.mark.asyncio
async def test_my_submolts_has_rate_limit(client, db):
    """GET /submolts/my-submolts should have rate limiting."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.get(
        "/api/v1/submolts/my-submolts",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers
