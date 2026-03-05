from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.main import app
from src.models import (
    EntityRelationship,
    FormalAttestation,
    Post,
    RelationshipType,
    Review,
)


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
    "email": "enhanced_a@example.com",
    "password": "Str0ngP@ss",
    "display_name": "EnhancedUserA",
}
USER_B = {
    "email": "enhanced_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "EnhancedUserB",
}
USER_C = {
    "email": "enhanced_c@example.com",
    "password": "Str0ngP@ss",
    "display_name": "EnhancedUserC",
}


async def _register_and_login(
    client: AsyncClient, user: dict,
) -> tuple[str, str]:
    """Register, login, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=user)
    login_resp = await client.post(
        LOGIN_URL,
        json={"email": user["email"], "password": user["password"]},
    )
    token = login_resp.json()["access_token"]
    me_resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    entity_id = me_resp.json()["id"]
    return token, entity_id


async def _create_review(
    db: AsyncSession,
    reviewer_id: uuid.UUID,
    target_id: uuid.UUID,
    rating: int,
    text: str | None = None,
) -> Review:
    review = Review(
        id=uuid.uuid4(),
        reviewer_entity_id=reviewer_id,
        target_entity_id=target_id,
        rating=rating,
        text=text,
    )
    db.add(review)
    await db.flush()
    return review


async def _create_attestation(
    db: AsyncSession,
    issuer_id: uuid.UUID,
    subject_id: uuid.UUID,
    attestation_type: str,
    evidence: str | None = None,
    expires_at: datetime | None = None,
    is_revoked: bool = False,
) -> FormalAttestation:
    att = FormalAttestation(
        id=uuid.uuid4(),
        issuer_entity_id=issuer_id,
        subject_entity_id=subject_id,
        attestation_type=attestation_type,
        evidence=evidence,
        expires_at=expires_at,
        is_revoked=is_revoked,
        revoked_at=datetime.now(timezone.utc) if is_revoked else None,
    )
    db.add(att)
    await db.flush()
    return att


# -----------------------------------------------------------------------
# Reviews endpoint
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reviews_empty(client: AsyncClient):
    """Reviews endpoint returns empty list for entity with no reviews."""
    _, entity_id = await _register_and_login(client, USER_A)

    resp = await client.get(f"/api/v1/profiles/{entity_id}/reviews")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reviews"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_reviews_with_data(client: AsyncClient, db: AsyncSession):
    """Reviews endpoint returns reviews with reviewer info."""
    _, a_id = await _register_and_login(client, USER_A)
    _, b_id = await _register_and_login(client, USER_B)
    _, c_id = await _register_and_login(client, USER_C)

    # Unique constraint: one review per (target, reviewer) pair
    await _create_review(db, uuid.UUID(b_id), uuid.UUID(a_id), 4, "Great!")
    await _create_review(db, uuid.UUID(c_id), uuid.UUID(a_id), 5, "Amazing!")

    resp = await client.get(f"/api/v1/profiles/{a_id}/reviews")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    assert len(data["reviews"]) >= 2
    # Both reviews present with reviewer info
    ratings = {r["rating"] for r in data["reviews"]}
    assert 4 in ratings
    assert 5 in ratings
    names = {r["reviewer_display_name"] for r in data["reviews"]}
    assert "EnhancedUserB" in names
    assert "EnhancedUserC" in names


@pytest.mark.asyncio
async def test_reviews_filter_by_rating(client: AsyncClient, db: AsyncSession):
    """Reviews endpoint respects min_rating / max_rating filters."""
    _, a_id = await _register_and_login(client, USER_A)
    _, b_id = await _register_and_login(client, USER_B)
    _, c_id = await _register_and_login(client, USER_C)

    # Unique constraint: one review per (target, reviewer) pair
    await _create_review(db, uuid.UUID(b_id), uuid.UUID(a_id), 2, "Meh")
    await _create_review(db, uuid.UUID(c_id), uuid.UUID(a_id), 5, "Wow")

    resp = await client.get(
        f"/api/v1/profiles/{a_id}/reviews?min_rating=4",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["reviews"][0]["rating"] == 5

    resp2 = await client.get(
        f"/api/v1/profiles/{a_id}/reviews?max_rating=3",
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["total"] == 1
    assert data2["reviews"][0]["rating"] == 2


@pytest.mark.asyncio
async def test_reviews_pagination(client: AsyncClient, db: AsyncSession):
    """Reviews endpoint supports limit and offset."""
    _, a_id = await _register_and_login(client, USER_A)

    # Create 5 distinct reviewers (unique constraint: one review per pair)
    reviewer_ids = []
    for i in range(5):
        user = {
            "email": f"reviewer_pag{i}@example.com",
            "password": "Str0ngP@ss",
            "display_name": f"Reviewer{i}",
        }
        _, rid = await _register_and_login(client, user)
        reviewer_ids.append(rid)

    for i, rid in enumerate(reviewer_ids):
        await _create_review(
            db, uuid.UUID(rid), uuid.UUID(a_id), (i % 5) + 1,
        )

    resp = await client.get(
        f"/api/v1/profiles/{a_id}/reviews?limit=2&offset=0",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["reviews"]) == 2


@pytest.mark.asyncio
async def test_reviews_entity_not_found(client: AsyncClient):
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/profiles/{fake_id}/reviews")
    assert resp.status_code == 404


# -----------------------------------------------------------------------
# Attestations endpoint
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attestations_empty(client: AsyncClient):
    """Attestations endpoint returns empty for entity with none."""
    _, entity_id = await _register_and_login(client, USER_A)

    resp = await client.get(f"/api/v1/profiles/{entity_id}/attestations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["received"] == []
    assert data["received_total"] == 0
    assert data["issued"] == []
    assert data["issued_total"] == 0


@pytest.mark.asyncio
async def test_attestations_received_and_issued(
    client: AsyncClient, db: AsyncSession,
):
    """Attestations endpoint separates received and issued."""
    _, a_id = await _register_and_login(client, USER_A)
    _, b_id = await _register_and_login(client, USER_B)

    # B attests about A (A receives, B issues)
    await _create_attestation(
        db, uuid.UUID(b_id), uuid.UUID(a_id), "identity_verified",
    )

    # Check A's attestations
    resp_a = await client.get(f"/api/v1/profiles/{a_id}/attestations")
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["received_total"] == 1
    assert data_a["issued_total"] == 0
    assert data_a["received"][0]["attestation_type"] == "identity_verified"
    assert data_a["received"][0]["issuer_display_name"] == "EnhancedUserB"

    # Check B's attestations
    resp_b = await client.get(f"/api/v1/profiles/{b_id}/attestations")
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["received_total"] == 0
    assert data_b["issued_total"] == 1
    assert data_b["issued"][0]["attestation_type"] == "identity_verified"


@pytest.mark.asyncio
async def test_attestations_excludes_revoked_by_default(
    client: AsyncClient, db: AsyncSession,
):
    """Revoked attestations are excluded unless include_revoked=true."""
    _, a_id = await _register_and_login(client, USER_A)
    _, b_id = await _register_and_login(client, USER_B)

    await _create_attestation(
        db, uuid.UUID(b_id), uuid.UUID(a_id),
        "capability_certified", is_revoked=True,
    )

    resp = await client.get(f"/api/v1/profiles/{a_id}/attestations")
    assert resp.status_code == 200
    assert resp.json()["received_total"] == 0

    resp2 = await client.get(
        f"/api/v1/profiles/{a_id}/attestations?include_revoked=true",
    )
    assert resp2.status_code == 200
    assert resp2.json()["received_total"] == 1


@pytest.mark.asyncio
async def test_attestations_excludes_expired_by_default(
    client: AsyncClient, db: AsyncSession,
):
    """Expired attestations are excluded unless include_expired=true."""
    _, a_id = await _register_and_login(client, USER_A)
    _, b_id = await _register_and_login(client, USER_B)

    past = datetime.now(timezone.utc) - timedelta(days=1)
    await _create_attestation(
        db, uuid.UUID(b_id), uuid.UUID(a_id),
        "security_audited", expires_at=past,
    )

    resp = await client.get(f"/api/v1/profiles/{a_id}/attestations")
    assert resp.status_code == 200
    assert resp.json()["received_total"] == 0

    resp2 = await client.get(
        f"/api/v1/profiles/{a_id}/attestations?include_expired=true",
    )
    assert resp2.status_code == 200
    assert resp2.json()["received_total"] == 1


@pytest.mark.asyncio
async def test_attestations_filter_by_type(
    client: AsyncClient, db: AsyncSession,
):
    """Attestation type filter works correctly."""
    _, a_id = await _register_and_login(client, USER_A)
    _, b_id = await _register_and_login(client, USER_B)

    await _create_attestation(
        db, uuid.UUID(b_id), uuid.UUID(a_id), "identity_verified",
    )
    await _create_attestation(
        db, uuid.UUID(b_id), uuid.UUID(a_id), "security_audited",
    )

    resp = await client.get(
        f"/api/v1/profiles/{a_id}/attestations"
        "?attestation_type=identity_verified",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["received_total"] == 1
    assert data["received"][0]["attestation_type"] == "identity_verified"


@pytest.mark.asyncio
async def test_attestations_entity_not_found(client: AsyncClient):
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/profiles/{fake_id}/attestations")
    assert resp.status_code == 404


# -----------------------------------------------------------------------
# Trust badges endpoint
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trust_badges_empty(client: AsyncClient):
    """Trust badges returns email_verified status and no attestation badges."""
    _, entity_id = await _register_and_login(client, USER_A)

    resp = await client.get(f"/api/v1/profiles/{entity_id}/trust-badges")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == entity_id
    assert data["badges"] == []
    assert data["email_verified"] is False


@pytest.mark.asyncio
async def test_trust_badges_with_attestations(
    client: AsyncClient, db: AsyncSession,
):
    """Trust badges aggregates active attestations by type."""
    _, a_id = await _register_and_login(client, USER_A)
    _, b_id = await _register_and_login(client, USER_B)

    await _create_attestation(
        db, uuid.UUID(b_id), uuid.UUID(a_id), "identity_verified",
    )

    resp = await client.get(f"/api/v1/profiles/{a_id}/trust-badges")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["badges"]) == 1
    badge = data["badges"][0]
    assert badge["badge_type"] == "identity_verified"
    assert badge["count"] == 1
    assert badge["latest_attestation_date"] is not None


@pytest.mark.asyncio
async def test_trust_badges_excludes_revoked(
    client: AsyncClient, db: AsyncSession,
):
    """Trust badges does not include revoked attestations."""
    _, a_id = await _register_and_login(client, USER_A)
    _, b_id = await _register_and_login(client, USER_B)

    await _create_attestation(
        db, uuid.UUID(b_id), uuid.UUID(a_id),
        "capability_certified", is_revoked=True,
    )

    resp = await client.get(f"/api/v1/profiles/{a_id}/trust-badges")
    assert resp.status_code == 200
    assert resp.json()["badges"] == []


@pytest.mark.asyncio
async def test_trust_badges_entity_not_found(client: AsyncClient):
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/profiles/{fake_id}/trust-badges")
    assert resp.status_code == 404


# -----------------------------------------------------------------------
# Summary endpoint
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_basic(client: AsyncClient):
    """Summary endpoint returns all expected fields."""
    _, entity_id = await _register_and_login(client, USER_A)

    resp = await client.get(f"/api/v1/profiles/{entity_id}/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == entity_id
    assert data["display_name"] == "EnhancedUserA"
    assert data["trust_score"] is None
    assert data["review_count"] == 0
    assert data["average_rating"] is None
    assert data["attestation_counts"] == {}
    assert data["follower_count"] == 0
    assert data["following_count"] == 0
    assert data["post_count"] == 0
    assert data["member_since"] is not None


@pytest.mark.asyncio
async def test_summary_with_data(client: AsyncClient, db: AsyncSession):
    """Summary aggregates reviews, attestations, and social counts."""
    _, a_id = await _register_and_login(client, USER_A)
    _, b_id = await _register_and_login(client, USER_B)

    # Add a review
    await _create_review(db, uuid.UUID(b_id), uuid.UUID(a_id), 4, "Good")

    # Add an attestation
    await _create_attestation(
        db, uuid.UUID(b_id), uuid.UUID(a_id), "identity_verified",
    )

    # Add a follow relationship (B follows A)
    follow = EntityRelationship(
        id=uuid.uuid4(),
        source_entity_id=uuid.UUID(b_id),
        target_entity_id=uuid.UUID(a_id),
        type=RelationshipType.FOLLOW,
    )
    db.add(follow)
    await db.flush()

    # Add a post by A
    post = Post(
        id=uuid.uuid4(),
        author_entity_id=uuid.UUID(a_id),
        content="Hello world",
        is_hidden=False,
    )
    db.add(post)
    await db.flush()

    resp = await client.get(f"/api/v1/profiles/{a_id}/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["review_count"] == 1
    assert data["average_rating"] == 4.0
    assert data["attestation_counts"]["identity_verified"] == 1
    assert data["follower_count"] == 1
    assert data["post_count"] == 1


@pytest.mark.asyncio
async def test_summary_entity_not_found(client: AsyncClient):
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/profiles/{fake_id}/summary")
    assert resp.status_code == 404
