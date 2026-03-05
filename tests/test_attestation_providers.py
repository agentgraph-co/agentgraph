from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from src.database import get_db
from src.main import app
from src.models import Entity


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
PROVIDERS_URL = "/api/v1/attestation-providers"

USER_OPERATOR = {
    "email": "ap_operator@example.com",
    "password": "Str0ngP@ss",
    "display_name": "APOperator",
}
USER_SUBJECT = {
    "email": "ap_subject@example.com",
    "password": "Str0ngP@ss",
    "display_name": "APSubject",
}
USER_ADMIN = {
    "email": "ap_admin@example.com",
    "password": "Str0ngP@ss",
    "display_name": "APAdmin",
}
USER_OTHER = {
    "email": "ap_other@example.com",
    "password": "Str0ngP@ss",
    "display_name": "APOther",
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
    stmt = update(Entity).where(
        Entity.id == uuid.UUID(entity_id),
    ).values(is_admin=True)
    await db.execute(stmt)
    await db.flush()


# --- Test: Register a provider ---


@pytest.mark.asyncio
async def test_register_provider_success(client: AsyncClient, db):
    """An authenticated user can register as an attestation provider."""
    token, entity_id = await _setup_user(client, USER_OPERATOR)

    resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "IdentityVerifier",
            "provider_url": "https://identity-verifier.example.com",
            "supported_attestation_types": ["identity_verified", "operator_verified"],
            "description": "KYC identity verification service",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["provider_name"] == "IdentityVerifier"
    assert data["is_active"] is False
    assert "api_key" in data
    assert len(data["api_key"]) > 20
    assert "provider_id" in data


@pytest.mark.asyncio
async def test_register_provider_duplicate_name(client: AsyncClient, db):
    """Registering a provider with an existing name is rejected."""
    token, _ = await _setup_user(client, USER_OPERATOR)

    body = {
        "provider_name": "DuplicateProvider",
        "supported_attestation_types": ["identity_verified"],
    }
    resp1 = await client.post(
        f"{PROVIDERS_URL}/register", json=body, headers=_auth(token),
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        f"{PROVIDERS_URL}/register", json=body, headers=_auth(token),
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_register_provider_unauthenticated(client: AsyncClient, db):
    """Unauthenticated requests cannot register a provider."""
    resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "NoAuth",
            "supported_attestation_types": ["identity_verified"],
        },
    )
    assert resp.status_code == 401


# --- Test: List providers ---


@pytest.mark.asyncio
async def test_list_providers(client: AsyncClient, db):
    """Public listing of providers works."""
    token, _ = await _setup_user(client, USER_OPERATOR)

    # Register a provider
    await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "ListTestProvider",
            "supported_attestation_types": ["security_audited"],
        },
        headers=_auth(token),
    )

    resp = await client.get(PROVIDERS_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert "total" in data
    assert data["total"] >= 1
    names = [p["provider_name"] for p in data["providers"]]
    assert "ListTestProvider" in names


# --- Test: Get provider detail ---


@pytest.mark.asyncio
async def test_get_provider_detail(client: AsyncClient, db):
    """Get full details for a registered provider."""
    token, entity_id = await _setup_user(client, USER_OPERATOR)

    reg_resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "DetailTestProvider",
            "provider_url": "https://detail.example.com",
            "supported_attestation_types": ["identity_verified"],
            "description": "Test description",
        },
        headers=_auth(token),
    )
    provider_id = reg_resp.json()["provider_id"]

    resp = await client.get(f"{PROVIDERS_URL}/{provider_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_name"] == "DetailTestProvider"
    assert data["provider_url"] == "https://detail.example.com"
    assert data["description"] == "Test description"
    assert data["operator_entity_id"] == entity_id
    assert data["is_active"] is False
    assert data["attestation_count"] == 0


@pytest.mark.asyncio
async def test_get_provider_not_found(client: AsyncClient, db):
    """Getting a nonexistent provider returns 404."""
    resp = await client.get(f"{PROVIDERS_URL}/{uuid.uuid4()}")
    assert resp.status_code == 404


# --- Test: Admin approve provider ---


