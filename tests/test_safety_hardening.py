"""Tests for anti-weaponization hardening endpoints."""
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
ME_URL = "/api/v1/auth/me"
BASE_URL = "/api/v1/safety/hardening"

USER_A = {
    "email": "hardening_a@test.com",
    "password": "Str0ngP@ss1",
    "display_name": "HardeningUserA",
}
USER_B = {
    "email": "hardening_b@test.com",
    "password": "Str0ngP@ss2",
    "display_name": "HardeningUserB",
}
ADMIN_USER = {
    "email": "hardening_admin@test.com",
    "password": "Str0ngP@ss3",
    "display_name": "HardeningAdmin",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register + login, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


async def _make_admin(db, entity_id: str):
    from src.models import Entity

    entity = await db.get(Entity, uuid.UUID(entity_id))
    entity.is_admin = True
    await db.flush()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. POST /safety/hardening/report-coordinated-behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_report_cib_success(client: AsyncClient, db):
    """Authenticated user can report CIB."""
    reporter_token, _ = await _setup_user(client, USER_A)
    _, target_id = await _setup_user(client, USER_B)

    resp = await client.post(
        f"{BASE_URL}/report-coordinated-behavior",
        json={
            "entity_ids": [target_id, target_id],
            "description": "These accounts appear to be coordinated bots.",
            "evidence": "All created at same time with similar names.",
        },
        headers=_auth(reporter_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "under_review"
    assert data["entities_flagged"] >= 1
    assert "investigation_id" in data


@pytest.mark.asyncio
async def test_report_cib_unauthenticated(client: AsyncClient):
    """Unauthenticated requests are rejected."""
    resp = await client.post(
        f"{BASE_URL}/report-coordinated-behavior",
        json={
            "entity_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
            "description": "Some suspicious behavior pattern.",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_report_cib_cannot_include_self(client: AsyncClient, db):
    """Cannot include yourself in a CIB report."""
    token, entity_id = await _setup_user(client, USER_A)
    _, other_id = await _setup_user(client, USER_B)

    resp = await client.post(
        f"{BASE_URL}/report-coordinated-behavior",
        json={
            "entity_ids": [entity_id, other_id],
            "description": "Including myself should fail validation.",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_report_cib_nonexistent_entities(client: AsyncClient, db):
    """Reporting entities that don't exist returns 404."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        f"{BASE_URL}/report-coordinated-behavior",
        json={
            "entity_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
            "description": "These entities definitely do not exist.",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_report_cib_invalid_uuid(client: AsyncClient, db):
    """Invalid entity IDs return 422."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.post(
        f"{BASE_URL}/report-coordinated-behavior",
        json={
            "entity_ids": ["not-a-uuid", "also-bad"],
            "description": "Bad IDs should fail validation.",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 2. GET /safety/hardening/sybil-risk/{entity_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sybil_risk_admin_only(client: AsyncClient, db):
    """Non-admin users cannot access sybil risk endpoint."""
    token, entity_id = await _setup_user(client, USER_A)

    resp = await client.get(
        f"{BASE_URL}/sybil-risk/{entity_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sybil_risk_success(client: AsyncClient, db):
    """Admin can check sybil risk for an entity."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    _, target_id = await _setup_user(client, USER_A)

    resp = await client.get(
        f"{BASE_URL}/sybil-risk/{target_id}",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == target_id
    assert 0.0 <= data["risk_score"] <= 1.0
    assert data["risk_level"] in ("low", "medium", "high", "critical")
    assert isinstance(data["risk_factors"], list)


@pytest.mark.asyncio
async def test_sybil_risk_not_found(client: AsyncClient, db):
    """Checking sybil risk for nonexistent entity returns 404."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    fake_id = str(uuid.uuid4())
    resp = await client.get(
        f"{BASE_URL}/sybil-risk/{fake_id}",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sybil_risk_detects_unverified(client: AsyncClient, db):
    """Sybil risk includes unverified email as a risk factor."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    _, target_id = await _setup_user(client, USER_A)

    resp = await client.get(
        f"{BASE_URL}/sybil-risk/{target_id}",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    factors = [f["factor"] for f in data["risk_factors"]]
    assert "unverified_email" in factors


# ---------------------------------------------------------------------------
# 3. GET /safety/hardening/trust-gaming-indicators/{entity_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trust_gaming_admin_only(client: AsyncClient, db):
    """Non-admin users cannot access trust gaming endpoint."""
    token, entity_id = await _setup_user(client, USER_A)

    resp = await client.get(
        f"{BASE_URL}/trust-gaming-indicators/{entity_id}",
        headers=_auth(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_trust_gaming_success(client: AsyncClient, db):
    """Admin can check trust gaming indicators."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    _, target_id = await _setup_user(client, USER_A)

    resp = await client.get(
        f"{BASE_URL}/trust-gaming-indicators/{target_id}",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == target_id
    assert data["overall_risk"] in ("none", "low", "medium", "high")
    assert isinstance(data["indicators"], list)


@pytest.mark.asyncio
async def test_trust_gaming_not_found(client: AsyncClient, db):
    """Checking trust gaming for nonexistent entity returns 404."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    fake_id = str(uuid.uuid4())
    resp = await client.get(
        f"{BASE_URL}/trust-gaming-indicators/{fake_id}",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. POST /safety/hardening/escalate-rate-limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escalate_rate_limit_admin_only(client: AsyncClient, db):
    """Non-admin users cannot escalate rate limits."""
    token, _ = await _setup_user(client, USER_A)
    _, target_id = await _setup_user(client, USER_B)

    resp = await client.post(
        f"{BASE_URL}/escalate-rate-limit",
        json={
            "entity_id": target_id,
            "duration_hours": 1,
            "reason": "Suspicious activity detected",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_escalate_rate_limit_success(client: AsyncClient, db):
    """Admin can escalate rate limits for a non-admin entity."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    _, target_id = await _setup_user(client, USER_A)

    resp = await client.post(
        f"{BASE_URL}/escalate-rate-limit",
        json={
            "entity_id": target_id,
            "duration_hours": 2,
            "reason": "Detected bot-like behavior patterns",
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == target_id
    assert "throttled_until" in data
    assert data["reason"] == "Detected bot-like behavior patterns"


@pytest.mark.asyncio
async def test_escalate_rate_limit_cannot_throttle_admin(
    client: AsyncClient, db,
):
    """Admin cannot throttle another admin."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    # Create another admin
    other_admin = {
        "email": "other_admin_hard@test.com",
        "password": "Str0ngP@ss5",
        "display_name": "OtherAdmin",
    }
    _, other_admin_id = await _setup_user(client, other_admin)
    await _make_admin(db, other_admin_id)

    resp = await client.post(
        f"{BASE_URL}/escalate-rate-limit",
        json={
            "entity_id": other_admin_id,
            "duration_hours": 1,
            "reason": "Trying to throttle admin",
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_escalate_rate_limit_not_found(client: AsyncClient, db):
    """Escalating rate limit for nonexistent entity returns 404."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"{BASE_URL}/escalate-rate-limit",
        json={
            "entity_id": fake_id,
            "duration_hours": 1,
            "reason": "Entity does not exist",
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. GET /safety/hardening/platform-health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_platform_health_admin_only(client: AsyncClient, db):
    """Non-admin users cannot access platform health."""
    token, _ = await _setup_user(client, USER_A)

    resp = await client.get(
        f"{BASE_URL}/platform-health",
        headers=_auth(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_platform_health_success(client: AsyncClient, db):
    """Admin can view platform health metrics."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    resp = await client.get(
        f"{BASE_URL}/platform-health",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_active_entities"] >= 1
    assert data["new_accounts_24h"] >= 1
    assert isinstance(data["flagged_content_rate"], float)
    assert isinstance(data["moderation_queue_depth"], int)
    # trust_score_trend may be null if no trust scores exist
    assert data["trust_score_trend"] in ("rising", "stable", "declining", None)
