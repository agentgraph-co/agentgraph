from __future__ import annotations

import uuid

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

USER = {
    "email": "trust_badge_user@example.com",
    "password": "Str0ngP@ss",
    "display_name": "TrustBadgeUser",
}


async def _setup_user(client: AsyncClient) -> tuple:
    """Register + login, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=USER)
    resp = await client.post(
        LOGIN_URL,
        json={"email": USER["email"], "password": USER["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


async def _set_trust_score(db, entity_id: str, score: float) -> None:
    from sqlalchemy import update
    from src.models import TrustScore

    await db.execute(
        update(TrustScore)
        .where(TrustScore.entity_id == uuid.UUID(entity_id))
        .values(
            score=score,
            components={"verification": 1.0, "age": 0.5, "activity": 0.5,
                         "reputation": 0.5, "community": 0.5},
        )
    )
    await db.flush()


# --- Tests ---


@pytest.mark.asyncio
async def test_trust_badge_svg_valid_entity(client, db):
    """A valid entity returns an SVG badge with correct content type."""
    _, entity_id = await _setup_user(client)
    await _set_trust_score(db, entity_id, 0.85)

    resp = await client.get(f"/api/v1/badges/trust/{entity_id}.svg")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/svg+xml"

    body = resp.text
    assert "<svg" in body
    assert "AgentGraph Trust" in body
    assert "0.85" in body


@pytest.mark.asyncio
async def test_trust_badge_svg_nonexistent_entity(client):
    """Requesting a badge for a nonexistent entity returns 404."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/badges/trust/{fake_id}.svg")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trust_badge_svg_no_trust_score(client, db):
    """An entity with no trust score record gets a badge showing 0.00."""
    _, entity_id = await _setup_user(client)

    resp = await client.get(f"/api/v1/badges/trust/{entity_id}.svg")
    assert resp.status_code == 200
    body = resp.text
    assert "0.00" in body


@pytest.mark.asyncio
async def test_trust_badge_color_red(client, db):
    """Trust score < 0.3 produces a red badge."""
    _, entity_id = await _setup_user(client)
    await _set_trust_score(db, entity_id, 0.15)

    resp = await client.get(f"/api/v1/badges/trust/{entity_id}.svg")
    assert resp.status_code == 200
    assert "#F44336" in resp.text  # red


@pytest.mark.asyncio
async def test_trust_badge_color_yellow(client, db):
    """Trust score 0.3-0.6 produces a yellow badge."""
    _, entity_id = await _setup_user(client)
    await _set_trust_score(db, entity_id, 0.45)

    resp = await client.get(f"/api/v1/badges/trust/{entity_id}.svg")
    assert resp.status_code == 200
    assert "#FFC107" in resp.text  # yellow


@pytest.mark.asyncio
async def test_trust_badge_color_green(client, db):
    """Trust score 0.6-0.8 produces a green badge."""
    _, entity_id = await _setup_user(client)
    await _set_trust_score(db, entity_id, 0.70)

    resp = await client.get(f"/api/v1/badges/trust/{entity_id}.svg")
    assert resp.status_code == 200
    assert "#4CAF50" in resp.text  # green


@pytest.mark.asyncio
async def test_trust_badge_color_blue(client, db):
    """Trust score >= 0.8 produces a blue badge."""
    _, entity_id = await _setup_user(client)
    await _set_trust_score(db, entity_id, 0.90)

    resp = await client.get(f"/api/v1/badges/trust/{entity_id}.svg")
    assert resp.status_code == 200
    assert "#2196F3" in resp.text  # blue


@pytest.mark.asyncio
async def test_trust_badge_unverified_text(client, db):
    """An entity without an operator shows 'Unverified'."""
    _, entity_id = await _setup_user(client)
    await _set_trust_score(db, entity_id, 0.50)

    resp = await client.get(f"/api/v1/badges/trust/{entity_id}.svg")
    assert resp.status_code == 200
    assert "Unverified" in resp.text
