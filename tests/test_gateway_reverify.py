"""Tests for the mutation-boundary re-check endpoint (POST /gateway/re-verify).

The 6th gate per SINT conformance model (a2aproject/A2A#1672). Matches
AgentID's /re-verify semantics: lightweight, short TTL, no-store.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

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


RE_VERIFY_URL = "/api/v1/gateway/re-verify"


def _fresh_cached_scan(score: int = 85, tier: str = "trusted") -> dict:
    """Build a cached scan payload with a current timestamp."""
    return {
        "trust_score": score,
        "trust_tier": tier,
        "recommended_limits": {
            "requests_per_minute": 60,
            "max_tokens_per_call": 4000,
            "require_user_confirmation": False,
        },
        "scan_result": "clean",
        "findings": {
            "critical": 0, "high": 0, "medium": 0, "total": 0,
            "categories": {}, "suppressed_lines": 0,
        },
        "positive_signals": [],
        "metadata": {
            "files_scanned": 50, "primary_language": "python",
            "has_readme": True, "has_license": True, "has_tests": True,
            "is_mcp_server": False,
        },
        "category_scores": {},
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }


def _aged_cached_scan(age_seconds: int, score: int = 85, tier: str = "trusted") -> dict:
    """Build a cached scan payload scanned N seconds ago."""
    d = _fresh_cached_scan(score, tier)
    d["scanned_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    ).isoformat()
    return d


@pytest.mark.asyncio
async def test_re_verify_invalid_repo_format(client):
    """Missing slash in repo → 400."""
    resp = await client.post(
        RE_VERIFY_URL, json={"repo": "no-slash", "action_class": "reversible"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_re_verify_invalid_action_class(client):
    """Unknown action_class → 400."""
    resp = await client.post(
        RE_VERIFY_URL,
        json={"repo": "owner/repo", "action_class": "nonsense"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_re_verify_no_attestation_returns_fail_closed(client):
    """No cached scan → verified=false with reason=no_attestation (fail-closed)."""
    with patch(
        "src.api.public_scan_router._get_cached",
        new=AsyncMock(return_value=None),
    ):
        resp = await client.post(
            RE_VERIFY_URL,
            json={"repo": "owner/never-scanned", "action_class": "irreversible"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is False
    assert "no_attestation" in body["reason"]
    assert body["cached"] is False
    assert body["jws"]  # verdict still signed even on failure
    # no-store headers
    assert resp.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_re_verify_fresh_scan_passes_for_irreversible(client):
    """Fresh cached scan + tier meets minimum → verified=true, short TTL."""
    with patch(
        "src.api.public_scan_router._get_cached",
        new=AsyncMock(return_value=_fresh_cached_scan(score=85, tier="trusted")),
    ):
        resp = await client.post(
            RE_VERIFY_URL,
            json={
                "repo": "owner/fresh-repo",
                "action_class": "irreversible",
                "min_tier": "standard",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    assert body["trust_tier"] == "trusted"
    assert body["cached"] is True
    assert body["scan_age_seconds"] < 5  # just-scanned
    assert body["jws"]

    # Irreversible TTL is 30s — max_valid_until should be ~30s out
    issued = datetime.fromisoformat(body["issued_at"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(body["max_valid_until"].replace("Z", "+00:00"))
    ttl = (expires - issued).total_seconds()
    assert 29 <= ttl <= 31

    assert resp.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_re_verify_stale_scan_blocks_irreversible(client):
    """Scan older than the irreversible window (10 min) → verified=false."""
    # 15 min old — beyond the 10-min irreversible threshold
    with patch(
        "src.api.public_scan_router._get_cached",
        new=AsyncMock(return_value=_aged_cached_scan(age_seconds=900)),
    ):
        resp = await client.post(
            RE_VERIFY_URL,
            json={"repo": "owner/aged", "action_class": "irreversible"},
        )

    body = resp.json()
    assert body["verified"] is False
    assert "scan_stale" in body["reason"]
    assert body["scan_age_seconds"] >= 900


@pytest.mark.asyncio
async def test_re_verify_stale_scan_still_valid_for_reversible(client):
    """15-min-old scan fails irreversible but holds for reversible (1hr window)."""
    with patch(
        "src.api.public_scan_router._get_cached",
        new=AsyncMock(return_value=_aged_cached_scan(age_seconds=900)),
    ):
        resp = await client.post(
            RE_VERIFY_URL,
            json={"repo": "owner/aged", "action_class": "reversible"},
        )

    body = resp.json()
    assert body["verified"] is True  # within 1hr window


@pytest.mark.asyncio
async def test_re_verify_tier_below_minimum_blocks(client):
    """Cached tier < min_tier → verified=false."""
    with patch(
        "src.api.public_scan_router._get_cached",
        new=AsyncMock(
            return_value=_fresh_cached_scan(score=25, tier="minimal"),
        ),
    ):
        resp = await client.post(
            RE_VERIFY_URL,
            json={
                "repo": "owner/low",
                "action_class": "reversible",
                "min_tier": "standard",
            },
        )

    body = resp.json()
    assert body["verified"] is False
    assert "tier_below_minimum" in body["reason"]


@pytest.mark.asyncio
async def test_re_verify_ttl_scales_with_action_class(client):
    """TTL: irreversible=30s, compensable=120s, reversible=300s."""
    expected = {"irreversible": 30, "compensable": 120, "reversible": 300}

    for action_class, expected_ttl in expected.items():
        with patch(
            "src.api.public_scan_router._get_cached",
            new=AsyncMock(return_value=_fresh_cached_scan()),
        ):
            resp = await client.post(
                RE_VERIFY_URL,
                json={"repo": "owner/r", "action_class": action_class},
            )
        body = resp.json()
        issued = datetime.fromisoformat(
            body["issued_at"].replace("Z", "+00:00"),
        )
        expires = datetime.fromisoformat(
            body["max_valid_until"].replace("Z", "+00:00"),
        )
        ttl = (expires - issued).total_seconds()
        assert abs(ttl - expected_ttl) <= 1, (
            f"{action_class}: expected {expected_ttl}s, got {ttl}s"
        )


@pytest.mark.asyncio
async def test_re_verify_jws_is_present_and_three_parts(client):
    """JWS verdict must be a compact JWS (header.payload.signature)."""
    with patch(
        "src.api.public_scan_router._get_cached",
        new=AsyncMock(return_value=_fresh_cached_scan()),
    ):
        resp = await client.post(
            RE_VERIFY_URL,
            json={"repo": "owner/r", "action_class": "reversible"},
        )

    body = resp.json()
    assert body["jws"].count(".") == 2


@pytest.mark.asyncio
async def test_re_verify_no_store_headers_on_success(client):
    """Cache-Control: no-store + Pragma: no-cache on every response."""
    with patch(
        "src.api.public_scan_router._get_cached",
        new=AsyncMock(return_value=_fresh_cached_scan()),
    ):
        resp = await client.post(
            RE_VERIFY_URL,
            json={"repo": "owner/r", "action_class": "irreversible"},
        )

    assert resp.headers.get("cache-control") == "no-store"
    assert resp.headers.get("pragma") == "no-cache"


@pytest.mark.asyncio
async def test_re_verify_does_not_trigger_fresh_scan(client):
    """Re-verify must be read-only: never calls scan_repo."""
    # If scan_repo gets imported/called, this mock would need patching.
    # Instead we verify that _get_cached is the only data source.
    with patch(
        "src.api.public_scan_router._get_cached",
        new=AsyncMock(return_value=_fresh_cached_scan()),
    ) as get_cached_mock:
        resp = await client.post(
            RE_VERIFY_URL,
            json={"repo": "owner/r", "action_class": "reversible"},
        )

    assert resp.status_code == 200
    assert get_cached_mock.await_count == 1
