"""Tests for Tasks #116-117: check_content on profile update,
sanitize_html on listing reviews, WebSocket broadcasts."""
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
MARKET_URL = "/api/v1/marketplace"

USER_A = {
    "email": "batch116a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch116A",
}
USER_B = {
    "email": "batch116b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch116B",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


SPAM_TEXT = "buy cheap discount click here visit http://spam.com"


# --- Task #116: check_content on profile update ---


@pytest.mark.asyncio
async def test_profile_update_rejects_spam_bio(client, db):
    """Updating profile with spam bio should be rejected."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.patch(
        f"/api/v1/profiles/{user_a_id}",
        json={"bio_markdown": SPAM_TEXT},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "Bio rejected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_profile_update_rejects_spam_display_name(client, db):
    """Updating profile with spam display name should be rejected."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.patch(
        f"/api/v1/profiles/{user_a_id}",
        json={"display_name": SPAM_TEXT},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "Display name rejected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_profile_update_valid_bio(client, db):
    """Updating profile with clean bio should succeed."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.patch(
        f"/api/v1/profiles/{user_a_id}",
        json={"bio_markdown": "I am a helpful AI assistant."},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert resp.json()["bio_markdown"] == "I am a helpful AI assistant."


@pytest.mark.asyncio
async def test_profile_update_sanitizes_html_in_bio(client, db):
    """HTML in profile bio should be sanitized."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.patch(
        f"/api/v1/profiles/{user_a_id}",
        json={"bio_markdown": "Hello <script>alert('xss')</script> world"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert "<script>" not in resp.json()["bio_markdown"]


# --- Task #116: sanitize_html on listing reviews ---


@pytest.mark.asyncio
async def test_listing_review_sanitizes_html(client, db):
    """HTML in listing review text should be sanitized."""
    token_a, user_a_id = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # Create a listing as user A
    resp = await client.post(
        MARKET_URL,
        json={
            "title": "Test Listing",
            "description": "A test listing",
            "category": "tool",
            "pricing_model": "free",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    # Review as user B with HTML
    resp = await client.post(
        f"{MARKET_URL}/{listing_id}/reviews",
        json={
            "rating": 4,
            "text": "Great tool <script>alert('xss')</script> really",
        },
        headers=_auth(token_b),
    )
    assert resp.status_code == 201
    assert "<script>" not in resp.json()["text"]


@pytest.mark.asyncio
async def test_listing_review_rejects_spam(client, db):
    """Listing review with spam text should be rejected."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    resp = await client.post(
        MARKET_URL,
        json={
            "title": "Test Listing Spam Review",
            "description": "A test listing",
            "category": "tool",
            "pricing_model": "free",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    resp = await client.post(
        f"{MARKET_URL}/{listing_id}/reviews",
        json={
            "rating": 1,
            "text": SPAM_TEXT,
        },
        headers=_auth(token_b),
    )
    assert resp.status_code == 400
    assert "Content rejected" in resp.json()["detail"]


# --- Task #117: WebSocket broadcast added (verified via code) ---
# WebSocket broadcasts are best-effort (try/except pass), so we verify
# they don't break the main flow.


@pytest.mark.asyncio
async def test_endorsement_still_works_with_ws_broadcast(client, db):
    """Endorsement creation should succeed even with WS broadcast code."""
    token_a, user_a_id = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # Register an agent via user A
    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "WS Test Agent",
            "description": "An agent for WS test",
            "capabilities": ["testing"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    agent_id = resp.json()["agent"]["id"]

    # Endorse capability as user B
    resp = await client.post(
        f"/api/v1/entities/{agent_id}/endorsements",
        json={"capability": "testing", "comment": "Works well"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201
    assert resp.json()["capability"] == "testing"


@pytest.mark.asyncio
async def test_marketplace_purchase_still_works_with_ws_broadcast(client, db):
    """Marketplace purchase should succeed even with WS broadcast code."""
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # Create a free listing
    resp = await client.post(
        MARKET_URL,
        json={
            "title": "Free Tool WS",
            "description": "A free tool",
            "category": "tool",
            "pricing_model": "free",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    # Purchase as user B
    resp = await client.post(
        f"{MARKET_URL}/{listing_id}/purchase",
        json={},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "completed"
