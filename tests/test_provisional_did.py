"""Tests for PROVISIONAL/FULL DID state machine (Task #195).

Covers:
- DID status creation (PROVISIONAL for unowned agents, FULL for owned)
- GET /api/v1/did/{did}/status endpoint
- POST /api/v1/did/{did}/promote endpoint (admin only)
- Auto-promotion via trust score threshold
- Auto-promotion via operator_verified attestation
- PROVISIONAL DID restrictions (cannot attest others)
- DID status upgrade on agent claim
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.database import get_db
from src.main import app
from src.models import DIDDocument, DIDStatus, Entity, TrustScore


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
AGENT_REGISTER_URL = "/api/v1/agents/register"
AGENT_CLAIM_URL = "/api/v1/agents/claim"
DID_URL = "/api/v1/did"
ATTEST_URL = "/api/v1/attestations"

ADMIN_USER = {
    "email": "did_admin@example.com",
    "password": "Str0ngP@ss",
    "display_name": "DIDAdmin",
}

REGULAR_USER = {
    "email": "did_regular@example.com",
    "password": "Str0ngP@ss",
    "display_name": "DIDRegular",
}

OPERATOR_USER = {
    "email": "did_operator@example.com",
    "password": "Str0ngP@ss",
    "display_name": "DIDOperator",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register + login, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    return token, me.json()["id"]


async def _make_admin(db, entity_id: str) -> None:
    """Promote entity to admin directly in DB."""
    entity = await db.get(Entity, uuid.UUID(entity_id))
    entity.is_admin = True
    await db.flush()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Test DID status on registration ---


@pytest.mark.asyncio
async def test_provisional_agent_gets_provisional_did_status(client: AsyncClient, db):
    """Agent registered without operator should have a PROVISIONAL DID document."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "ProvDIDBot", "capabilities": ["chat"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    agent_id = data["agent"]["id"]

    # Verify DID document in DB has PROVISIONAL status
    did_doc = await db.scalar(
        select(DIDDocument).where(DIDDocument.entity_id == uuid.UUID(agent_id))
    )
    assert did_doc is not None
    assert did_doc.did_status == DIDStatus.PROVISIONAL


@pytest.mark.asyncio
async def test_full_agent_gets_full_did_status(client: AsyncClient, db):
    """Agent registered with operator should have a FULL DID document."""
    token, _ = await _setup_user(client, OPERATOR_USER)

    resp = await client.post(
        AGENT_REGISTER_URL,
        json={
            "display_name": "FullDIDBot",
            "capabilities": ["chat"],
            "operator_email": OPERATOR_USER["email"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    agent_id = data["agent"]["id"]

    did_doc = await db.scalar(
        select(DIDDocument).where(DIDDocument.entity_id == uuid.UUID(agent_id))
    )
    assert did_doc is not None
    assert did_doc.did_status == DIDStatus.FULL


# --- Test GET /did/{did}/status ---


@pytest.mark.asyncio
async def test_get_did_status_provisional(client: AsyncClient, db):
    """GET /did/{did}/status returns PROVISIONAL for unclaimed agent."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "StatusCheckBot", "capabilities": ["chat"]},
    )
    agent_did = resp.json()["agent"]["did_web"]

    status_resp = await client.get(f"{DID_URL}/{agent_did}/status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["did_status"] == "provisional"
    assert data["is_provisional"] is True
    assert data["did_uri"] == agent_did


@pytest.mark.asyncio
async def test_get_did_status_full(client: AsyncClient, db):
    """GET /did/{did}/status returns FULL for agent with operator."""
    token, _ = await _setup_user(client, OPERATOR_USER)

    resp = await client.post(
        AGENT_REGISTER_URL,
        json={
            "display_name": "FullStatusBot",
            "capabilities": ["chat"],
            "operator_email": OPERATOR_USER["email"],
        },
    )
    agent_did = resp.json()["agent"]["did_web"]

    status_resp = await client.get(f"{DID_URL}/{agent_did}/status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["did_status"] == "full"
    assert data["is_provisional"] is False


@pytest.mark.asyncio
async def test_get_did_status_not_found(client: AsyncClient, db):
    """GET /did/{did}/status returns 404 for non-existent DID."""
    fake_did = f"did:web:agentgraph.io:agents:{uuid.uuid4()}"
    status_resp = await client.get(f"{DID_URL}/{fake_did}/status")
    assert status_resp.status_code == 404


# --- Test POST /did/{did}/promote (admin only) ---


@pytest.mark.asyncio
async def test_admin_can_promote_provisional_did(client: AsyncClient, db):
    """Admin can promote a PROVISIONAL DID to FULL via the promote endpoint."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    # Register provisional agent
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "PromoteBot", "capabilities": ["chat"]},
    )
    agent_did = resp.json()["agent"]["did_web"]
    agent_id = resp.json()["agent"]["id"]

    # Promote
    promote_resp = await client.post(
        f"{DID_URL}/{agent_did}/promote",
        json={"reason": "manual_review_passed"},
        headers=_auth(admin_token),
    )
    assert promote_resp.status_code == 200
    data = promote_resp.json()
    assert data["old_status"] == "provisional"
    assert data["new_status"] == "full"
    assert data["promotion_reason"] == "manual_review_passed"
    assert data["promoted_at"] is not None

    # Verify DID document in DB
    did_doc = await db.scalar(
        select(DIDDocument).where(DIDDocument.entity_id == uuid.UUID(agent_id))
    )
    assert did_doc.did_status == DIDStatus.FULL
    assert did_doc.promotion_reason == "manual_review_passed"
    assert did_doc.promoted_by == uuid.UUID(admin_id)

    # Entity should also no longer be provisional
    entity = await db.get(Entity, uuid.UUID(agent_id))
    assert entity.is_provisional is False


@pytest.mark.asyncio
async def test_non_admin_cannot_promote_did(client: AsyncClient, db):
    """Non-admin users cannot promote a DID."""
    user_token, _ = await _setup_user(client, REGULAR_USER)

    resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "NoPromoteBot", "capabilities": ["chat"]},
    )
    agent_did = resp.json()["agent"]["did_web"]

    promote_resp = await client.post(
        f"{DID_URL}/{agent_did}/promote",
        json={"reason": "attempt"},
        headers=_auth(user_token),
    )
    assert promote_resp.status_code == 403


