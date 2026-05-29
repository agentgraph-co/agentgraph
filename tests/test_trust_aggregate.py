"""Tests for the Trust Score v2 /aggregate API surface + the v1→v2 source map.

Pure unit tests for ``components_to_signals``; integration tests drive the
``/api/v1/aggregate/{did}`` endpoints through the app with a seeded Entity and
a stubbed v1 composite (so the test doesn't depend on the full scoring graph).
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
from src.trust.aggregate_sources import components_to_signals
from src.trust.envelope_v2 import verify_envelope

# ---- pure: components_to_signals ----


def test_components_map_to_sources():
    sigs = components_to_signals({"scan": 0.2, "external": 0.3, "community": 0.1})
    by_src = {s.metadata["v1_component"]: s.source for s in sigs}
    assert by_src == {
        "scan": "scan_corpus",
        "external": "erc8004_reputation",
        "community": "community_signal",
    }


def test_components_skip_zero_and_nonnumeric():
    sigs = components_to_signals({"scan": 0.0, "age": None, "community": 0.1})
    assert len(sigs) == 1
    assert sigs[0].metadata["v1_component"] == "community"


def test_components_empty_or_none():
    assert components_to_signals(None) == []
    assert components_to_signals({}) == []


def test_components_preserve_value_and_passthrough_cap():
    sigs = components_to_signals({"verification": 0.35})
    assert sigs[0].raw_signal == pytest.approx(0.35)
    assert sigs[0].max_contribution == 1.0  # already-weighted; not re-capped


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
    _stub_composite(monkeypatch, {"scan": 0.0})  # all zero → no signals
    r = await client.get(f"/api/v1/aggregate/{seeded_did}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_aggregate_happy_path_signed_and_verifiable(
    client, seeded_did, monkeypatch
):
    _stub_composite(monkeypatch, {"scan": 0.2, "external": 0.3, "community": 0.1})
    r = await client.get(f"/api/v1/aggregate/{seeded_did}")
    assert r.status_code == 200
    env = r.json()
    assert env["subject_did"] == seeded_did
    assert env["trust_score"] == pytest.approx(0.6, abs=1e-4)  # sum of components
    assert env["score_version"] == "v2.0"
    assert "proof" in env
    assert len(env["contributions"]) == 3
    # the served envelope verifies against our published public key
    assert verify_envelope(env, get_public_key()) is True
    # freshness is carried in the envelope itself (a global no-cache middleware
    # overrides the response Cache-Control header, so consumers key off this).
    assert env["freshness_ttl_seconds"] > 0


@pytest.mark.asyncio
async def test_contributions_endpoint(client, seeded_did, monkeypatch):
    _stub_composite(monkeypatch, {"scan": 0.5})
    r = await client.get(f"/api/v1/aggregate/{seeded_did}/contributions")
    assert r.status_code == 200
    body = r.json()
    assert body["subject_did"] == seeded_did
    assert body["contributions"][0]["source"] == "scan_corpus"


@pytest.mark.asyncio
async def test_verify_endpoint(client, seeded_did, monkeypatch):
    _stub_composite(monkeypatch, {"scan": 0.4, "community": 0.2})
    r = await client.get(f"/api/v1/aggregate/{seeded_did}/verify")
    assert r.status_code == 200
    body = r.json()
    assert body["signature_valid"] is True
    assert body["fresh"] is True
    assert body["kid"]  # platform key id present
