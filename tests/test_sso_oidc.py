"""Tests for OIDC SSO endpoints."""
from __future__ import annotations

import base64
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app

PREFIX = "/api/v1/sso"
ORG_PREFIX = "/api/v1/organizations"


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
    body = {"email": email, "password": "Str0ngP@ss1", "display_name": name}
    await client.post("/api/v1/auth/register", json=body)
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Str0ngP@ss1"}
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    return token, me.json()["id"]


async def _create_org_with_oidc(client, token, org_name):
    """Create an org and configure OIDC SSO."""
    resp = await client.post(
        ORG_PREFIX,
        json={"name": org_name, "display_name": f"Org {org_name}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    org_id = resp.json()["id"]
    await client.put(
        f"{PREFIX}/config/{org_id}",
        json={
            "provider": "oidc",
            "enabled": True,
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
            "client_id": "agentgraph-client",
            "client_secret": "secret123",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    return org_id


def _make_oidc_code(sub, email=None, name=None):
    """Build a base64-encoded mock OIDC code."""
    userinfo = {
        "sub": sub,
        "email": email or f"{sub}@company.com",
        "name": name or sub,
    }
    return base64.b64encode(json.dumps(userinfo).encode()).decode()


# --- Tests ---


@pytest.mark.asyncio
async def test_oidc_login_initiation(client, db):
    token, _ = await _create_user(client, "oidc1@test.com", "OidcUser1")
    org_id = await _create_org_with_oidc(client, token, "oidc-org-1")

    resp = await client.get(f"{PREFIX}/oidc/login/{org_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "redirect_url" in data
    assert "state" in data
    assert "nonce" in data
    assert "idp.example.com" in data["redirect_url"]
    assert "agentgraph-client" in data["redirect_url"]


@pytest.mark.asyncio
async def test_oidc_login_not_configured(client, db):
    token, _ = await _create_user(client, "oidc2@test.com", "OidcUser2")
    resp = await client.post(
        ORG_PREFIX,
        json={"name": "no-oidc-org", "display_name": "No OIDC"},
        headers={"Authorization": f"Bearer {token}"},
    )
    org_id = resp.json()["id"]

    resp = await client.get(f"{PREFIX}/oidc/login/{org_id}")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_oidc_callback_creates_entity(client, db):
    token, _ = await _create_user(client, "oidc3@test.com", "OidcUser3")
    org_id = await _create_org_with_oidc(client, token, "oidc-org-3")

    code = _make_oidc_code("user-42", email="oidcnew@company.com", name="OIDC New")
    resp = await client.get(
        f"{PREFIX}/oidc/callback",
        params={"code": code, "state": "somestate", "org_id": org_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_oidc_callback_invalid_code(client, db):
    token, _ = await _create_user(client, "oidc4@test.com", "OidcUser4")
    org_id = await _create_org_with_oidc(client, token, "oidc-org-4")

    resp = await client.get(
        f"{PREFIX}/oidc/callback",
        params={"code": "garbage!!!", "state": "s", "org_id": org_id},
    )
    assert resp.status_code == 401
    assert "Invalid OIDC" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_oidc_callback_finds_existing_entity(client, db):
    token, _ = await _create_user(client, "oidc5@test.com", "OidcUser5")
    org_id = await _create_org_with_oidc(client, token, "oidc-org-5")

    code = _make_oidc_code("repeat-sub", email="oidcrepeat@company.com")
    resp1 = await client.get(
        f"{PREFIX}/oidc/callback",
        params={"code": code, "state": "s1", "org_id": org_id},
    )
    entity_id_1 = resp1.json()["entity_id"]

    resp2 = await client.get(
        f"{PREFIX}/oidc/callback",
        params={"code": code, "state": "s2", "org_id": org_id},
    )
    entity_id_2 = resp2.json()["entity_id"]
    assert entity_id_1 == entity_id_2
