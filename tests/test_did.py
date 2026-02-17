from __future__ import annotations

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
DID_URL = "/api/v1/did"

USER = {
    "email": "did@test.com",
    "password": "Str0ngP@ss",
    "display_name": "DIDUser",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str, str]:
    """Register + login, return (token, entity_id, did_web)."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    me_data = me.json()
    return token, me_data["id"], me_data["did_web"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_resolve_did_by_entity_id(client: AsyncClient):
    _, entity_id, _ = await _setup_user(client, USER)

    resp = await client.get(f"{DID_URL}/entity/{entity_id}")
    assert resp.status_code == 200
    doc = resp.json()
    assert "@context" in doc
    assert "did:web:" in doc["id"]
    assert len(doc["verificationMethod"]) >= 1
    assert len(doc["service"]) >= 1


@pytest.mark.asyncio
async def test_resolve_did_by_did_uri(client: AsyncClient):
    _, entity_id, did_web = await _setup_user(client, USER)

    resp = await client.get(f"{DID_URL}/resolve", params={"uri": did_web})
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["id"] == did_web


@pytest.mark.asyncio
async def test_resolve_did_not_found(client: AsyncClient):
    resp = await client.get(f"{DID_URL}/entity/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_did_document_add_service(client: AsyncClient):
    token, entity_id, _ = await _setup_user(client, USER)

    resp = await client.patch(
        f"{DID_URL}/entity/{entity_id}",
        json={
            "service": [
                {
                    "id": "did:web:test#api",
                    "type": "AgentAPI",
                    "serviceEndpoint": "https://my-agent.example.com/api",
                }
            ]
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    doc = resp.json()
    endpoints = [s["serviceEndpoint"] for s in doc["service"]]
    assert "https://my-agent.example.com/api" in endpoints


@pytest.mark.asyncio
async def test_update_did_document_not_owner(client: AsyncClient):
    token_a, _, _ = await _setup_user(client, USER)
    _, id_b, _ = await _setup_user(
        client,
        {"email": "other@did.com", "password": "Str0ngP@ss", "display_name": "Other"},
    )

    resp = await client.patch(
        f"{DID_URL}/entity/{id_b}",
        json={"service": []},
        headers=_auth(token_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_did_has_w3c_context(client: AsyncClient):
    _, entity_id, _ = await _setup_user(client, USER)

    resp = await client.get(f"{DID_URL}/entity/{entity_id}")
    doc = resp.json()
    assert "https://www.w3.org/ns/did/v1" in doc["@context"]


@pytest.mark.asyncio
async def test_did_has_authentication(client: AsyncClient):
    _, entity_id, _ = await _setup_user(client, USER)

    resp = await client.get(f"{DID_URL}/entity/{entity_id}")
    doc = resp.json()
    assert len(doc["authentication"]) >= 1
    assert "#key-1" in doc["authentication"][0]