@pytest.mark.asyncio
async def test_approve_provider(client: AsyncClient, db):
    """Admin can approve a pending provider."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    token_admin, admin_id = await _setup_user(client, USER_ADMIN)
    await _make_admin(db, admin_id)

    reg_resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "ApproveTestProvider",
            "supported_attestation_types": ["identity_verified"],
        },
        headers=_auth(token_op),
    )
    provider_id = reg_resp.json()["provider_id"]

    resp = await client.post(
        f"{PROVIDERS_URL}/{provider_id}/approve",
        headers=_auth(token_admin),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_active"] is True
    assert data["provider_id"] == provider_id


@pytest.mark.asyncio
async def test_approve_provider_non_admin_rejected(client: AsyncClient, db):
    """Non-admin cannot approve a provider."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)

    reg_resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "NonAdminApproveTest",
            "supported_attestation_types": ["identity_verified"],
        },
        headers=_auth(token_op),
    )
    provider_id = reg_resp.json()["provider_id"]

    resp = await client.post(
        f"{PROVIDERS_URL}/{provider_id}/approve",
        headers=_auth(token_op),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_approve_already_active(client: AsyncClient, db):
    """Approving an already-active provider returns 409."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    token_admin, admin_id = await _setup_user(client, USER_ADMIN)
    await _make_admin(db, admin_id)

    reg_resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "AlreadyActiveTest",
            "supported_attestation_types": ["identity_verified"],
        },
        headers=_auth(token_op),
    )
    provider_id = reg_resp.json()["provider_id"]

    await client.post(
        f"{PROVIDERS_URL}/{provider_id}/approve",
        headers=_auth(token_admin),
    )
    resp = await client.post(
        f"{PROVIDERS_URL}/{provider_id}/approve",
        headers=_auth(token_admin),
    )
    assert resp.status_code == 409


# --- Test: Admin revoke provider ---


@pytest.mark.asyncio
async def test_revoke_provider(client: AsyncClient, db):
    """Admin can revoke an active provider."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    token_admin, admin_id = await _setup_user(client, USER_ADMIN)
    await _make_admin(db, admin_id)

    reg_resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "RevokeTestProvider",
            "supported_attestation_types": ["identity_verified"],
        },
        headers=_auth(token_op),
    )
    provider_id = reg_resp.json()["provider_id"]

    # Approve first
    await client.post(
        f"{PROVIDERS_URL}/{provider_id}/approve",
        headers=_auth(token_admin),
    )

    # Revoke
    resp = await client.post(
        f"{PROVIDERS_URL}/{provider_id}/revoke",
        headers=_auth(token_admin),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_active"] is False


@pytest.mark.asyncio
async def test_revoke_already_inactive(client: AsyncClient, db):
    """Revoking an already-inactive provider returns 409."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    token_admin, admin_id = await _setup_user(client, USER_ADMIN)
    await _make_admin(db, admin_id)

    reg_resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "AlreadyInactiveTest",
            "supported_attestation_types": ["identity_verified"],
        },
        headers=_auth(token_op),
    )
    provider_id = reg_resp.json()["provider_id"]

    resp = await client.post(
        f"{PROVIDERS_URL}/{provider_id}/revoke",
        headers=_auth(token_admin),
    )
    assert resp.status_code == 409


# --- Test: Submit attestation via provider ---


@pytest.mark.asyncio
async def test_submit_attestation_success(client: AsyncClient, db):
    """An active provider can submit an attestation via API key."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    _, subject_id = await _setup_user(client, USER_SUBJECT)
    token_admin, admin_id = await _setup_user(client, USER_ADMIN)
    await _make_admin(db, admin_id)

    # Register provider
    reg_resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "SubmitTestProvider",
            "supported_attestation_types": ["identity_verified", "security_audited"],
        },
        headers=_auth(token_op),
    )
    provider_id = reg_resp.json()["provider_id"]
    api_key = reg_resp.json()["api_key"]

    # Approve
    await client.post(
        f"{PROVIDERS_URL}/{provider_id}/approve",
        headers=_auth(token_admin),
    )

    # Submit attestation
    resp = await client.post(
        f"{PROVIDERS_URL}/{provider_id}/submit",
        json={
            "subject_entity_id": subject_id,
            "attestation_type": "identity_verified",
            "evidence": "KYC check passed via provider",
        },
        headers={"X-Provider-Key": api_key},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["subject_entity_id"] == subject_id
    assert data["attestation_type"] == "identity_verified"
    assert data["provider_id"] == provider_id

    # Verify attestation count incremented
    detail_resp = await client.get(f"{PROVIDERS_URL}/{provider_id}")
    assert detail_resp.json()["attestation_count"] == 1


@pytest.mark.asyncio
async def test_submit_attestation_inactive_provider(client: AsyncClient, db):
    """An inactive provider cannot submit attestations."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    _, subject_id = await _setup_user(client, USER_SUBJECT)

    reg_resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "InactiveSubmitTest",
            "supported_attestation_types": ["identity_verified"],
        },
        headers=_auth(token_op),
    )
    provider_id = reg_resp.json()["provider_id"]
    api_key = reg_resp.json()["api_key"]

    resp = await client.post(
        f"{PROVIDERS_URL}/{provider_id}/submit",
        json={
            "subject_entity_id": subject_id,
            "attestation_type": "identity_verified",
        },
        headers={"X-Provider-Key": api_key},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_submit_attestation_invalid_key(client: AsyncClient, db):
    """Invalid API key is rejected."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    token_admin, admin_id = await _setup_user(client, USER_ADMIN)
    await _make_admin(db, admin_id)

    reg_resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "InvalidKeyTest",
            "supported_attestation_types": ["identity_verified"],
        },
        headers=_auth(token_op),
    )
    provider_id = reg_resp.json()["provider_id"]

    await client.post(
        f"{PROVIDERS_URL}/{provider_id}/approve",
        headers=_auth(token_admin),
    )

    resp = await client.post(
        f"{PROVIDERS_URL}/{provider_id}/submit",
        json={
            "subject_entity_id": str(uuid.uuid4()),
            "attestation_type": "identity_verified",
        },
        headers={"X-Provider-Key": "totally-bogus-key"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_submit_attestation_no_key(client: AsyncClient, db):
    """Missing X-Provider-Key header returns 401."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)

    reg_resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "NoKeyTest",
            "supported_attestation_types": ["identity_verified"],
        },
        headers=_auth(token_op),
    )
    provider_id = reg_resp.json()["provider_id"]

    resp = await client.post(
        f"{PROVIDERS_URL}/{provider_id}/submit",
        json={
            "subject_entity_id": str(uuid.uuid4()),
            "attestation_type": "identity_verified",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_submit_attestation_unsupported_type(client: AsyncClient, db):
    """Provider cannot submit attestation type not in supported_types."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    _, subject_id = await _setup_user(client, USER_SUBJECT)
    token_admin, admin_id = await _setup_user(client, USER_ADMIN)
    await _make_admin(db, admin_id)

    reg_resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "UnsupportedTypeTest",
            "supported_attestation_types": ["identity_verified"],
        },
        headers=_auth(token_op),
    )
    provider_id = reg_resp.json()["provider_id"]
    api_key = reg_resp.json()["api_key"]

    await client.post(
        f"{PROVIDERS_URL}/{provider_id}/approve",
        headers=_auth(token_admin),
    )

    resp = await client.post(
        f"{PROVIDERS_URL}/{provider_id}/submit",
        json={
            "subject_entity_id": subject_id,
            "attestation_type": "security_audited",
        },
        headers={"X-Provider-Key": api_key},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_attestation_wrong_provider(client: AsyncClient, db):
    """API key for provider A cannot submit to provider B's endpoint."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    token_other, _ = await _setup_user(client, USER_OTHER)
    _, subject_id = await _setup_user(client, USER_SUBJECT)
    token_admin, admin_id = await _setup_user(client, USER_ADMIN)
    await _make_admin(db, admin_id)

    # Register provider A
    reg_a = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "ProviderA",
            "supported_attestation_types": ["identity_verified"],
        },
        headers=_auth(token_op),
    )
    api_key_a = reg_a.json()["api_key"]

    # Register provider B
    reg_b = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "ProviderB",
            "supported_attestation_types": ["identity_verified"],
        },
        headers=_auth(token_other),
    )
    provider_b_id = reg_b.json()["provider_id"]

    # Approve both
    await client.post(
        f"{PROVIDERS_URL}/{reg_a.json()['provider_id']}/approve",
        headers=_auth(token_admin),
    )
    await client.post(
        f"{PROVIDERS_URL}/{provider_b_id}/approve",
        headers=_auth(token_admin),
    )

    # Try to use provider A's key on provider B's endpoint
    resp = await client.post(
        f"{PROVIDERS_URL}/{provider_b_id}/submit",
        json={
            "subject_entity_id": subject_id,
            "attestation_type": "identity_verified",
        },
        headers={"X-Provider-Key": api_key_a},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_submit_attestation_subject_not_found(client: AsyncClient, db):
    """Submitting attestation for a nonexistent subject returns 404."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    token_admin, admin_id = await _setup_user(client, USER_ADMIN)
    await _make_admin(db, admin_id)

    reg_resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "SubjectNotFoundTest",
            "supported_attestation_types": ["identity_verified"],
        },
        headers=_auth(token_op),
    )
    provider_id = reg_resp.json()["provider_id"]
    api_key = reg_resp.json()["api_key"]

    await client.post(
        f"{PROVIDERS_URL}/{provider_id}/approve",
        headers=_auth(token_admin),
    )

    resp = await client.post(
        f"{PROVIDERS_URL}/{provider_id}/submit",
        json={
            "subject_entity_id": str(uuid.uuid4()),
            "attestation_type": "identity_verified",
        },
        headers={"X-Provider-Key": api_key},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_submit_attestation_self_attest_blocked(client: AsyncClient, db):
    """Provider operator cannot attest for themselves."""
    token_op, op_id = await _setup_user(client, USER_OPERATOR)
    token_admin, admin_id = await _setup_user(client, USER_ADMIN)
    await _make_admin(db, admin_id)

    reg_resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "SelfAttestTest",
            "supported_attestation_types": ["identity_verified"],
        },
        headers=_auth(token_op),
    )
    provider_id = reg_resp.json()["provider_id"]
    api_key = reg_resp.json()["api_key"]

    await client.post(
        f"{PROVIDERS_URL}/{provider_id}/approve",
        headers=_auth(token_admin),
    )

    resp = await client.post(
        f"{PROVIDERS_URL}/{provider_id}/submit",
        json={
            "subject_entity_id": op_id,
            "attestation_type": "identity_verified",
        },
        headers={"X-Provider-Key": api_key},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_submit_attestation_duplicate_blocked(client: AsyncClient, db):
    """Duplicate active attestation (same type, subject) is rejected."""
    token_op, _ = await _setup_user(client, USER_OPERATOR)
    _, subject_id = await _setup_user(client, USER_SUBJECT)
    token_admin, admin_id = await _setup_user(client, USER_ADMIN)
    await _make_admin(db, admin_id)

    reg_resp = await client.post(
        f"{PROVIDERS_URL}/register",
        json={
            "provider_name": "DuplicateAttTest",
            "supported_attestation_types": ["identity_verified"],
        },
        headers=_auth(token_op),
    )
    provider_id = reg_resp.json()["provider_id"]
    api_key = reg_resp.json()["api_key"]

    await client.post(
        f"{PROVIDERS_URL}/{provider_id}/approve",
        headers=_auth(token_admin),
    )

    # First submission should succeed
    resp1 = await client.post(
        f"{PROVIDERS_URL}/{provider_id}/submit",
        json={
            "subject_entity_id": subject_id,
            "attestation_type": "identity_verified",
            "evidence": "First attestation",
        },
        headers={"X-Provider-Key": api_key},
    )
    assert resp1.status_code == 201

    # Second submission with same type + subject should be rejected
    resp2 = await client.post(
        f"{PROVIDERS_URL}/{provider_id}/submit",
        json={
            "subject_entity_id": subject_id,
            "attestation_type": "identity_verified",
            "evidence": "Duplicate attestation",
        },
        headers={"X-Provider-Key": api_key},
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_approve_provider_not_found(client: AsyncClient, db):
    """Approving a nonexistent provider returns 404."""
    token_admin, admin_id = await _setup_user(client, USER_ADMIN)
    await _make_admin(db, admin_id)

    resp = await client.post(
        f"{PROVIDERS_URL}/{uuid.uuid4()}/approve",
        headers=_auth(token_admin),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_provider_not_found(client: AsyncClient, db):
    """Revoking a nonexistent provider returns 404."""
    token_admin, admin_id = await _setup_user(client, USER_ADMIN)
    await _make_admin(db, admin_id)

    resp = await client.post(
        f"{PROVIDERS_URL}/{uuid.uuid4()}/revoke",
        headers=_auth(token_admin),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_providers_pagination(client: AsyncClient, db):
    """Provider listing supports pagination."""
    token, _ = await _setup_user(client, USER_OPERATOR)

    # Register several providers
    for i in range(3):
        await client.post(
            f"{PROVIDERS_URL}/register",
            json={
                "provider_name": f"PaginationProvider{i}",
                "supported_attestation_types": ["identity_verified"],
            },
            headers=_auth(token),
        )

    # Get page with limit=2
    resp = await client.get(f"{PROVIDERS_URL}?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["providers"]) <= 2
    assert data["total"] >= 3
