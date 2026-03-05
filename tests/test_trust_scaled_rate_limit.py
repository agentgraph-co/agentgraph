from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.rate_limit import (
    RateLimitTier,
    _resolve_tier,
    _trust_scaled_limit,
    get_tier_info,
)
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

USER = {
    "email": "ratelimit-test@test.com",
    "password": "Str0ngP@ss",
    "display_name": "RateLimitUser",
}


async def _setup_user(client: AsyncClient, user: dict) -> str:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL,
        json={"email": user["email"], "password": user["password"]},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Unit tests for scaling function ---


class TestTrustScaledLimit:
    def test_none_score_returns_base(self):
        assert _trust_scaled_limit(100, None) == 100

    def test_zero_score_returns_base(self):
        assert _trust_scaled_limit(100, 0.0) == 100

    def test_negative_score_returns_base(self):
        assert _trust_scaled_limit(100, -0.5) == 100

    def test_score_0_5_gives_1_5x(self):
        assert _trust_scaled_limit(100, 0.5) == 150

    def test_score_0_7_gives_2x(self):
        assert _trust_scaled_limit(100, 0.7) == 200

    def test_score_0_9_gives_3x(self):
        assert _trust_scaled_limit(100, 0.9) == 300

    def test_score_1_0_gives_3_5x(self):
        assert _trust_scaled_limit(100, 1.0) == 350

    def test_score_above_1_capped(self):
        # Scores above 1.0 are capped at 1.0
        assert _trust_scaled_limit(100, 1.5) == 350

    def test_intermediate_score_0_3(self):
        # 0.3 is in [0, 0.5] range: multiplier = 1.0 + 0.3 = 1.3
        assert _trust_scaled_limit(100, 0.3) == 130

    def test_intermediate_score_0_8(self):
        # 0.8 is in [0.7, 0.9] range: multiplier = 2.0 + (0.1)*5.0 = 2.5
        assert _trust_scaled_limit(100, 0.8) == 250

    def test_with_different_base(self):
        # 300 reads * 2.0x at 0.7 = 600
        assert _trust_scaled_limit(300, 0.7) == 600


# --- Unit tests for tier resolution ---


class TestTierResolution:
    def test_none_entity_is_anonymous(self):
        assert _resolve_tier(None) == RateLimitTier.ANONYMOUS

    def test_human_entity(self):
        class FakeHuman:
            type = type("E", (), {"value": "human"})()

        assert _resolve_tier(FakeHuman()) == RateLimitTier.HUMAN

    def test_agent_entity(self):
        class FakeAgent:
            type = type("E", (), {"value": "agent"})()
            is_provisional = False

        assert _resolve_tier(FakeAgent()) == RateLimitTier.AGENT

    def test_provisional_agent(self):
        class FakeAgent:
            type = type("E", (), {"value": "agent"})()
            is_provisional = True

        assert _resolve_tier(FakeAgent()) == RateLimitTier.PROVISIONAL


# --- Tests for tier info ---


class TestTierInfo:
    def test_get_tier_info(self):
        info = get_tier_info()
        assert "tiers" in info
        assert "trust_scaling_info" in info
        tier_names = [t["tier"] for t in info["tiers"]]
        assert "anonymous" in tier_names
        assert "human" in tier_names
        assert "agent" in tier_names
        assert "trusted_agent" in tier_names

    def test_trust_scaling_multipliers(self):
        info = get_tier_info()
        multipliers = info["trust_scaling_info"]["multipliers"]
        assert multipliers["0.7"] == "2.0x"
        assert multipliers["1.0"] == "3.5x"


# --- API endpoint tests ---


@pytest.mark.asyncio
async def test_list_tiers_endpoint(client):
    resp = await client.get("/api/v1/rate-limits/tiers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tiers"]) == 5
    assert data["trust_scaling_info"]["multipliers"]["0.9"] == "3.0x"


@pytest.mark.asyncio
async def test_my_rate_limit_anonymous(client):
    resp = await client.get("/api/v1/rate-limits/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "anonymous"
    assert data["trust_score"] is None
    assert data["trust_scaling_applied"] is False


@pytest.mark.asyncio
async def test_my_rate_limit_authenticated(client):
    token = await _setup_user(client, USER)
    resp = await client.get(
        "/api/v1/rate-limits/me", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "human"
    assert "limits" in data
    assert data["limits"]["reads_per_minute"]["base"] > 0
    assert data["limits"]["writes_per_minute"]["base"] > 0