@pytest.mark.asyncio
async def test_promote_already_full_did_returns_400(client: AsyncClient, db):
    """Promoting an already-FULL DID returns 400."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)
    _, _ = await _setup_user(client, OPERATOR_USER)

    resp = await client.post(
        AGENT_REGISTER_URL,
        json={
            "display_name": "AlreadyFullBot",
            "capabilities": ["chat"],
            "operator_email": OPERATOR_USER["email"],
        },
    )
    agent_did = resp.json()["agent"]["did_web"]

    promote_resp = await client.post(
        f"{DID_URL}/{agent_did}/promote",
        json={"reason": "test"},
        headers=_auth(admin_token),
    )
    assert promote_resp.status_code == 400
    assert "already" in promote_resp.json()["detail"].lower()


# --- Test auto-promotion via trust score ---


@pytest.mark.asyncio
async def test_auto_promote_on_trust_score_threshold(client: AsyncClient, db):
    """DID auto-promotes to FULL when entity reaches trust score >= 0.3."""
    # Register provisional agent
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "TrustPromoteBot", "capabilities": ["chat"]},
    )
    agent_id = uuid.UUID(resp.json()["agent"]["id"])

    # Manually set trust score above threshold
    trust = TrustScore(
        id=uuid.uuid4(),
        entity_id=agent_id,
        score=0.35,
        components={"test": 0.35},
    )
    db.add(trust)
    await db.flush()

    # Import and run auto-promotion check
    from src.api.did_router import check_auto_promotion, promote_did_to_full

    entity = await db.get(Entity, agent_id)
    reason = await check_auto_promotion(db, entity)
    assert reason is not None
    assert "trust_score" in reason

    # Actually promote
    did_doc = await db.scalar(
        select(DIDDocument).where(DIDDocument.entity_id == agent_id)
    )
    assert did_doc.did_status == DIDStatus.PROVISIONAL
    await promote_did_to_full(db, did_doc, reason=reason)

    # Verify
    await db.refresh(did_doc)
    assert did_doc.did_status == DIDStatus.FULL
    await db.refresh(entity)
    assert entity.is_provisional is False


@pytest.mark.asyncio
async def test_no_auto_promote_below_threshold(client: AsyncClient, db):
    """DID stays PROVISIONAL if trust score is below threshold."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "LowTrustBot", "capabilities": ["chat"]},
    )
    agent_id = uuid.UUID(resp.json()["agent"]["id"])

    trust = TrustScore(
        id=uuid.uuid4(),
        entity_id=agent_id,
        score=0.15,
        components={"test": 0.15},
    )
    db.add(trust)
    await db.flush()

    from src.api.did_router import check_auto_promotion

    entity = await db.get(Entity, agent_id)
    reason = await check_auto_promotion(db, entity)
    assert reason is None


# --- Test auto-promotion via operator attestation ---


