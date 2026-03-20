"""Tests for propagation safety controls.

Covers freeze/quarantine logic, trust score checks, and admin endpoints.
"""
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


async def _create_user(client, email, name):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Str0ngP@ss1", "display_name": name},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Str0ngP@ss1"},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    return token, me.json()["id"]


async def _create_admin(client, db):
    token, eid = await _create_user(client, f"admin-{uuid.uuid4().hex[:8]}@test.com", "Admin")
    from src.models import Entity

    entity = await db.get(Entity, uuid.UUID(eid))
    entity.is_admin = True
    await db.flush()
    return token, eid


# --- Propagation freeze tests ---


@pytest.mark.asyncio
async def test_propagation_freeze_default_unfrozen(db):
    """Propagation should be unfrozen by default."""
    from src.safety.propagation import is_propagation_frozen

    result = await is_propagation_frozen()
    assert result is False


@pytest.mark.asyncio
async def test_propagation_freeze_set_and_check(db):
    """Setting freeze to active should be detectable."""
    from src.safety.propagation import is_propagation_frozen, set_propagation_freeze

    await set_propagation_freeze(True)
    try:
        result = await is_propagation_frozen()
        assert result is True
    finally:
        await set_propagation_freeze(False)

    result = await is_propagation_frozen()
    assert result is False


# --- Quarantine tests ---


@pytest.mark.asyncio
async def test_quarantine_entity(client, db):
    """Quarantining an entity should set is_quarantined=True."""
    from src.safety.propagation import is_entity_quarantined, quarantine_entity

    _, eid = await _create_user(client, f"q-{uuid.uuid4().hex[:8]}@test.com", "QuarantineTarget")
    entity_id = uuid.UUID(eid)

    assert await is_entity_quarantined(db, entity_id) is False

    await quarantine_entity(db, entity_id, "Suspicious activity")

    assert await is_entity_quarantined(db, entity_id) is True


@pytest.mark.asyncio
async def test_release_quarantine(client, db):
    """Releasing quarantine should set is_quarantined=False."""
    from src.safety.propagation import (
        is_entity_quarantined,
        quarantine_entity,
        release_quarantine,
    )

    _, eid = await _create_user(client, f"rq-{uuid.uuid4().hex[:8]}@test.com", "ReleaseTarget")
    entity_id = uuid.UUID(eid)

    await quarantine_entity(db, entity_id, "Suspicious activity")
    assert await is_entity_quarantined(db, entity_id) is True

    await release_quarantine(db, entity_id, "Investigation complete")
    assert await is_entity_quarantined(db, entity_id) is False


@pytest.mark.asyncio
async def test_quarantined_entity_blocked_from_operations(client, db):
    """A quarantined entity should be detectable for blocking operations."""
    from src.safety.propagation import is_entity_quarantined, quarantine_entity

    _, eid = await _create_user(client, f"blk-{uuid.uuid4().hex[:8]}@test.com", "BlockedUser")
    entity_id = uuid.UUID(eid)

    await quarantine_entity(db, entity_id, "Malicious behavior")

    # Verify quarantine state is accessible for enforcement
    is_q = await is_entity_quarantined(db, entity_id)
    assert is_q is True


# --- Trust score checks ---


@pytest.mark.asyncio
async def test_min_trust_check_passes(client, db):
    """Entity with sufficient trust score should pass the check."""
    from src.models import TrustScore
    from src.safety.propagation import check_min_trust_for_publish

    _, eid = await _create_user(client, f"tp-{uuid.uuid4().hex[:8]}@test.com", "TrustedUser")
    entity_id = uuid.UUID(eid)

    # Update trust score above threshold
    from sqlalchemy import update as _sa_update
    await db.execute(
        _sa_update(TrustScore)
        .where(TrustScore.entity_id == entity_id)
        .values(score=0.8, components={})
    )
    await db.flush()

    result = await check_min_trust_for_publish(db, entity_id, min_trust=0.3)
    assert result is True


@pytest.mark.asyncio
async def test_min_trust_check_fails(client, db):
    """Entity with insufficient trust score should fail the check."""
    from src.models import TrustScore
    from src.safety.propagation import check_min_trust_for_publish

    _, eid = await _create_user(client, f"tf-{uuid.uuid4().hex[:8]}@test.com", "UntrustedUser")
    entity_id = uuid.UUID(eid)

    # Update trust score below threshold
    from sqlalchemy import update as _sa_update
    await db.execute(
        _sa_update(TrustScore)
        .where(TrustScore.entity_id == entity_id)
        .values(score=0.1, components={})
    )
    await db.flush()

    # grace_period_days=0 to test pure trust threshold without newbie grace
    result = await check_min_trust_for_publish(
        db, entity_id, min_trust=0.3, grace_period_days=0,
    )
    assert result is False


# --- Admin endpoint tests ---


@pytest.mark.asyncio
async def test_freeze_endpoint_requires_admin(client, db):
    """Non-admin users should be rejected from freeze endpoint."""
    token, _ = await _create_user(client, f"na-{uuid.uuid4().hex[:8]}@test.com", "NonAdmin")
    resp = await client.post(
        "/api/v1/admin/safety/freeze",
        json={"active": True, "reason": "Test freeze"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_freeze_endpoint_activate(client, db):
    """Admin should be able to activate propagation freeze."""
    token, _ = await _create_admin(client, db)

    resp = await client.post(
        "/api/v1/admin/safety/freeze",
        json={"active": True, "reason": "Emergency shutdown"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["frozen"] is True
    assert data["since"] is not None

    # Cleanup
    from src.safety.propagation import set_propagation_freeze
    await set_propagation_freeze(False)


@pytest.mark.asyncio
async def test_freeze_endpoint_deactivate(client, db):
    """Admin should be able to deactivate propagation freeze."""
    token, _ = await _create_admin(client, db)

    # First activate
    from src.safety.propagation import set_propagation_freeze
    await set_propagation_freeze(True)

    resp = await client.post(
        "/api/v1/admin/safety/freeze",
        json={"active": False, "reason": "All clear"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["frozen"] is False
    assert data["since"] is None


@pytest.mark.asyncio
async def test_quarantine_endpoint_requires_admin(client, db):
    """Non-admin users should be rejected from quarantine endpoint."""
    token, eid = await _create_user(client, f"naq-{uuid.uuid4().hex[:8]}@test.com", "NonAdmin")
    resp = await client.post(
        f"/api/v1/admin/safety/quarantine/{eid}",
        json={"reason": "Test quarantine"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_quarantine_endpoint_nonexistent_entity(client, db):
    """Quarantining a nonexistent entity should return 404."""
    token, _ = await _create_admin(client, db)
    fake_id = uuid.uuid4()
    resp = await client.post(
        f"/api/v1/admin/safety/quarantine/{fake_id}",
        json={"reason": "Test quarantine"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
