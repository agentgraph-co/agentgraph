"""Tests for the Trust Score v2 /aggregate API surface + the v1→v2 source map.

Pure unit tests for ``components_to_contributions``; integration tests drive the
``/api/v1/aggregate/{did}`` endpoints through the app with a seeded Entity and a
stubbed v1 composite (so the test doesn't depend on the full scoring graph).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import src.api.trust_aggregate_router as agg_router
from src.database import get_db
from src.main import app
from src.models import Entity, EntityType
from src.signing import get_public_key
from src.trust.aggregate_sources import components_to_contributions
from src.trust.envelope_v2 import verify_envelope
from src.trust.score import EXTERNAL_WEIGHT, SCAN_WEIGHT, VERIFICATION_WEIGHT

# v1 component keys exactly as score.py stores them.
_AGENT_COMPONENTS = {
    "verification": 0.6,
    "external_reputation": 0.4,
    "scan_score": 0.5,
    "activity": 0.9,  # weight 0 → must be dropped
    "community": 0.8,  # weight 0 → must be dropped
}

# ---- pure: components_to_contributions ----


def test_components_map_to_sources():
    contribs = components_to_contributions(_AGENT_COMPONENTS, is_human=False)
    by_component = {c.metadata["v1_component"]: c.source for c in contribs}
    assert by_component == {
        "verification": "self_attested",
        "external_reputation": "erc8004_reputation",
        "scan_score": "scan_corpus",
    }  # zero-weight activity/community dropped


def test_components_weighted_contribution_matches_v1_weights():
    contribs = components_to_contributions(
        {"verification": 0.6, "external_reputation": 0.4, "scan_score": 0.5},
        is_human=False,
    )
    weighted = {c.metadata["v1_component"]: c.weighted_contribution for c in contribs}
    assert weighted["verification"] == pytest.approx(VERIFICATION_WEIGHT * 0.6, abs=1e-4)
    assert weighted["external_reputation"] == pytest.approx(EXTERNAL_WEIGHT * 0.4, abs=1e-4)
    assert weighted["scan_score"] == pytest.approx(SCAN_WEIGHT * 0.5, abs=1e-4)
    # raw value preserved for transparent display
    assert contribs[0].raw_signal == 0.6


def test_human_gets_verification_bonus_and_no_scan():
    agent = components_to_contributions(
        {"verification": 1.0, "scan_score": 1.0}, is_human=False
    )
    human = components_to_contributions(
        {"verification": 1.0, "scan_score": 1.0}, is_human=True
    )
    a_verif = next(c for c in agent if c.metadata["v1_component"] == "verification")
    h_verif = next(c for c in human if c.metadata["v1_component"] == "verification")
    assert h_verif.weighted_contribution > a_verif.weighted_contribution  # +0.10 bonus
    # scan is zero-weight for humans → dropped entirely
    assert all(c.metadata["v1_component"] != "scan_score" for c in human)


def test_framework_modifier_scales_contributions():
    base = components_to_contributions({"verification": 1.0}, is_human=False)
    scaled = components_to_contributions(
        {"verification": 1.0}, is_human=False, framework_modifier=0.8
    )
    assert scaled[0].weighted_contribution == pytest.approx(
        base[0].weighted_contribution * 0.8, abs=1e-4
    )


def test_components_empty_or_none():
    assert components_to_contributions(None) == []
    assert components_to_contributions({}) == []
    assert components_to_contributions({"activity": 0.9}) == []  # only zero-weight


# ---- integration: /aggregate endpoints ----


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_did(db):
    did = f"did:web:aggsubj-{uuid.uuid4().hex[:8]}"
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="AggSubject",
        did_web=did,
        is_active=True,
    )
    db.add(entity)
    await db.flush()
    return did


def _stub_composite(monkeypatch, components):
    async def fake_compute(db, entity_id):
        return SimpleNamespace(id=entity_id, components=components)

    monkeypatch.setattr(agg_router, "compute_trust_score", fake_compute)


@pytest.mark.asyncio
async def test_aggregate_unknown_did_404(client):
    r = await client.get("/api/v1/aggregate/did:web:nobody.example")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_aggregate_no_signals_404(client, seeded_did, monkeypatch):
    _stub_composite(monkeypatch, {"activity": 0.9})  # only zero-weight → no contribs
    r = await client.get(f"/api/v1/aggregate/{seeded_did}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_aggregate_persists_envelope_row(client, seeded_did, monkeypatch, db):
    """Write-through: a /aggregate call persists a row in aggregate_envelopes."""
    from sqlalchemy import select

    from src.models import AggregateEnvelope

    _stub_composite(monkeypatch, {"verification": 0.6, "scan_score": 0.5})
    r = await client.get(f"/api/v1/aggregate/{seeded_did}")
    assert r.status_code == 200
    row = (
        await db.execute(
            select(AggregateEnvelope).where(
                AggregateEnvelope.subject_did == seeded_did
            )
        )
    ).scalar_one_or_none()
    assert row is not None
    assert row.envelope["subject_did"] == seeded_did
    assert row.trust_score == pytest.approx(r.json()["trust_score"], abs=1e-4)


@pytest.mark.asyncio
async def test_aggregate_happy_path_signed_and_verifiable(
    client, seeded_did, monkeypatch
):
    _stub_composite(
        monkeypatch,
        {"verification": 0.6, "external_reputation": 0.4, "scan_score": 0.5},
    )
    r = await client.get(f"/api/v1/aggregate/{seeded_did}")
    assert r.status_code == 200
    env = r.json()
    assert env["subject_did"] == seeded_did
    # trust_score equals the v1 composite: 0.35*0.6 + 0.35*0.4 + 0.20*0.5 = 0.45
    expected = VERIFICATION_WEIGHT * 0.6 + EXTERNAL_WEIGHT * 0.4 + SCAN_WEIGHT * 0.5
    assert env["trust_score"] == pytest.approx(expected, abs=1e-3)
    assert env["score_version"] == "v2.0"
    assert "proof" in env
    assert len(env["contributions"]) == 3
    assert verify_envelope(env, get_public_key()) is True
    assert env["freshness_ttl_seconds"] > 0


@pytest.mark.asyncio
async def test_contributions_endpoint(client, seeded_did, monkeypatch):
    _stub_composite(monkeypatch, {"scan_score": 0.5})
    r = await client.get(f"/api/v1/aggregate/{seeded_did}/contributions")
    assert r.status_code == 200
    body = r.json()
    assert body["subject_did"] == seeded_did
    assert body["contributions"][0]["source"] == "scan_corpus"


@pytest.mark.asyncio
async def test_verify_endpoint(client, seeded_did, monkeypatch):
    _stub_composite(monkeypatch, {"verification": 0.4, "scan_score": 0.2})
    r = await client.get(f"/api/v1/aggregate/{seeded_did}/verify")
    assert r.status_code == 200
    body = r.json()
    assert body["signature_valid"] is True
    assert body["fresh"] is True
    assert body["kid"]  # platform key id present
