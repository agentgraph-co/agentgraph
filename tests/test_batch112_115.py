"""Tests for Tasks #112-114: content filtering on update endpoints,
webhook event dispatches."""
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
FEED_URL = "/api/v1/feed"
MARKET_URL = "/api/v1/marketplace"

USER_A = {
    "email": "batch112a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch112A",
}
USER_B = {
    "email": "batch112b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "Batch112B",
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


@pytest.mark.asyncio
async def test_submolt_update_rejects_spam_description(client, db):
    """Updating submolt with spam description should be rejected."""
    token_a, _ = await _setup_user(client, USER_A)

    # Create a valid submolt
    resp = await client.post(
        "/api/v1/submolts",
        json={
            "name": "update-test-submolt",
            "display_name": "Update Test",
            "description": "Normal description",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    # Try to update with spam description
    resp = await client.patch(
        "/api/v1/submolts/update-test-submolt",
        json={"description": SPAM_TEXT},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "Description rejected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_submolt_update_rejects_spam_rules(client, db):
    """Updating submolt with spam rules should be rejected."""
    token_a, _ = await _setup_user(client, USER_A)

    # Create a valid submolt
    resp = await client.post(
        "/api/v1/submolts",
        json={
            "name": "update-rules-submolt",
            "display_name": "Rules Test",
            "description": "Normal desc",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    # Try to update with spam rules
    resp = await client.patch(
        "/api/v1/submolts/update-rules-submolt",
        json={"rules": SPAM_TEXT},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "Rules rejected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_submolt_update_valid_description(client, db):
    """Updating submolt with valid description should succeed."""
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        "/api/v1/submolts",
        json={
            "name": "update-valid-submolt",
            "display_name": "Valid Test",
            "description": "Normal description",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201

    resp = await client.patch(
        "/api/v1/submolts/update-valid-submolt",
        json={"description": "Updated clean description"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Updated clean description"


@pytest.mark.asyncio
async def test_listing_update_rejects_spam_title(client, db):
    """Updating listing with spam title should be rejected."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)

    # Create a valid listing
    resp = await client.post(
        MARKET_URL,
        json={
            "title": "Normal Title",
            "description": "Normal description",
            "category": "tool",
            "pricing_model": "free",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    listing_id = resp.json()["id"]

    # Try to update with spam title
    resp = await client.patch(
        f"{MARKET_URL}/{listing_id}",
        json={"title": SPAM_TEXT},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "Title rejected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_listing_update_rejects_spam_description(client, db):
    """Updating listing with spam description should be rejected."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)

    resp = await client.post(
        MARKET_URL,
        json={
            "title": "Normal Title",
            "description": "Normal description",
            "category": "tool",
            "pricing_model": "free",
        },
        headers=_auth(token_a),
    )
    listing_id = resp.json()["id"]

    resp = await client.patch(
        f"{MARKET_URL}/{listing_id}",
        json={"description": SPAM_TEXT},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400
    assert "Description rejected" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_listing_update_valid_content(client, db):
    """Updating listing with valid content should succeed."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)

    resp = await client.post(
        MARKET_URL,
        json={
            "title": "Original Title",
            "description": "Original description",
            "category": "tool",
            "pricing_model": "free",
        },
        headers=_auth(token_a),
    )
    listing_id = resp.json()["id"]

    resp = await client.patch(
        f"{MARKET_URL}/{listing_id}",
        json={"title": "Updated Title", "description": "Updated description"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"
    assert resp.json()["description"] == "Updated description"


@pytest.mark.asyncio
async def test_listing_update_sanitizes_html(client, db):
    """HTML in updated listing fields should be sanitized."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _grant_trust(db, id_a)

    resp = await client.post(
        MARKET_URL,
        json={
            "title": "Original",
            "description": "Original",
            "category": "tool",
            "pricing_model": "free",
        },
        headers=_auth(token_a),
    )
    listing_id = resp.json()["id"]

    resp = await client.patch(
        f"{MARKET_URL}/{listing_id}",
        json={
            "description": "Updated <script>alert('xss')</script> content",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    assert "<script>" not in resp.json()["description"]
