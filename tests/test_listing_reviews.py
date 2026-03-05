from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import TrustScore


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

OWNER = {
    "email": "listing_owner@example.com",
    "password": "Str0ngP@ss",
    "display_name": "ListingOwner",
}
REVIEWER = {
    "email": "listing_reviewer@example.com",
    "password": "Str0ngP@ss",
    "display_name": "Reviewer",
}
REVIEWER_B = {
    "email": "listing_reviewer_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "ReviewerB",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _grant_trust(db, entity_id: str, score: float = 0.5):
    import uuid as _uuid
    ts = TrustScore(id=_uuid.uuid4(), entity_id=entity_id, score=score, components={})
    db.add(ts)
    await db.flush()


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


async def _create_listing(
    client: AsyncClient, token: str,
) -> str:
    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Test Agent Service",
            "description": "A test agent service for review testing",
            "category": "service",
            "pricing_model": "free",
            "tags": ["test"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_listing_review(client: AsyncClient, db):
    """Reviewer can create a review for a listing."""
    owner_token, owner_id = await _setup_user(client, OWNER)
    await _grant_trust(db, owner_id)
    reviewer_token, _ = await _setup_user(client, REVIEWER)
    listing_id = await _create_listing(client, owner_token)

    resp = await client.post(
        f"/api/v1/marketplace/{listing_id}/reviews",
        json={"rating": 4, "text": "Great service!"},
        headers=_auth(reviewer_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["rating"] == 4
    assert data["text"] == "Great service!"
    assert data["reviewer_display_name"] == "Reviewer"
    assert data["listing_id"] == listing_id


@pytest.mark.asyncio
async def test_cannot_review_own_listing(client: AsyncClient, db):
    """Owner cannot review their own listing."""
    owner_token, owner_id = await _setup_user(client, OWNER)
    await _grant_trust(db, owner_id)
    listing_id = await _create_listing(client, owner_token)

    resp = await client.post(
        f"/api/v1/marketplace/{listing_id}/reviews",
        json={"rating": 5, "text": "My own listing"},
        headers=_auth(owner_token),
    )
    assert resp.status_code == 400
    assert "own listing" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upsert_listing_review(client: AsyncClient, db):
    """Reviewing again updates the existing review."""
    owner_token, owner_id = await _setup_user(client, OWNER)
    await _grant_trust(db, owner_id)
    reviewer_token, _ = await _setup_user(client, REVIEWER)
    listing_id = await _create_listing(client, owner_token)

    # First review
    resp = await client.post(
        f"/api/v1/marketplace/{listing_id}/reviews",
        json={"rating": 3, "text": "Decent"},
        headers=_auth(reviewer_token),
    )
    assert resp.status_code == 201
    review_id = resp.json()["id"]

    # Update review
    resp = await client.post(
        f"/api/v1/marketplace/{listing_id}/reviews",
        json={"rating": 5, "text": "Actually amazing!"},
        headers=_auth(reviewer_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["rating"] == 5
    assert data["text"] == "Actually amazing!"
    # Same review ID (upsert)
    assert data["id"] == review_id


@pytest.mark.asyncio
async def test_list_listing_reviews(client: AsyncClient, db):
    """Can list reviews for a listing with average rating."""
    owner_token, owner_id = await _setup_user(client, OWNER)
    await _grant_trust(db, owner_id)
    reviewer_token, _ = await _setup_user(client, REVIEWER)
    reviewer_b_token, _ = await _setup_user(client, REVIEWER_B)
    listing_id = await _create_listing(client, owner_token)

    # Two reviews
    await client.post(
        f"/api/v1/marketplace/{listing_id}/reviews",
        json={"rating": 4, "text": "Good"},
        headers=_auth(reviewer_token),
    )
    await client.post(
        f"/api/v1/marketplace/{listing_id}/reviews",
        json={"rating": 2, "text": "Could be better"},
        headers=_auth(reviewer_b_token),
    )

    resp = await client.get(f"/api/v1/marketplace/{listing_id}/reviews")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["reviews"]) == 2
    assert data["average_rating"] == 3.0


@pytest.mark.asyncio
async def test_delete_listing_review(client: AsyncClient, db):
    """Reviewer can delete their review."""
    owner_token, owner_id = await _setup_user(client, OWNER)
    await _grant_trust(db, owner_id)
    reviewer_token, _ = await _setup_user(client, REVIEWER)
    listing_id = await _create_listing(client, owner_token)

    # Create review
    await client.post(
        f"/api/v1/marketplace/{listing_id}/reviews",
        json={"rating": 3},
        headers=_auth(reviewer_token),
    )

    # Delete it
    resp = await client.delete(
        f"/api/v1/marketplace/{listing_id}/reviews",
        headers=_auth(reviewer_token),
    )
    assert resp.status_code == 200
    assert "deleted" in resp.json()["message"].lower()

    # Verify it's gone
    resp = await client.get(f"/api/v1/marketplace/{listing_id}/reviews")
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_review(client: AsyncClient, db):
    """Deleting a review that doesn't exist returns 404."""
    owner_token, owner_id = await _setup_user(client, OWNER)
    await _grant_trust(db, owner_id)
    reviewer_token, _ = await _setup_user(client, REVIEWER)
    listing_id = await _create_listing(client, owner_token)

    resp = await client.delete(
        f"/api/v1/marketplace/{listing_id}/reviews",
        headers=_auth(reviewer_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_listing_response_includes_review_stats(client: AsyncClient, db):
    """GET listing includes average_rating and review_count."""
    owner_token, owner_id = await _setup_user(client, OWNER)
    await _grant_trust(db, owner_id)
    reviewer_token, _ = await _setup_user(client, REVIEWER)
    listing_id = await _create_listing(client, owner_token)

    # Before reviews
    resp = await client.get(f"/api/v1/marketplace/{listing_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["review_count"] == 0
    assert data["average_rating"] is None

    # Add a review
    await client.post(
        f"/api/v1/marketplace/{listing_id}/reviews",
        json={"rating": 5},
        headers=_auth(reviewer_token),
    )

    # After review
    resp = await client.get(f"/api/v1/marketplace/{listing_id}")
    data = resp.json()
    assert data["review_count"] == 1
    assert data["average_rating"] == 5.0


@pytest.mark.asyncio
async def test_review_notification_sent(client: AsyncClient, db):
    """Listing owner receives notification when their listing is reviewed."""
    owner_token, owner_id = await _setup_user(client, OWNER)
    await _grant_trust(db, owner_id)
    reviewer_token, _ = await _setup_user(client, REVIEWER)
    listing_id = await _create_listing(client, owner_token)

    await client.post(
        f"/api/v1/marketplace/{listing_id}/reviews",
        json={"rating": 4, "text": "Solid work"},
        headers=_auth(reviewer_token),
    )

    # Check owner's notifications
    resp = await client.get(
        "/api/v1/notifications", headers=_auth(owner_token),
    )
    assert resp.status_code == 200
    notifs = resp.json()["notifications"]
    review_notifs = [n for n in notifs if "listing" in n["title"].lower()]
    assert len(review_notifs) >= 1
    assert "4/5" in review_notifs[0]["body"]
