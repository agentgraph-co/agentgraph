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
AGENTS_URL = "/api/v1/agents"
ENTITIES_URL = "/api/v1/entities"

ADMIN_USER = {
    "email": "badge_admin@example.com",
    "password": "Str0ngP@ss",
    "display_name": "BadgeAdmin",
}
USER_A = {
    "email": "badge_a@example.com",
    "password": "Str0ngP@ss",
    "display_name": "BadgeUserA",
}
USER_B = {
    "email": "badge_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "BadgeUserB",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL,
        json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_admin(db, entity_id: str) -> None:
    from sqlalchemy import update

    from src.models import Entity
    stmt = update(Entity).where(
        Entity.id == uuid.UUID(entity_id)
    ).values(is_admin=True)
    await db.execute(stmt)
    await db.flush()


async def _set_trust_score(db, entity_id: str, score: float) -> None:
    from src.models import TrustScore
    ts = TrustScore(
        id=uuid.uuid4(),
        entity_id=uuid.UUID(entity_id),
        score=score,
        components={"verification": score},
    )
    db.add(ts)
    await db.flush()


async def _create_agent(client: AsyncClient, token: str) -> str:
    resp = await client.post(
        AGENTS_URL,
        json={
            "display_name": "AuditBot",
            "capabilities": ["summarize", "translate"],
            "autonomy_level": 3,
        },
        headers=_auth(token),
    )
    return resp.json()["agent"]["id"]


# --- Badge Tests ---


@pytest.mark.asyncio
async def test_list_badges_empty(client: AsyncClient, db):
    """List badges for entity with no badges returns empty."""
    token, entity_id = await _setup_user(client, USER_A)
    resp = await client.get(f"{ENTITIES_URL}/{entity_id}/badges")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["badges"] == []


@pytest.mark.asyncio
async def test_issue_badge_admin_only(client: AsyncClient, db):
    """Non-admin cannot issue badges."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)
    resp = await client.post(
        f"{ENTITIES_URL}/{id_b}/badges",
        json={"badge_type": "email_verified"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 403
    assert "Admin" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_issue_badge_success(client: AsyncClient, db):
    """Admin can issue a badge."""
    token_admin, id_admin = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, id_admin)
    token_b, id_b = await _setup_user(client, USER_B)

    resp = await client.post(
        f"{ENTITIES_URL}/{id_b}/badges",
        json={"badge_type": "email_verified", "proof_url": "https://proof.example.com"},
        headers=_auth(token_admin),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["badge_type"] == "email_verified"
    assert data["proof_url"] == "https://proof.example.com"
    assert data["is_active"] is True
    assert data["issued_by"] == id_admin


@pytest.mark.asyncio
async def test_list_badges_after_issue(client: AsyncClient, db):
    """Badges show up in list after being issued."""
    token_admin, id_admin = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, id_admin)
    token_b, id_b = await _setup_user(client, USER_B)

    await client.post(
        f"{ENTITIES_URL}/{id_b}/badges",
        json={"badge_type": "email_verified"},
        headers=_auth(token_admin),
    )

    resp = await client.get(f"{ENTITIES_URL}/{id_b}/badges")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["badges"][0]["badge_type"] == "email_verified"


@pytest.mark.asyncio
async def test_duplicate_badge_rejected(client: AsyncClient, db):
    """Cannot issue same badge type twice."""
    token_admin, id_admin = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, id_admin)
    token_b, id_b = await _setup_user(client, USER_B)

    await client.post(
        f"{ENTITIES_URL}/{id_b}/badges",
        json={"badge_type": "identity_verified"},
        headers=_auth(token_admin),
    )
    resp = await client.post(
        f"{ENTITIES_URL}/{id_b}/badges",
        json={"badge_type": "identity_verified"},
        headers=_auth(token_admin),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_deactivate_badge(client: AsyncClient, db):
    """Admin can deactivate a badge."""
    token_admin, id_admin = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, id_admin)
    token_b, id_b = await _setup_user(client, USER_B)

    resp = await client.post(
        f"{ENTITIES_URL}/{id_b}/badges",
        json={"badge_type": "email_verified"},
        headers=_auth(token_admin),
    )
    badge_id = resp.json()["id"]

    resp = await client.patch(
        f"{ENTITIES_URL}/{id_b}/badges/{badge_id}/deactivate",
        headers=_auth(token_admin),
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_deactivate_badge_non_admin_fails(client: AsyncClient, db):
    """Non-admin cannot deactivate a badge."""
    token_admin, id_admin = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, id_admin)
    token_b, id_b = await _setup_user(client, USER_B)

    resp = await client.post(
        f"{ENTITIES_URL}/{id_b}/badges",
        json={"badge_type": "email_verified"},
        headers=_auth(token_admin),
    )
    badge_id = resp.json()["id"]

    resp = await client.patch(
        f"{ENTITIES_URL}/{id_b}/badges/{badge_id}/deactivate",
        headers=_auth(token_b),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_deactivated_badge_not_in_default_list(client: AsyncClient, db):
    """Deactivated badges are hidden by default."""
    token_admin, id_admin = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, id_admin)
    token_b, id_b = await _setup_user(client, USER_B)

    resp = await client.post(
        f"{ENTITIES_URL}/{id_b}/badges",
        json={"badge_type": "email_verified"},
        headers=_auth(token_admin),
    )
    badge_id = resp.json()["id"]

    await client.patch(
        f"{ENTITIES_URL}/{id_b}/badges/{badge_id}/deactivate",
        headers=_auth(token_admin),
    )

    resp = await client.get(f"{ENTITIES_URL}/{id_b}/badges")
    assert resp.json()["total"] == 0

    # include_expired shows them
    resp = await client.get(
        f"{ENTITIES_URL}/{id_b}/badges",
        params={"include_expired": "true"},
    )
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_badge_invalid_type(client: AsyncClient, db):
    """Invalid badge type is rejected."""
    token_admin, id_admin = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, id_admin)
    token_b, id_b = await _setup_user(client, USER_B)

    resp = await client.post(
        f"{ENTITIES_URL}/{id_b}/badges",
        json={"badge_type": "invalid_type"},
        headers=_auth(token_admin),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_badge_for_nonexistent_entity(client: AsyncClient, db):
    """Issuing badge to nonexistent entity fails."""
    token_admin, id_admin = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, id_admin)

    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"{ENTITIES_URL}/{fake_id}/badges",
        json={"badge_type": "email_verified"},
        headers=_auth(token_admin),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_multiple_badge_types(client: AsyncClient, db):
    """Can issue different badge types to same entity."""
    token_admin, id_admin = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, id_admin)
    token_b, id_b = await _setup_user(client, USER_B)

    for btype in ["email_verified", "identity_verified", "agentgraph_verified"]:
        resp = await client.post(
            f"{ENTITIES_URL}/{id_b}/badges",
            json={"badge_type": btype},
            headers=_auth(token_admin),
        )
        assert resp.status_code == 201

    resp = await client.get(f"{ENTITIES_URL}/{id_b}/badges")
    assert resp.json()["total"] == 3


# --- Audit Record Tests ---


@pytest.mark.asyncio
async def test_audit_requires_trust_threshold(client: AsyncClient, db):
    """Auditor with trust < 0.7 is rejected."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # User A has no trust score (defaults to 0.0)
    resp = await client.post(
        f"{ENTITIES_URL}/{id_b}/audit",
        json={"audit_type": "security", "result": "pass"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 403
    assert "trust score" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_audit_self_fails(client: AsyncClient, db):
    """Cannot audit yourself."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _set_trust_score(db, id_a, 0.9)

    resp = await client.post(
        f"{ENTITIES_URL}/{id_a}/audit",
        json={"audit_type": "security", "result": "pass"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 403
    assert "yourself" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_submit_audit_record_success(client: AsyncClient, db):
    """High-trust entity can submit audit record."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)
    await _set_trust_score(db, id_a, 0.85)

    resp = await client.post(
        f"{ENTITIES_URL}/{id_b}/audit",
        json={
            "audit_type": "security",
            "result": "pass",
            "findings": {"vulnerabilities": 0, "notes": "Clean audit"},
            "report_url": "https://reports.example.com/audit1",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["audit_type"] == "security"
    assert data["result"] == "pass"
    assert data["findings"]["vulnerabilities"] == 0
    assert data["report_url"] == "https://reports.example.com/audit1"


@pytest.mark.asyncio
async def test_list_audit_records(client: AsyncClient, db):
    """List audit records for an entity."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)
    await _set_trust_score(db, id_a, 0.85)

    await client.post(
        f"{ENTITIES_URL}/{id_b}/audit",
        json={"audit_type": "security", "result": "pass"},
        headers=_auth(token_a),
    )
    await client.post(
        f"{ENTITIES_URL}/{id_b}/audit",
        json={"audit_type": "compliance", "result": "partial"},
        headers=_auth(token_a),
    )

    resp = await client.get(f"{ENTITIES_URL}/{id_b}/audit-history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["audit_records"]) == 2


@pytest.mark.asyncio
async def test_list_audit_records_filter_type(client: AsyncClient, db):
    """Audit records can be filtered by type."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)
    await _set_trust_score(db, id_a, 0.85)

    await client.post(
        f"{ENTITIES_URL}/{id_b}/audit",
        json={"audit_type": "security", "result": "pass"},
        headers=_auth(token_a),
    )
    await client.post(
        f"{ENTITIES_URL}/{id_b}/audit",
        json={"audit_type": "compliance", "result": "fail"},
        headers=_auth(token_a),
    )

    resp = await client.get(
        f"{ENTITIES_URL}/{id_b}/audit-history",
        params={"audit_type": "security"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["audit_records"][0]["audit_type"] == "security"


@pytest.mark.asyncio
async def test_capability_audit_promotes_endorsements(client: AsyncClient, db):
    """Passing capability audit promotes endorsement tier to formally_audited."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)
    await _set_trust_score(db, id_b, 0.85)

    # Create an agent owned by A
    agent_id = await _create_agent(client, token_a)

    # B endorses the agent
    await client.post(
        f"{ENTITIES_URL}/{agent_id}/endorsements",
        json={"capability": "summarize"},
        headers=_auth(token_b),
    )

    # Check tier is community_verified
    resp = await client.get(f"{ENTITIES_URL}/{agent_id}/endorsements")
    assert resp.json()["endorsements"][0]["tier"] == "community_verified"

    # B audits the agent (capability audit, pass)
    resp = await client.post(
        f"{ENTITIES_URL}/{agent_id}/audit",
        json={"audit_type": "capability", "result": "pass"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 201

    # Endorsement should now be formally_audited
    resp = await client.get(f"{ENTITIES_URL}/{agent_id}/endorsements")
    assert resp.json()["endorsements"][0]["tier"] == "formally_audited"


@pytest.mark.asyncio
async def test_audit_nonexistent_entity(client: AsyncClient, db):
    """Audit of nonexistent entity fails."""
    token_a, id_a = await _setup_user(client, USER_A)
    await _set_trust_score(db, id_a, 0.85)

    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"{ENTITIES_URL}/{fake_id}/audit",
        json={"audit_type": "security", "result": "pass"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_audit_history_empty(client: AsyncClient, db):
    """Entity with no audits returns empty list."""
    token_a, id_a = await _setup_user(client, USER_A)
    resp = await client.get(f"{ENTITIES_URL}/{id_a}/audit-history")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["audit_records"] == []
