from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import Entity, ModerationFlag


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
COMPLIANCE_URL = "/api/v1/compliance"

USER = {
    "email": "compliance_user@test.com",
    "password": "Str0ngP@ss",
    "display_name": "ComplianceUser",
}
ADMIN = {
    "email": "compliance_admin@test.com",
    "password": "Str0ngP@ss",
    "display_name": "ComplianceAdmin",
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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Audit Report Tests ---


@pytest.mark.asyncio
async def test_audit_report_requires_admin(client: AsyncClient, db):
    """Non-admin users should get 403 on audit report."""
    token, _ = await _setup_user(client, USER)
    resp = await client.get(
        f"{COMPLIANCE_URL}/audit-report",
        params={"start_date": "2025-01-01", "end_date": "2025-12-31"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audit_report_unauthenticated(client: AsyncClient):
    """Unauthenticated requests should get 401."""
    resp = await client.get(
        f"{COMPLIANCE_URL}/audit-report",
        params={"start_date": "2025-01-01", "end_date": "2025-12-31"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_audit_report_success(client: AsyncClient, db):
    """Admin should get a valid audit report."""
    token, eid = await _setup_user(client, ADMIN)
    await _make_admin(db, eid)

    resp = await client.get(
        f"{COMPLIANCE_URL}/audit-report",
        params={
            "start_date": "2020-01-01",
            "end_date": "2030-12-31",
            "report_type": "summary",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_type"] == "summary"
    assert data["total_entities"] >= 1
    assert data["active_entities"] >= 1
    assert data["active_admin_accounts"] >= 1
    assert "generated_at" in data
    assert "start_date" in data
    assert "end_date" in data


@pytest.mark.asyncio
async def test_audit_report_gdpr_type(client: AsyncClient, db):
    """GDPR report type should work."""
    token, eid = await _setup_user(client, {
        "email": "gdpr_admin@test.com",
        "password": "Str0ngP@ss",
        "display_name": "GDPRAdmin",
    })
    await _make_admin(db, eid)

    resp = await client.get(
        f"{COMPLIANCE_URL}/audit-report",
        params={
            "start_date": "2020-01-01",
            "end_date": "2030-12-31",
            "report_type": "gdpr",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["report_type"] == "gdpr"


@pytest.mark.asyncio
async def test_audit_report_soc2_type(client: AsyncClient, db):
    """SOC2 report type should work."""
    token, eid = await _setup_user(client, {
        "email": "soc2_admin@test.com",
        "password": "Str0ngP@ss",
        "display_name": "SOC2Admin",
    })
    await _make_admin(db, eid)

    resp = await client.get(
        f"{COMPLIANCE_URL}/audit-report",
        params={
            "start_date": "2020-01-01",
            "end_date": "2030-12-31",
            "report_type": "soc2",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["report_type"] == "soc2"


@pytest.mark.asyncio
async def test_audit_report_invalid_date_range(client: AsyncClient, db):
    """start_date > end_date should return 400."""
    token, eid = await _setup_user(client, {
        "email": "daterange_admin@test.com",
        "password": "Str0ngP@ss",
        "display_name": "DateRangeAdmin",
    })
    await _make_admin(db, eid)

    resp = await client.get(
        f"{COMPLIANCE_URL}/audit-report",
        params={
            "start_date": "2026-12-31",
            "end_date": "2025-01-01",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_audit_report_narrow_date_range(client: AsyncClient, db):
    """Narrow date range should return zero counts for activity outside range."""
    token, eid = await _setup_user(client, {
        "email": "narrow_admin@test.com",
        "password": "Str0ngP@ss",
        "display_name": "NarrowAdmin",
    })
    await _make_admin(db, eid)

    resp = await client.get(
        f"{COMPLIANCE_URL}/audit-report",
        params={
            "start_date": "1999-01-01",
            "end_date": "1999-01-02",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_posts"] == 0
    assert data["total_evolution_records"] == 0


# --- Data Retention Tests ---


@pytest.mark.asyncio
async def test_data_retention_requires_auth(client: AsyncClient):
    """Unauthenticated requests should get 401."""
    resp = await client.get(f"{COMPLIANCE_URL}/data-retention")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_data_retention_returns_policy(client: AsyncClient, db):
    """Authenticated user should get data retention policy."""
    token, eid = await _setup_user(client, {
        "email": "retention_user@test.com",
        "password": "Str0ngP@ss",
        "display_name": "RetentionUser",
    })

    resp = await client.get(
        f"{COMPLIANCE_URL}/data-retention",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == eid
    assert data["posts_retention_days"] is None
    assert data["audit_log_retention_days"] == 365
    assert data["inactive_account_policy_days"] == 730
    assert isinstance(data["entity_data_categories"], list)
    assert len(data["entity_data_categories"]) > 0


# --- Data Deletion Request Tests ---


@pytest.mark.asyncio
async def test_data_deletion_requires_auth(client: AsyncClient):
    """Unauthenticated requests should get 401."""
    resp = await client.post(f"{COMPLIANCE_URL}/data-deletion-request")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_data_deletion_creates_request(client: AsyncClient, db):
    """Authenticated user should be able to create a data deletion request."""
    token, eid = await _setup_user(client, {
        "email": "deletion_user@test.com",
        "password": "Str0ngP@ss",
        "display_name": "DeletionUser",
    })

    resp = await client.post(
        f"{COMPLIANCE_URL}/data-deletion-request",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == eid
    assert data["status"] == "pending"
    assert data["estimated_processing_days"] == 30
    assert "request_id" in data
    assert "created_at" in data

    # Verify the flag was created in the database
    flag = await db.get(ModerationFlag, uuid.UUID(data["request_id"]))
    assert flag is not None
    assert flag.details == "data_deletion_request"
    assert str(flag.target_id) == eid


@pytest.mark.asyncio
async def test_data_deletion_multiple_requests(client: AsyncClient, db):
    """User should be able to create multiple deletion requests."""
    token, eid = await _setup_user(client, {
        "email": "multi_deletion@test.com",
        "password": "Str0ngP@ss",
        "display_name": "MultiDeletion",
    })

    resp1 = await client.post(
        f"{COMPLIANCE_URL}/data-deletion-request",
        headers=_auth(token),
    )
    resp2 = await client.post(
        f"{COMPLIANCE_URL}/data-deletion-request",
        headers=_auth(token),
    )
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["request_id"] != resp2.json()["request_id"]


# --- Consent Records Tests ---


@pytest.mark.asyncio
async def test_consent_records_requires_auth(client: AsyncClient):
    """Unauthenticated requests should get 401."""
    resp = await client.get(f"{COMPLIANCE_URL}/consent-records")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_consent_records_returns_records(client: AsyncClient, db):
    """Authenticated user should get consent records."""
    token, eid = await _setup_user(client, {
        "email": "consent_user@test.com",
        "password": "Str0ngP@ss",
        "display_name": "ConsentUser",
    })

    resp = await client.get(
        f"{COMPLIANCE_URL}/consent-records",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == eid
    assert data["tos_version"] == "1.0"
    assert data["privacy_policy_version"] == "1.0"
    assert data["data_processing_consent"] is True
    assert "tos_agreed_at" in data


# --- Data Export Tests ---


@pytest.mark.asyncio
async def test_data_export_requires_auth(client: AsyncClient):
    """Unauthenticated requests should get 401."""
    resp = await client.get(f"{COMPLIANCE_URL}/data-export")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_data_export_returns_profile(client: AsyncClient, db):
    """Data export should include profile information."""
    token, eid = await _setup_user(client, {
        "email": "export_user@test.com",
        "password": "Str0ngP@ss",
        "display_name": "ExportUser",
    })

    resp = await client.get(
        f"{COMPLIANCE_URL}/data-export",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == eid
    assert data["profile"]["display_name"] == "ExportUser"
    assert data["profile"]["email"] == "export_user@test.com"
    assert "exported_at" in data


@pytest.mark.asyncio
async def test_data_export_includes_posts(client: AsyncClient, db):
    """Data export should include the user's posts."""
    token, eid = await _setup_user(client, {
        "email": "export_posts@test.com",
        "password": "Str0ngP@ss",
        "display_name": "ExportPosts",
    })

    # Create a post
    post_resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Compliance test post"},
        headers=_auth(token),
    )
    assert post_resp.status_code in (200, 201)

    resp = await client.get(
        f"{COMPLIANCE_URL}/data-export",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["posts"]) >= 1
    assert any("Compliance test post" in p["content"] for p in data["posts"])


@pytest.mark.asyncio
async def test_data_export_comprehensive_structure(client: AsyncClient, db):
    """Data export should contain all required sections."""
    token, eid = await _setup_user(client, {
        "email": "export_full@test.com",
        "password": "Str0ngP@ss",
        "display_name": "ExportFull",
    })

    resp = await client.get(
        f"{COMPLIANCE_URL}/data-export",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    # Verify all sections are present
    assert "profile" in data
    assert "posts" in data
    assert "relationships" in data
    assert "trust_score" in data
    assert "evolution_records" in data
    assert "audit_logs" in data
    assert "exported_at" in data
    # Lists should be valid (can be empty)
    assert isinstance(data["posts"], list)
    assert isinstance(data["relationships"], list)
    assert isinstance(data["evolution_records"], list)
    assert isinstance(data["audit_logs"], list)
