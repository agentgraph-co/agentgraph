from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

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
ATTESTATIONS_URL = "/api/v1/attestations"

USER_ISSUER = {
    "email": "att_issuer@example.com",
    "password": "Str0ngP@ss",
    "display_name": "AttIssuer",
}
USER_SUBJECT = {
    "email": "att_subject@example.com",
    "password": "Str0ngP@ss",
    "display_name": "AttSubject",
}
USER_THIRD = {
    "email": "att_third@example.com",
    "password": "Str0ngP@ss",
    "display_name": "AttThird",
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


# --- Test: Create attestation ---


@pytest.mark.asyncio
async def test_create_attestation_success(client: AsyncClient, db):
    """Issuer can create a formal attestation about a subject entity."""
    token_issuer, id_issuer = await _setup_user(client, USER_ISSUER)
    token_subject, id_subject = await _setup_user(client, USER_SUBJECT)

    resp = await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_subject,
            "attestation_type": "identity_verified",
            "evidence": "KYC verification completed via third-party provider",
        },
        headers=_auth(token_issuer),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["issuer_entity_id"] == id_issuer
    assert data["subject_entity_id"] == id_subject
    assert data["attestation_type"] == "identity_verified"
    assert data["evidence"] == "KYC verification completed via third-party provider"
    assert data["is_revoked"] is False
    assert data["is_expired"] is False
    assert data["revoked_at"] is None


# --- Test: List attestations by subject ---


@pytest.mark.asyncio
async def test_list_attestations_by_subject(client: AsyncClient, db):
    """List attestations received by a subject entity."""
    token_issuer, id_issuer = await _setup_user(client, USER_ISSUER)
    token_subject, id_subject = await _setup_user(client, USER_SUBJECT)

    # Create two attestations
    await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_subject,
            "attestation_type": "identity_verified",
            "evidence": "KYC passed",
        },
        headers=_auth(token_issuer),
    )
    await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_subject,
            "attestation_type": "community_endorsed",
            "evidence": "Active community member",
        },
        headers=_auth(token_issuer),
    )

    resp = await client.get(f"{ATTESTATIONS_URL}/{id_subject}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["attestations"]) == 2
    types = {a["attestation_type"] for a in data["attestations"]}
    assert types == {"identity_verified", "community_endorsed"}


# --- Test: List attestations issued by entity ---


@pytest.mark.asyncio
async def test_list_attestations_issued_by_entity(client: AsyncClient, db):
    """List attestations issued by an entity."""
    token_issuer, id_issuer = await _setup_user(client, USER_ISSUER)
    token_subject, id_subject = await _setup_user(client, USER_SUBJECT)
    token_third, id_third = await _setup_user(client, USER_THIRD)

    # Issuer attests about subject and third
    await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_subject,
            "attestation_type": "capability_certified",
        },
        headers=_auth(token_issuer),
    )
    await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_third,
            "attestation_type": "operator_verified",
        },
        headers=_auth(token_issuer),
    )

    resp = await client.get(f"{ATTESTATIONS_URL}/{id_issuer}/issued")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    subjects = {a["subject_entity_id"] for a in data["attestations"]}
    assert id_subject in subjects
    assert id_third in subjects


# --- Test: Revoke attestation ---


