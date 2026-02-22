"""Tests for SAML SSO endpoints."""
from __future__ import annotations

import base64
import json
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.database import get_db
from src.main import app

PREFIX = "/api/v1/sso"
ORG_PREFIX = "/api/v1/organizations"


@pytest_asyncio.fixture(autouse=True)
async def _enable_sso():
    """Enable SSO feature flag for all tests in this module."""
    original = settings.sso_enabled
    settings.sso_enabled = True
    yield
    settings.sso_enabled = original


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


async def _create_org_with_saml(client, token, org_name):
    """Create an org and configure SAML SSO."""
    resp = await client.post(
        ORG_PREFIX,
        json={"name": org_name, "display_name": f"Org {org_name}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    org_id = resp.json()["id"]
    # Configure SAML SSO
    await client.put(
        f"{PREFIX}/config/{org_id}",
        json={
            "provider": "saml",
            "enabled": True,
            "idp_sso_url": "https://idp.example.com/sso",
            "idp_entity_id": "https://idp.example.com",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    return org_id


def _make_saml_assertion(name_id, email=None, display_name=None):
    """Build a base64-encoded mock SAML assertion."""
    assertion = {
        "name_id": name_id,
        "attributes": {
            "email": email or name_id,
            "display_name": display_name or name_id.split("@")[0],
        },
        "session_index": f"_session_{uuid.uuid4().hex[:8]}",
    }
    return base64.b64encode(json.dumps(assertion).encode()).decode()


# --- Tests ---


@pytest.mark.asyncio
async def test_saml_login_initiation(client, db):
    token, _ = await _create_user(client, "saml1@test.com", "SamlUser1")
    org_id = await _create_org_with_saml(client, token, "saml-org-1")

    resp = await client.post(
        f"{PREFIX}/saml/login", json={"org_id": org_id}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "redirect_url" in data
    assert "request_id" in data
    assert "idp.example.com" in data["redirect_url"]


@pytest.mark.asyncio
async def test_saml_login_not_configured(client, db):
    token, _ = await _create_user(client, "saml2@test.com", "SamlUser2")
    # Create org without SSO config
    resp = await client.post(
        ORG_PREFIX,
        json={"name": "no-saml-org", "display_name": "No SAML"},
        headers={"Authorization": f"Bearer {token}"},
    )
    org_id = resp.json()["id"]

    resp = await client.post(
        f"{PREFIX}/saml/login", json={"org_id": org_id}
    )
    assert resp.status_code == 400
    assert "not configured" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_saml_callback_creates_entity(client, db):
    token, _ = await _create_user(client, "saml3@test.com", "SamlUser3")
    org_id = await _create_org_with_saml(client, token, "saml-org-3")

    assertion = _make_saml_assertion(
        "newuser@company.com", display_name="New User"
    )
    resp = await client.post(
        f"{PREFIX}/saml/callback",
        json={"saml_response": assertion, "org_id": org_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert "entity_id" in data


@pytest.mark.asyncio
async def test_saml_callback_finds_existing_entity(client, db):
    token, _ = await _create_user(client, "saml4@test.com", "SamlUser4")
    org_id = await _create_org_with_saml(client, token, "saml-org-4")

    assertion = _make_saml_assertion("repeat@company.com")
    # First call creates entity
    resp1 = await client.post(
        f"{PREFIX}/saml/callback",
        json={"saml_response": assertion, "org_id": org_id},
    )
    entity_id_1 = resp1.json()["entity_id"]

    # Second call finds existing entity
    resp2 = await client.post(
        f"{PREFIX}/saml/callback",
        json={"saml_response": assertion, "org_id": org_id},
    )
    entity_id_2 = resp2.json()["entity_id"]
    assert entity_id_1 == entity_id_2


@pytest.mark.asyncio
async def test_saml_callback_invalid_assertion(client, db):
    token, _ = await _create_user(client, "saml5@test.com", "SamlUser5")
    org_id = await _create_org_with_saml(client, token, "saml-org-5")

    resp = await client.post(
        f"{PREFIX}/saml/callback",
        json={"saml_response": "not-valid-base64!!!", "org_id": org_id},
    )
    assert resp.status_code == 401
    assert "Invalid SAML assertion" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_saml_callback_missing_name_id(client, db):
    token, _ = await _create_user(client, "saml6@test.com", "SamlUser6")
    org_id = await _create_org_with_saml(client, token, "saml-org-6")

    bad_assertion = base64.b64encode(
        json.dumps({"attributes": {"email": "no-nameid@co.com"}}).encode()
    ).decode()
    resp = await client.post(
        f"{PREFIX}/saml/callback",
        json={"saml_response": bad_assertion, "org_id": org_id},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_saml_metadata(client, db):
    token, _ = await _create_user(client, "saml7@test.com", "SamlUser7")
    resp = await client.post(
        ORG_PREFIX,
        json={"name": "meta-org", "display_name": "Meta Org"},
        headers={"Authorization": f"Bearer {token}"},
    )
    org_id = resp.json()["id"]

    resp = await client.get(f"{PREFIX}/saml/metadata/{org_id}")
    assert resp.status_code == 200
    assert "EntityDescriptor" in resp.text
    assert "agentgraph-sp" in resp.text
    assert "AssertionConsumerService" in resp.text


@pytest.mark.asyncio
async def test_saml_metadata_org_not_found(client, db):
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"{PREFIX}/saml/metadata/{fake_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sso_config_crud_saml(client, db):
    token, _ = await _create_user(client, "saml8@test.com", "SamlUser8")
    h = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        ORG_PREFIX,
        json={"name": "cfg-org", "display_name": "Cfg Org"},
        headers=h,
    )
    org_id = resp.json()["id"]

    # Set config
    put_resp = await client.put(
        f"{PREFIX}/config/{org_id}",
        json={
            "provider": "saml",
            "enabled": True,
            "idp_sso_url": "https://myidp.com/sso",
            "idp_entity_id": "https://myidp.com",
            "idp_certificate": "MIIC...",
        },
        headers=h,
    )
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert data["sso"]["provider"] == "saml"
    assert data["sso"]["idp_sso_url"] == "https://myidp.com/sso"

    # Get config (sensitive fields redacted)
    get_resp = await client.get(f"{PREFIX}/config/{org_id}", headers=h)
    assert get_resp.status_code == 200
    sso = get_resp.json()["sso"]
    assert sso["provider"] == "saml"
    assert sso["idp_certificate"] == "***"


@pytest.mark.asyncio
async def test_sso_config_unauthorized(client, db):
    token1, _ = await _create_user(client, "saml9@test.com", "Owner9")
    token2, _ = await _create_user(client, "saml9b@test.com", "NonMember9")
    h1 = {"Authorization": f"Bearer {token1}"}
    h2 = {"Authorization": f"Bearer {token2}"}
    resp = await client.post(
        ORG_PREFIX,
        json={"name": "priv-sso-org", "display_name": "Priv SSO"},
        headers=h1,
    )
    org_id = resp.json()["id"]

    # Non-member cannot read config
    get_resp = await client.get(f"{PREFIX}/config/{org_id}", headers=h2)
    assert get_resp.status_code == 403

    # Non-member cannot set config
    put_resp = await client.put(
        f"{PREFIX}/config/{org_id}",
        json={"provider": "saml", "enabled": True},
        headers=h2,
    )
    assert put_resp.status_code == 403
