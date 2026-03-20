from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import TrustAttestation, TrustScore


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

USER_A = {
    "email": "domain_a@test.com",
    "password": "Str0ngP@ss",
    "display_name": "DomainA",
}
USER_B = {
    "email": "domain_b@test.com",
    "password": "Str0ngP@ss",
    "display_name": "DomainB",
}


async def _setup(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_trust_domains(client: AsyncClient):
    """GET /trust/domains returns predefined domains."""
    resp = await client.get("/api/v1/trust/domains")
    assert resp.status_code == 200
    data = resp.json()
    assert "domains" in data
    domain_ids = [d["id"] for d in data["domains"]]
    assert "code_review" in domain_ids
    assert "security_audit" in domain_ids


@pytest.mark.asyncio
async def test_domains_include_attestation_counts(client: AsyncClient, db):
    """Domains reflect attestation counts."""
    token_a, id_a = await _setup(client, USER_A)
    token_b, id_b = await _setup(client, USER_B)

    # Create attestation with context
    att = TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=id_a,
        target_entity_id=id_b,
        attestation_type="competent",
        context="code_review",
        weight=0.5,
    )
    db.add(att)
    await db.flush()

    resp = await client.get("/api/v1/trust/domains")
    assert resp.status_code == 200
    domains = {d["id"]: d for d in resp.json()["domains"]}
    assert domains["code_review"]["entity_count"] >= 1


@pytest.mark.asyncio
async def test_domain_leaders_empty(client: AsyncClient):
    """Leaders endpoint returns empty for domain with no data."""
    resp = await client.get(
        "/api/v1/trust/domains/nonexistent_domain/leaders"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "nonexistent_domain"
    assert data["leaders"] == []
    assert data["count"] == 0


@pytest.mark.asyncio
async def test_domain_leaders_with_data(client: AsyncClient, db):
    """Leaders endpoint returns ranked entities."""
    token_a, id_a = await _setup(client, USER_A)

    # Update trust score with contextual data
    from sqlalchemy import update as _sa_update
    await db.execute(
        _sa_update(TrustScore)
        .where(TrustScore.entity_id == uuid.UUID(id_a))
        .values(score=0.6, components={"verification": 0.5}, contextual_scores={"code_review": 0.8})
    )
    await db.flush()

    resp = await client.get(
        "/api/v1/trust/domains/code_review/leaders"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    leader = data["leaders"][0]
    assert leader["entity_id"] == id_a
    assert leader["domain_score"] == 0.8
    assert leader["base_score"] == 0.6
    # blended = 0.7*0.6 + 0.3*0.8 = 0.66
    assert abs(leader["blended_score"] - 0.66) < 0.01


@pytest.mark.asyncio
async def test_custom_domains_from_attestations(client: AsyncClient, db):
    """Custom domains appear from attestation contexts."""
    token_a, id_a = await _setup(client, USER_A)
    token_b, id_b = await _setup(client, USER_B)

    att = TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=id_a,
        target_entity_id=id_b,
        attestation_type="reliable",
        context="quantum_computing",
        weight=0.5,
    )
    db.add(att)
    await db.flush()

    resp = await client.get("/api/v1/trust/domains")
    domain_ids = [d["id"] for d in resp.json()["domains"]]
    assert "quantum_computing" in domain_ids