@pytest.mark.asyncio
async def test_revoke_attestation(client: AsyncClient, db):
    """Issuer can revoke their own attestation."""
    token_issuer, id_issuer = await _setup_user(client, USER_ISSUER)
    token_subject, id_subject = await _setup_user(client, USER_SUBJECT)

    resp = await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_subject,
            "attestation_type": "security_audited",
            "evidence": "Security audit passed",
        },
        headers=_auth(token_issuer),
    )
    attestation_id = resp.json()["id"]

    # Revoke
    resp = await client.post(
        f"{ATTESTATIONS_URL}/{attestation_id}/revoke",
        headers=_auth(token_issuer),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Attestation revoked successfully"
    assert data["attestation_id"] == attestation_id
    assert data["revoked_at"] is not None

    # Verify it's excluded from default list
    resp = await client.get(f"{ATTESTATIONS_URL}/{id_subject}")
    assert resp.json()["total"] == 0

    # Verify it shows with include_revoked
    resp = await client.get(
        f"{ATTESTATIONS_URL}/{id_subject}",
        params={"include_revoked": "true"},
    )
    assert resp.json()["total"] == 1
    assert resp.json()["attestations"][0]["is_revoked"] is True


# --- Test: Non-issuer cannot revoke ---


@pytest.mark.asyncio
async def test_non_issuer_cannot_revoke(client: AsyncClient, db):
    """Only the original issuer can revoke an attestation."""
    token_issuer, id_issuer = await _setup_user(client, USER_ISSUER)
    token_subject, id_subject = await _setup_user(client, USER_SUBJECT)

    resp = await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_subject,
            "attestation_type": "community_endorsed",
        },
        headers=_auth(token_issuer),
    )
    attestation_id = resp.json()["id"]

    # Subject tries to revoke (should fail)
    resp = await client.post(
        f"{ATTESTATIONS_URL}/{attestation_id}/revoke",
        headers=_auth(token_subject),
    )
    assert resp.status_code == 403
    assert "issuer" in resp.json()["detail"].lower()


# --- Test: Duplicate prevention ---


@pytest.mark.asyncio
async def test_duplicate_attestation_prevented(client: AsyncClient, db):
    """Cannot create duplicate active attestation (same issuer, subject, type)."""
    token_issuer, id_issuer = await _setup_user(client, USER_ISSUER)
    token_subject, id_subject = await _setup_user(client, USER_SUBJECT)

    resp = await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_subject,
            "attestation_type": "identity_verified",
        },
        headers=_auth(token_issuer),
    )
    assert resp.status_code == 201

    # Try duplicate
    resp = await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_subject,
            "attestation_type": "identity_verified",
        },
        headers=_auth(token_issuer),
    )
    assert resp.status_code == 409
    assert "active attestation" in resp.json()["detail"].lower()


# --- Test: Expired attestation filtering ---


@pytest.mark.asyncio
async def test_expired_attestation_excluded_by_default(client: AsyncClient, db):
    """Expired attestations are hidden by default, visible with include_expired."""
    token_issuer, id_issuer = await _setup_user(client, USER_ISSUER)
    token_subject, id_subject = await _setup_user(client, USER_SUBJECT)

    # Create an attestation that expires in the past
    past = datetime.now(timezone.utc) - timedelta(days=1)
    resp = await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_subject,
            "attestation_type": "capability_certified",
            "expires_at": past.isoformat(),
        },
        headers=_auth(token_issuer),
    )
    assert resp.status_code == 201

    # Default list should exclude expired
    resp = await client.get(f"{ATTESTATIONS_URL}/{id_subject}")
    assert resp.json()["total"] == 0

    # With include_expired it should appear
    resp = await client.get(
        f"{ATTESTATIONS_URL}/{id_subject}",
        params={"include_expired": "true"},
    )
    assert resp.json()["total"] == 1
    assert resp.json()["attestations"][0]["is_expired"] is True


# --- Test: Self-attestation prevented ---


@pytest.mark.asyncio
async def test_self_attestation_prevented(client: AsyncClient, db):
    """Cannot create an attestation about yourself."""
    token_issuer, id_issuer = await _setup_user(client, USER_ISSUER)

    resp = await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_issuer,
            "attestation_type": "identity_verified",
        },
        headers=_auth(token_issuer),
    )
    assert resp.status_code == 403
    assert "yourself" in resp.json()["detail"].lower()


# --- Test: List attestation types ---


