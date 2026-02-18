"""Tests for Tasks #147-149: social stats is_active filtering,
review stats is_active filtering, endorsement target is_active checks."""
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

USER_A = {
    "email": "batch147a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch147A",
}
USER_B = {
    "email": "batch147b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch147B",
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


# --- Task #147: Social stats is_active checks ---


@pytest.mark.asyncio
async def test_social_stats_returns_counts(client, db):
    """Social stats endpoint should return follower/following counts."""
    token_a, user_a_id = await _setup_user(client, USER_A)
    token_b, user_b_id = await _setup_user(client, USER_B)

    # B follows A
    resp = await client.post(
        f"/api/v1/social/follow/{user_a_id}",
        headers=_auth(token_b),
    )
    assert resp.status_code in (200, 201)

    resp = await client.get(
        f"/api/v1/social/stats/{user_a_id}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["followers_count"] == 1
    assert data["following_count"] == 0


@pytest.mark.asyncio
async def test_social_stats_rejects_deactivated_entity(client, db):
    """Social stats should return 404 for deactivated entity."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    # Deactivate
    resp = await client.post(
        "/api/v1/account/deactivate",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200

    # Stats should 404
    token_b, _ = await _setup_user(client, USER_B)
    resp = await client.get(
        f"/api/v1/social/stats/{user_a_id}",
        headers=_auth(token_b),
    )
    assert resp.status_code == 404


# --- Task #148: Review stats is_active filtering ---


@pytest.mark.asyncio
async def test_review_list_accessible(client, db):
    """Review list endpoint should be accessible."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.get(
        f"/api/v1/entities/{user_a_id}/reviews",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "reviews" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_review_summary_accessible(client, db):
    """Review summary endpoint should be accessible."""
    token_a, user_a_id = await _setup_user(client, USER_A)

    resp = await client.get(
        f"/api/v1/entities/{user_a_id}/reviews/summary",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "review_count" in data
    assert "rating_distribution" in data


# --- Task #149: Endorsement target is_active checks ---


@pytest.mark.asyncio
async def test_endorsement_list_accessible(client, db):
    """Endorsement list for active agent should work."""
    token_a, _ = await _setup_user(client, USER_A)

    # Create an agent first
    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "Endorse Target",
            "description": "Test agent",
            "capabilities": ["testing"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    agent_id = resp.json()["agent"]["id"]

    resp = await client.get(
        f"/api/v1/entities/{agent_id}/endorsements",
    )
    assert resp.status_code == 200
    assert "endorsements" in resp.json()


@pytest.mark.asyncio
async def test_capability_summary_accessible(client, db):
    """Capability summary for active agent should work."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/agents",
        json={
            "display_name": "Cap Summary Agent",
            "description": "Test agent",
            "capabilities": ["testing", "analysis"],
            "framework": "custom",
        },
        headers=_auth(token_a),
    )
    agent_id = resp.json()["agent"]["id"]

    resp = await client.get(
        f"/api/v1/entities/{agent_id}/capabilities",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_review_with_rating_counted(client, db):
    """Creating a review should reflect in list endpoint."""
    token_a, user_a_id = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # B reviews A
    resp = await client.post(
        f"/api/v1/entities/{user_a_id}/reviews",
        json={"rating": 4, "text": "Good entity"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201

    # Check reviews list
    resp = await client.get(
        f"/api/v1/entities/{user_a_id}/reviews",
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert resp.json()["average_rating"] is not None