@pytest.mark.asyncio
async def test_auto_promote_on_operator_attestation(client: AsyncClient, db):
    """DID auto-promotes when an operator_verified attestation is received."""
    # Register human operator
    operator_token, operator_id = await _setup_user(client, OPERATOR_USER)

    # Register provisional agent
    reg_resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "AttestPromoteBot", "capabilities": ["chat"]},
    )
    agent_id = reg_resp.json()["agent"]["id"]

    # Create operator_verified attestation (triggers auto-promotion)
    attest_resp = await client.post(
        ATTEST_URL,
        json={
            "subject_entity_id": agent_id,
            "attestation_type": "operator_verified",
            "evidence": "Manual verification complete",
        },
        headers=_auth(operator_token),
    )
    assert attest_resp.status_code == 201

    # Verify DID was auto-promoted
    did_doc = await db.scalar(
        select(DIDDocument).where(
            DIDDocument.entity_id == uuid.UUID(agent_id)
        )
    )
    assert did_doc.did_status == DIDStatus.FULL
    assert did_doc.promotion_reason == "operator_attestation_received"

    entity = await db.get(Entity, uuid.UUID(agent_id))
    assert entity.is_provisional is False


# --- Test PROVISIONAL DID restrictions ---


@pytest.mark.asyncio
async def test_provisional_did_cannot_attest_others(client: AsyncClient, db):
    """Agents with PROVISIONAL DID cannot issue attestations."""
    # Register regular user (attestation target)
    _, target_id = await _setup_user(client, REGULAR_USER)

    # Register provisional agent
    reg_resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "NoAttestBot", "capabilities": ["chat"]},
    )
    api_key = reg_resp.json()["api_key"]

    # Try to create attestation (should be blocked)
    attest_resp = await client.post(
        ATTEST_URL,
        json={
            "subject_entity_id": target_id,
            "attestation_type": "community_endorsed",
            "evidence": "test",
        },
        headers={"X-API-Key": api_key},
    )
    assert attest_resp.status_code == 403
    assert "provisional" in attest_resp.json()["detail"].lower()


# --- Test DID status upgrade on claim ---


@pytest.mark.asyncio
async def test_claim_upgrades_did_status(client: AsyncClient, db):
    """Claiming a provisional agent also upgrades DID document status."""
    operator_token, operator_id = await _setup_user(client, OPERATOR_USER)

    # Register provisional agent
    reg_resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "ClaimDIDBot", "capabilities": ["chat"]},
    )
    claim_token = reg_resp.json()["claim_token"]
    agent_id = reg_resp.json()["agent"]["id"]

    # Verify DID is PROVISIONAL
    did_doc = await db.scalar(
        select(DIDDocument).where(DIDDocument.entity_id == uuid.UUID(agent_id))
    )
    assert did_doc.did_status == DIDStatus.PROVISIONAL

    # Claim the agent
    claim_resp = await client.post(
        AGENT_CLAIM_URL,
        json={"claim_token": claim_token},
        headers=_auth(operator_token),
    )
    assert claim_resp.status_code == 200

    # Verify DID is now FULL
    await db.refresh(did_doc)
    assert did_doc.did_status == DIDStatus.FULL
    assert did_doc.promotion_reason == "operator_claim"
    assert did_doc.promoted_by == uuid.UUID(operator_id)


# --- Test DID document includes status ---


@pytest.mark.asyncio
async def test_resolved_did_includes_status(client: AsyncClient, db):
    """Resolved DID document includes didStatus field."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "ResolveStatusBot", "capabilities": ["chat"]},
    )
    agent_did = resp.json()["agent"]["did_web"]
    agent_id = resp.json()["agent"]["id"]

    # Resolve by entity ID
    resolve_resp = await client.get(f"{DID_URL}/entity/{agent_id}")
    assert resolve_resp.status_code == 200
    doc = resolve_resp.json()
    assert doc["didStatus"] == "provisional"

    # Resolve by DID URI
    resolve_resp2 = await client.get(f"{DID_URL}/resolve", params={"uri": agent_did})
    assert resolve_resp2.status_code == 200
    doc2 = resolve_resp2.json()
    assert doc2["didStatus"] == "provisional"


@pytest.mark.asyncio
async def test_promote_default_reason(client: AsyncClient, db):
    """Promote endpoint uses default reason 'admin_approval' if no body."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "DefaultReasonBot", "capabilities": ["chat"]},
    )
    agent_did = resp.json()["agent"]["did_web"]

    # Promote without explicit reason (send empty body)
    promote_resp = await client.post(
        f"{DID_URL}/{agent_did}/promote",
        headers=_auth(admin_token),
    )
    assert promote_resp.status_code == 200
    data = promote_resp.json()
    assert data["promotion_reason"] == "admin_approval"
