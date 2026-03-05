from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.jobs.expire_provisional import expire_provisional_agents
from src.main import app
from src.models import APIKey, Entity, EntityType


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _make_entity(
    *,
    display_name: str = "TestAgent",
    is_provisional: bool = False,
    provisional_expires_at: datetime | None = None,
    is_active: bool = True,
    entity_type: EntityType = EntityType.AGENT,
) -> Entity:
    """Create an Entity instance with sensible defaults."""
    entity_id = uuid.uuid4()
    return Entity(
        id=entity_id,
        type=entity_type,
        display_name=display_name,
        did_web=f"did:web:agentgraph.co:{entity_id}",
        is_provisional=is_provisional,
        provisional_expires_at=provisional_expires_at,
        is_active=is_active,
    )


def _make_api_key(entity_id: uuid.UUID) -> APIKey:
    """Create an active API key for an entity."""
    raw_key = uuid.uuid4().hex
    return APIKey(
        id=uuid.uuid4(),
        entity_id=entity_id,
        key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
        label="test-key",
        is_active=True,
    )


# --- Direct job function tests ---


@pytest.mark.asyncio
async def test_expired_provisional_agents_get_deactivated(db):
    """Expired provisional agents should be set is_active=False."""
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    agent = _make_entity(
        display_name="ExpiredAgent",
        is_provisional=True,
        provisional_expires_at=past,
    )
    db.add(agent)
    await db.flush()

    summary = await expire_provisional_agents(db)

    assert summary["expired_count"] == 1
    await db.refresh(agent)
    assert agent.is_active is False


@pytest.mark.asyncio
async def test_non_expired_provisional_agents_untouched(db):
    """Provisional agents whose expiry is in the future should remain active."""
    future = datetime.now(timezone.utc) + timedelta(hours=24)
    agent = _make_entity(
        display_name="FutureAgent",
        is_provisional=True,
        provisional_expires_at=future,
    )
    db.add(agent)
    await db.flush()

    summary = await expire_provisional_agents(db)

    assert summary["expired_count"] == 0
    await db.refresh(agent)
    assert agent.is_active is True
    assert agent.is_provisional is True


@pytest.mark.asyncio
async def test_non_provisional_agents_untouched(db):
    """Non-provisional agents should not be affected, even if they have no expiry."""
    agent = _make_entity(
        display_name="RegularAgent",
        is_provisional=False,
        provisional_expires_at=None,
    )
    db.add(agent)
    await db.flush()

    summary = await expire_provisional_agents(db)

    assert summary["expired_count"] == 0
    await db.refresh(agent)
    assert agent.is_active is True


@pytest.mark.asyncio
async def test_api_keys_revoked_for_expired_agents(db):
    """API keys belonging to expired provisional agents should be revoked."""
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    agent = _make_entity(
        display_name="AgentWithKeys",
        is_provisional=True,
        provisional_expires_at=past,
    )
    db.add(agent)
    await db.flush()

    key1 = _make_api_key(agent.id)
    key2 = _make_api_key(agent.id)
    db.add_all([key1, key2])
    await db.flush()

    summary = await expire_provisional_agents(db)

    assert summary["expired_count"] == 1
    assert summary["keys_revoked"] == 2

    await db.refresh(key1)
    await db.refresh(key2)
    assert key1.is_active is False
    assert key2.is_active is False
    assert key1.revoked_at is not None
    assert key2.revoked_at is not None


@pytest.mark.asyncio
async def test_already_deactivated_provisional_agents_skipped(db):
    """Already-deactivated provisional agents should not be processed again."""
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    agent = _make_entity(
        display_name="AlreadyDeactivated",
        is_provisional=True,
        provisional_expires_at=past,
        is_active=False,
    )
    db.add(agent)
    await db.flush()

    summary = await expire_provisional_agents(db)

    assert summary["expired_count"] == 0


@pytest.mark.asyncio
async def test_mixed_agents_only_expired_affected(db):
    """With a mix of agent types, only expired provisional ones are deactivated."""
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    future = datetime.now(timezone.utc) + timedelta(hours=24)

    expired = _make_entity(
        display_name="Expired",
        is_provisional=True,
        provisional_expires_at=past,
    )
    not_expired = _make_entity(
        display_name="NotExpired",
        is_provisional=True,
        provisional_expires_at=future,
    )
    regular = _make_entity(
        display_name="Regular",
        is_provisional=False,
    )
    db.add_all([expired, not_expired, regular])
    await db.flush()

    summary = await expire_provisional_agents(db)

    assert summary["expired_count"] == 1

    await db.refresh(expired)
    await db.refresh(not_expired)
    await db.refresh(regular)

    assert expired.is_active is False
    assert not_expired.is_active is True
    assert regular.is_active is True


# --- Admin endpoint tests ---


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
EXPIRE_URL = "/api/v1/admin/jobs/expire-provisional"

ADMIN_USER = {
    "email": "expjob-admin@test.com",
    "password": "Str0ngP@ss",
    "display_name": "ExpireJobAdmin",
}
REGULAR_USER = {
    "email": "expjob-user@test.com",
    "password": "Str0ngP@ss",
    "display_name": "ExpireJobUser",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register + login, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


async def _make_admin(db, entity_id: str):
    entity = await db.get(Entity, uuid.UUID(entity_id))
    entity.is_admin = True
    await db.flush()


@pytest.mark.asyncio
async def test_endpoint_requires_admin(client: AsyncClient):
    """Non-admin users should get 403."""
    token, _ = await _setup_user(client, REGULAR_USER)
    resp = await client.post(
        EXPIRE_URL, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_endpoint_requires_auth(client: AsyncClient):
    """Unauthenticated requests should get 401."""
    resp = await client.post(EXPIRE_URL)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_endpoint_returns_summary(client: AsyncClient, db):
    """Admin can trigger the job and get a summary response."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    # Create an expired provisional agent
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    agent = _make_entity(
        display_name="EndpointTestAgent",
        is_provisional=True,
        provisional_expires_at=past,
    )
    db.add(agent)
    await db.flush()

    resp = await client.post(
        EXPIRE_URL, headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["expired_count"] >= 1
    assert "keys_revoked" in data
    assert "duration_seconds" in data
