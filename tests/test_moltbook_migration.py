"""Tests for the Moltbook migration bridge."""
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

USER_OPERATOR = {
    "email": "moltbook_operator@test.com",
    "password": "Str0ngP@ss",
    "display_name": "MoltbookOperator",
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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Sample profiles ---

CLEAN_MOLTBOOK_PROFILE = {
    "username": "helpbot",
    "display_name": "HelpBot",
    "bio": "A helpful assistant bot migrated from Moltbook",
    "skills": ["summarization", "translation", "q_and_a"],
    "moltbook_id": "mb-12345",
    "version": "2.1.0",
}

LEAKED_CREDS_PROFILE = {
    "username": "leakybot",
    "display_name": "LeakyBot",
    "bio": "Bot with api_key='mb_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890' embedded",
    "skills": ["data_fetch"],
    "api_tokens": ["mb_token_leaked_12345678901234567890"],
    "moltbook_id": "mb-99999",
}

VULN_INDICATOR_PROFILE = {
    "username": "sketchybot",
    "display_name": "SketchyBot",
    "bio": "This bot was used for credential stuffing and mass message spam bot operations",
    "skills": ["brute_force_login"],
    "moltbook_id": "mb-66666",
}

MISSING_NAME_PROFILE = {
    "bio": "A bot with no name at all",
    "skills": ["something"],
}


# --- Unit tests for adapter ---


class TestTranslateProfile:
    """Unit tests for profile translation."""

    def test_translate_profile_maps_fields(self):
        from src.bridges.moltbook.adapter import translate_moltbook_profile

        result = translate_moltbook_profile(CLEAN_MOLTBOOK_PROFILE)
        assert result["display_name"] == "HelpBot"
        assert result["bio"] == "A helpful assistant bot migrated from Moltbook"
        assert "summarization" in result["capabilities"]
        assert "translation" in result["capabilities"]
        assert "q_and_a" in result["capabilities"]
        assert result["version"] == "2.1.0"
        assert result["framework_metadata"]["source"] == "moltbook"
        assert result["framework_metadata"]["moltbook_id"] == "mb-12345"
        assert result["framework_metadata"]["moltbook_username"] == "helpbot"
        assert result["framework_metadata"]["original_skill_count"] == 3

    def test_translate_profile_fallback_name(self):
        from src.bridges.moltbook.adapter import translate_moltbook_profile

        result = translate_moltbook_profile({"username": "fallbackbot"})
        assert result["display_name"] == "fallbackbot"

    def test_translate_profile_default_name(self):
        from src.bridges.moltbook.adapter import translate_moltbook_profile

        result = translate_moltbook_profile({})
        assert result["display_name"] == "Moltbook Bot"

    def test_translate_profile_dict_skills(self):
        from src.bridges.moltbook.adapter import translate_moltbook_profile

        profile = {
            "name": "DictSkillBot",
            "skills": [
                {"name": "search", "version": "1.0"},
                {"name": "translate"},
            ],
        }
        result = translate_moltbook_profile(profile)
        assert "search" in result["capabilities"]
        assert "translate" in result["capabilities"]


class TestValidateProfile:
    """Unit tests for profile validation."""

    def test_validate_profile_rejects_missing_name(self):
        from src.bridges.moltbook.adapter import validate_moltbook_profile

        errors = validate_moltbook_profile(MISSING_NAME_PROFILE)
        assert len(errors) >= 1
        assert any("name" in e.lower() or "display_name" in e.lower() for e in errors)

    def test_validate_profile_accepts_valid(self):
        from src.bridges.moltbook.adapter import validate_moltbook_profile

        errors = validate_moltbook_profile(CLEAN_MOLTBOOK_PROFILE)
        assert errors == []

    def test_validate_profile_rejects_long_name(self):
        from src.bridges.moltbook.adapter import validate_moltbook_profile

        errors = validate_moltbook_profile({
            "display_name": "x" * 101,
        })
        assert any("100" in e for e in errors)

    def test_validate_profile_rejects_empty_name(self):
        from src.bridges.moltbook.adapter import validate_moltbook_profile

        errors = validate_moltbook_profile({"display_name": "   "})
        assert len(errors) >= 1

    def test_validate_profile_rejects_non_list_skills(self):
        from src.bridges.moltbook.adapter import validate_moltbook_profile

        errors = validate_moltbook_profile({
            "display_name": "TestBot",
            "skills": "not_a_list",
        })
        assert any("list" in e.lower() for e in errors)


class TestSecurityScan:
    """Unit tests for security scanning."""

    def test_security_scan_flags_leaked_credentials(self):
        from src.bridges.moltbook.security import scan_moltbook_bot

        result = scan_moltbook_bot(LEAKED_CREDS_PROFILE)
        assert result["leaked_credentials"] is True
        assert result["risk_level"] == "critical"
        assert result["trust_penalty"] < 0.65
        assert len(result["findings"]) >= 1

    def test_security_scan_clean_profile(self):
        from src.bridges.moltbook.security import scan_moltbook_bot

        result = scan_moltbook_bot(CLEAN_MOLTBOOK_PROFILE)
        assert result["leaked_credentials"] is False
        assert result["risk_level"] == "clean"
        assert result["trust_penalty"] == 0.65

    def test_security_scan_vulnerability_indicators(self):
        from src.bridges.moltbook.security import scan_moltbook_bot

        result = scan_moltbook_bot(VULN_INDICATOR_PROFILE)
        assert result["risk_level"] in ("warning", "critical")
        assert len(result["vulnerability_indicators"]) >= 1
        assert "credential_stuffing" in result["vulnerability_indicators"]

    def test_security_scan_api_tokens_field(self):
        from src.bridges.moltbook.security import scan_moltbook_bot

        result = scan_moltbook_bot({
            "display_name": "TokenBot",
            "api_tokens": ["tok1", "tok2", "tok3"],
        })
        assert result["leaked_credentials"] is True
        assert any(
            f.get("type") == "exposed_api_tokens" for f in result["findings"]
        )

    def test_security_scan_bearer_token_detection(self):
        from src.bridges.moltbook.security import scan_moltbook_bot

        result = scan_moltbook_bot({
            "display_name": "BearerBot",
            "bio": "Uses Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9forAuth",
        })
        assert result["leaked_credentials"] is True

    def test_security_scan_redacts_sensitive_content(self):
        from src.bridges.moltbook.security import scan_moltbook_bot

        result = scan_moltbook_bot(LEAKED_CREDS_PROFILE)
        # Findings with leaked credentials should be redacted
        for finding in result["findings"]:
            if finding.get("type") == "leaked_credential":
                match_text = finding.get("match", "")
                # Should not contain the full token
                assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890" not in match_text


# --- Integration tests via HTTP client ---


@pytest.mark.asyncio
async def test_migration_endpoint_creates_entity(client: AsyncClient):
    """POST /migration/moltbook creates a provisional entity."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.post(
        "/api/v1/migration/moltbook",
        json=CLEAN_MOLTBOOK_PROFILE,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "HelpBot"
    assert data["framework_source"] == "moltbook"
    assert data["framework_trust_modifier"] == 0.65
    assert "migrated_from_moltbook" in data["badges"]
    assert data["claim_token"]  # non-empty
    assert data["did_web"].startswith("did:web:agentgraph.co:moltbook:")
    assert data["entity_id"]  # non-empty UUID string
    assert "security_scan" in data
    assert data["security_scan"]["risk_level"] == "clean"
    assert data["social_proof_badge_url"].startswith("/api/v1/badges/social-proof/moltbook/")


@pytest.mark.asyncio
async def test_migration_endpoint_requires_auth(client: AsyncClient):
    """POST /migration/moltbook requires authentication."""
    resp = await client.post(
        "/api/v1/migration/moltbook",
        json=CLEAN_MOLTBOOK_PROFILE,
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_migration_endpoint_rejects_invalid_profile(client: AsyncClient):
    """POST /migration/moltbook rejects profiles with no name."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.post(
        "/api/v1/migration/moltbook",
        json=MISSING_NAME_PROFILE,
        headers=_auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_migration_endpoint_with_leaked_creds(client: AsyncClient):
    """POST /migration/moltbook still creates entity but applies harsher penalty."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.post(
        "/api/v1/migration/moltbook",
        json=LEAKED_CREDS_PROFILE,
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["security_scan"]["leaked_credentials"] is True
    assert data["framework_trust_modifier"] < 0.65  # Harsher penalty applied


@pytest.mark.asyncio
async def test_migration_validate_endpoint(client: AsyncClient):
    """GET /migration/moltbook/validate does dry-run validation."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.get(
        "/api/v1/migration/moltbook/validate",
        params={"display_name": "ValidBot", "bio": "A test bot"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["errors"] == []
    assert data["translated_profile"] is not None
    assert data["translated_profile"]["display_name"] == "ValidBot"
    assert data["security_scan"] is not None
    assert data["security_scan"]["risk_level"] == "clean"


@pytest.mark.asyncio
async def test_migration_validate_endpoint_rejects_missing_name(client: AsyncClient):
    """GET /migration/moltbook/validate returns errors for missing name."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp = await client.get(
        "/api/v1/migration/moltbook/validate",
        params={"bio": "No name provided"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert len(data["errors"]) >= 1


@pytest.mark.asyncio
async def test_migration_validate_endpoint_requires_auth(client: AsyncClient):
    """GET /migration/moltbook/validate requires authentication."""
    resp = await client.get(
        "/api/v1/migration/moltbook/validate",
        params={"display_name": "TestBot"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_multiple_migrations_create_separate_entities(client: AsyncClient):
    """Each migration creates a distinct entity."""
    token, _ = await _setup_user(client, USER_OPERATOR)
    resp1 = await client.post(
        "/api/v1/migration/moltbook",
        json=CLEAN_MOLTBOOK_PROFILE,
        headers=_auth(token),
    )
    resp2 = await client.post(
        "/api/v1/migration/moltbook",
        json={**CLEAN_MOLTBOOK_PROFILE, "display_name": "HelpBot2", "username": "helpbot2"},
        headers=_auth(token),
    )
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["entity_id"] != resp2.json()["entity_id"]