@pytest.mark.asyncio
async def test_list_attestation_types(client: AsyncClient, db):
    """List all available attestation types with descriptions."""
    token_issuer, _ = await _setup_user(client, USER_ISSUER)

    resp = await client.get(f"{ATTESTATIONS_URL}/types")
    assert resp.status_code == 200
    data = resp.json()
    assert "types" in data
    type_names = {t["attestation_type"] for t in data["types"]}
    assert type_names == {
        "identity_verified",
        "capability_certified",
        "security_audited",
        "operator_verified",
        "community_endorsed",
    }
    # Each type should have a description
    for t in data["types"]:
        assert len(t["description"]) > 0


# --- Test: Attestation for nonexistent entity ---


@pytest.mark.asyncio
async def test_attestation_for_nonexistent_entity(client: AsyncClient, db):
    """Creating attestation for nonexistent entity returns 404."""
    token_issuer, _ = await _setup_user(client, USER_ISSUER)

    fake_id = str(uuid.uuid4())
    resp = await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": fake_id,
            "attestation_type": "identity_verified",
        },
        headers=_auth(token_issuer),
    )
    assert resp.status_code == 404


# --- Test: Filter attestations by type ---


@pytest.mark.asyncio
async def test_filter_attestations_by_type(client: AsyncClient, db):
    """Can filter attestations by attestation_type query param."""
    token_issuer, id_issuer = await _setup_user(client, USER_ISSUER)
    token_subject, id_subject = await _setup_user(client, USER_SUBJECT)

    for att_type in ["identity_verified", "capability_certified", "community_endorsed"]:
        await client.post(
            ATTESTATIONS_URL,
            json={
                "subject_entity_id": id_subject,
                "attestation_type": att_type,
            },
            headers=_auth(token_issuer),
        )

    # Filter by identity_verified only
    resp = await client.get(
        f"{ATTESTATIONS_URL}/{id_subject}",
        params={"attestation_type": "identity_verified"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["attestations"][0]["attestation_type"] == "identity_verified"


# --- Test: Revoke then re-attest ---


@pytest.mark.asyncio
async def test_revoke_then_reattest(client: AsyncClient, db):
    """After revoking, issuer can create a new attestation of the same type."""
    token_issuer, id_issuer = await _setup_user(client, USER_ISSUER)
    token_subject, id_subject = await _setup_user(client, USER_SUBJECT)

    # Create
    resp = await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_subject,
            "attestation_type": "security_audited",
        },
        headers=_auth(token_issuer),
    )
    assert resp.status_code == 201
    att_id = resp.json()["id"]

    # Revoke
    resp = await client.post(
        f"{ATTESTATIONS_URL}/{att_id}/revoke",
        headers=_auth(token_issuer),
    )
    assert resp.status_code == 200

    # Re-attest should succeed (revoked one is cleaned up automatically)
    resp = await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_subject,
            "attestation_type": "security_audited",
        },
        headers=_auth(token_issuer),
    )
    assert resp.status_code == 201
    assert resp.json()["attestation_type"] == "security_audited"
    assert resp.json()["is_revoked"] is False


# --- Test: Unauthenticated request ---


@pytest.mark.asyncio
async def test_unauthenticated_create_fails(client: AsyncClient, db):
    """Unauthenticated users cannot create attestations."""
    token_subject, id_subject = await _setup_user(client, USER_SUBJECT)

    resp = await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_subject,
            "attestation_type": "identity_verified",
        },
    )
    assert resp.status_code == 401


# --- Test: Invalid attestation type ---


@pytest.mark.asyncio
async def test_invalid_attestation_type(client: AsyncClient, db):
    """Invalid attestation type is rejected."""
    token_issuer, id_issuer = await _setup_user(client, USER_ISSUER)
    token_subject, id_subject = await _setup_user(client, USER_SUBJECT)

    resp = await client.post(
        ATTESTATIONS_URL,
        json={
            "subject_entity_id": id_subject,
            "attestation_type": "totally_fake_type",
        },
        headers=_auth(token_issuer),
    )
    assert resp.status_code == 422
