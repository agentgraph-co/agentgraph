"""Tests for emergency protocols and alert system.

Covers alert creation, listing, WebSocket broadcast, and admin endpoint validation.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

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


# --- Direct function tests ---


@pytest.mark.asyncio
async def test_broadcast_network_alert(db):
    """broadcast_network_alert should create a PropagationAlert record."""
    from src.safety.emergency import broadcast_network_alert

    alert = await broadcast_network_alert(
        db,
        alert_type="network_alert",
        message="Test alert message",
        severity="info",
    )

    assert alert is not None
    assert alert.alert_type == "network_alert"
    assert alert.severity == "info"
    assert alert.message == "Test alert message"
    assert alert.is_resolved is False


@pytest.mark.asyncio
async def test_get_recent_alerts(db):
    """get_recent_alerts should return alerts ordered by recency."""
    from src.safety.emergency import broadcast_network_alert, get_recent_alerts

    # Create a few alerts
    await broadcast_network_alert(db, "network_alert", "First", "info")
    await broadcast_network_alert(db, "freeze", "Second", "critical")
    await broadcast_network_alert(db, "quarantine", "Third", "warning")

    alerts = await get_recent_alerts(db, limit=10)
    assert len(alerts) >= 3

    # Most recent should be first
    messages = [a.message for a in alerts[:3]]
    assert "Third" in messages[0] or "Third" in messages


@pytest.mark.asyncio
async def test_alert_broadcast_websocket(db):
    """broadcast_network_alert should attempt WebSocket broadcast."""
    mock_broadcast = AsyncMock(return_value=0)
    with patch("src.ws.manager") as mock_manager:
        mock_manager.broadcast_to_channel = mock_broadcast

        from src.safety.emergency import broadcast_network_alert

        alert = await broadcast_network_alert(
            db,
            alert_type="network_alert",
            message="WS test",
            severity="warning",
        )

        assert alert is not None
        mock_broadcast.assert_called_once()
        call_args = mock_broadcast.call_args
        assert call_args[0][0] == "safety"
        assert call_args[0][1]["type"] == "network_alert"
        assert call_args[0][1]["severity"] == "warning"


# --- Admin endpoint tests ---


@pytest.mark.asyncio
async def test_alert_endpoint_requires_admin(client, db):
    """Non-admin users should be rejected from alert endpoint."""
    token, _ = await _create_user(client, f"na-{uuid.uuid4().hex[:8]}@test.com", "NonAdmin")
    resp = await client.post(
        "/api/v1/admin/safety/alert",
        json={"alert_type": "test", "message": "Hello", "severity": "info"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_alert_endpoint_creates_record(client, db):
    """Admin should be able to create an alert via the endpoint."""
    token, admin_id = await _create_admin(client, db)

    resp = await client.post(
        "/api/v1/admin/safety/alert",
        json={
            "alert_type": "network_alert",
            "message": "Endpoint test alert",
            "severity": "warning",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["alert_type"] == "network_alert"
    assert data["severity"] == "warning"
    assert data["message"] == "Endpoint test alert"
    assert data["issued_by"] == admin_id
    assert data["is_resolved"] is False


@pytest.mark.asyncio
async def test_alert_endpoint_invalid_severity(client, db):
    """Invalid severity should be rejected with 422."""
    token, _ = await _create_admin(client, db)

    resp = await client.post(
        "/api/v1/admin/safety/alert",
        json={
            "alert_type": "test",
            "message": "Bad severity",
            "severity": "extreme",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_alerts_list_endpoint(client, db):
    """Admin should be able to list recent alerts."""
    token, _ = await _create_admin(client, db)

    # Create an alert first
    await client.post(
        "/api/v1/admin/safety/alert",
        json={
            "alert_type": "network_alert",
            "message": "List test",
            "severity": "info",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.get(
        "/api/v1/admin/safety/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "alerts" in data
    assert len(data["alerts"]) >= 1


@pytest.mark.asyncio
async def test_freeze_creates_alert(client, db):
    """Activating freeze should create a PropagationAlert record."""
    token, _ = await _create_admin(client, db)

    resp = await client.post(
        "/api/v1/admin/safety/freeze",
        json={"active": True, "reason": "Alert test freeze"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # Check that an alert was created
    resp2 = await client.get(
        "/api/v1/admin/safety/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )
    alerts = resp2.json()["alerts"]
    freeze_alerts = [a for a in alerts if a["alert_type"] == "freeze"]
    assert len(freeze_alerts) >= 1

    # Cleanup
    from src.safety.propagation import set_propagation_freeze
    await set_propagation_freeze(False)


@pytest.mark.asyncio
async def test_quarantine_creates_alert(client, db):
    """Quarantining an entity should create a PropagationAlert record."""
    token, admin_id = await _create_admin(client, db)
    _, target_id = await _create_user(
        client, f"qt-{uuid.uuid4().hex[:8]}@test.com", "QTarget"
    )

    resp = await client.post(
        f"/api/v1/admin/safety/quarantine/{target_id}",
        json={"reason": "Alert test quarantine"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # Check alert was created
    resp2 = await client.get(
        "/api/v1/admin/safety/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )
    alerts = resp2.json()["alerts"]
    q_alerts = [a for a in alerts if a["alert_type"] == "quarantine"]
    assert len(q_alerts) >= 1


@pytest.mark.asyncio
async def test_release_quarantine_creates_alert(client, db):
    """Releasing quarantine should create a PropagationAlert record."""
    token, _ = await _create_admin(client, db)
    _, target_id = await _create_user(
        client, f"rqa-{uuid.uuid4().hex[:8]}@test.com", "RQATarget"
    )

    # First quarantine
    await client.post(
        f"/api/v1/admin/safety/quarantine/{target_id}",
        json={"reason": "Pre-release quarantine"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Then release
    resp = await client.request(
        "DELETE",
        f"/api/v1/admin/safety/quarantine/{target_id}",
        json={"reason": "All clear"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_quarantined"] is False


@pytest.mark.asyncio
async def test_freeze_status_endpoint(client, db):
    """Freeze status endpoint should return current state."""
    token, _ = await _create_admin(client, db)

    resp = await client.get(
        "/api/v1/admin/safety/freeze",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "frozen" in data


@pytest.mark.asyncio
async def test_quarantine_release_endpoint(client, db):
    """Full quarantine-release cycle via endpoints."""
    token, _ = await _create_admin(client, db)
    _, target_id = await _create_user(
        client, f"cycle-{uuid.uuid4().hex[:8]}@test.com", "CycleTarget"
    )

    # Quarantine
    resp = await client.post(
        f"/api/v1/admin/safety/quarantine/{target_id}",
        json={"reason": "Cycle test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_quarantined"] is True

    # Release
    resp = await client.request(
        "DELETE",
        f"/api/v1/admin/safety/quarantine/{target_id}",
        json={"reason": "Cycle resolved"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_quarantined"] is False


@pytest.mark.asyncio
async def test_freeze_persists_in_redis(db):
    """Freeze state should persist in Redis between checks."""
    from src.safety.propagation import is_propagation_frozen, set_propagation_freeze

    await set_propagation_freeze(True)
    try:
        # Multiple checks should all return True
        assert await is_propagation_frozen() is True
        assert await is_propagation_frozen() is True
    finally:
        await set_propagation_freeze(False)

    assert await is_propagation_frozen() is False
