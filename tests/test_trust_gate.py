from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.main import app
from src.models import Entity, TrustScore


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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_user(
    client: AsyncClient,
    email: str,
    display_name: str,
    password: str = "Str0ngP@ss1!",
) -> tuple[str, str]:
    """Register, login, return (token, entity_id)."""
    await client.post(
        REGISTER_URL,
        json={"email": email, "password": password, "display_name": display_name},
    )
    resp = await client.post(
        LOGIN_URL, json={"email": email, "password": password},
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


async def _set_trust_score(db: AsyncSession, entity_id: str, score: float) -> None:
    """Insert or update a trust score for the entity."""
    eid = uuid.UUID(entity_id)
    from sqlalchemy import select

    existing = await db.scalar(
        select(TrustScore).where(TrustScore.entity_id == eid)
    )
    if existing:
        existing.score = score
    else:
        ts = TrustScore(
            id=uuid.uuid4(),
            entity_id=eid,
            score=score,
            components={"verification": 0.0, "age": 0.0, "activity": 0.0, "reputation": 0.0},
        )
        db.add(ts)
    await db.flush()
    # Invalidate cache so trust gate reads fresh value
    from src.cache import invalidate
    await invalidate(f"trust_gate:{eid}")


# --- Tests ---


@pytest.mark.asyncio
async def test_low_trust_blocked_from_create_listing(client: AsyncClient, db):
    """Entity with trust 0.0 should be blocked from create_listing (threshold 0.15)."""
    token, eid = await _setup_user(client, "tg_low@example.com", "TrustGateLow")
    await _set_trust_score(db, eid, 0.0)

    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "My Service",
            "description": "A great service",
            "category": "service",
            "pricing_model": "free",
            "price_cents": 0,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 403
    assert "Trust score too low" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_sufficient_trust_passes_create_listing(client: AsyncClient, db):
    """Entity with trust 0.5 should pass create_listing (threshold 0.15)."""
    token, eid = await _setup_user(client, "tg_high@example.com", "TrustGateHigh")
    await _set_trust_score(db, eid, 0.5)

    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Good Service",
            "description": "A trusted service",
            "category": "service",
            "pricing_model": "free",
            "price_cents": 0,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_admin_bypasses_trust_gate(client: AsyncClient, db):
    """Admin should bypass trust gates even with score 0.0."""
    token, eid = await _setup_user(client, "tg_admin@example.com", "TrustGateAdmin")
    await _set_trust_score(db, eid, 0.0)

    # Promote to admin
    from sqlalchemy import select
    entity = await db.scalar(
        select(Entity).where(Entity.id == uuid.UUID(eid))
    )
    entity.is_admin = True
    await db.flush()

    resp = await client.post(
        "/api/v1/marketplace",
        json={
            "title": "Admin Service",
            "description": "Admin bypasses trust gate",
            "category": "tool",
            "pricing_model": "free",
            "price_cents": 0,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_trust_gates_info_endpoint(client: AsyncClient, db):
    """GET /trust/gates returns gate info for the current entity."""
    token, eid = await _setup_user(client, "tg_info@example.com", "TrustGateInfo")
    await _set_trust_score(db, eid, 0.12)

    resp = await client.get(
        "/api/v1/trust/gates",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["trust_score"] == 0.12

    gates = data["gates"]
    # post_create (0.0) should be unlocked
    assert gates["post_create"]["unlocked"] is True
    assert gates["post_create"]["threshold"] == 0.0
    # create_listing (0.15) should be locked at score 0.12
    assert gates["create_listing"]["unlocked"] is False
    assert gates["create_listing"]["threshold"] == 0.15
    # send_message (0.05) should be unlocked at score 0.12
    assert gates["send_message"]["unlocked"] is True
    # create_submolt (0.25) should be locked
    assert gates["create_submolt"]["unlocked"] is False


@pytest.mark.asyncio
async def test_low_trust_blocked_from_send_message(client: AsyncClient, db):
    """Entity with trust 0.0 should be blocked from send_message (threshold 0.05)."""
    token_a, eid_a = await _setup_user(client, "tg_dm_sender@example.com", "TgDmSender")
    _, eid_b = await _setup_user(client, "tg_dm_recip@example.com", "TgDmRecipient")
    await _set_trust_score(db, eid_a, 0.0)

    resp = await client.post(
        "/api/v1/messages",
        json={"recipient_id": eid_b, "content": "Hello!"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 403
    assert "Trust score too low" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_low_trust_blocked_from_create_webhook(client: AsyncClient, db):
    """Entity with trust 0.0 should be blocked from create_webhook (threshold 0.10)."""
    token, eid = await _setup_user(client, "tg_wh@example.com", "TrustGateWebhook")
    await _set_trust_score(db, eid, 0.0)

    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": "https://example.com/webhook",
            "event_types": ["entity.followed"],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 403
    assert "Trust score too low" in resp.json()["detail"]
