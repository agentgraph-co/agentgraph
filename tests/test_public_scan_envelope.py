"""Tests for the Trust Score v2 envelope attached to /check scans (#117, §5.2).

Exercises ``_build_scan_envelope`` directly: Case A (scan-only, no entity) and
Case B (repo maps to a known entity). The full public_scan endpoint hits GitHub,
so we test the envelope builder in isolation.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

import src.trust.score as score_mod
from src.api.public_scan_router import _build_scan_envelope
from src.models import Entity, EntityType
from src.signing import get_public_key
from src.trust.envelope_v2 import verify_envelope
from src.trust.score import SCAN_WEIGHT, VERIFICATION_WEIGHT


@pytest.mark.asyncio
async def test_scan_envelope_case_a_scan_only(db):
    # random repo name → no matching entity → Case A
    owner, repo = "ownr", f"repo-{uuid.uuid4().hex[:8]}"
    scan = {"trust_score": 58, "scan_result": "clean", "findings": {"total": 3}}
    env = await _build_scan_envelope(owner, repo, scan, db)
    assert env is not None
    assert env["subject_did"] == f"did:web:github.com:{owner}:{repo}"
    assert env["subject_kind"] == "service"
    assert len(env["contributions"]) == 1
    assert env["contributions"][0]["source"] == "scan_corpus"
    assert env["trust_score"] == pytest.approx(0.58, abs=1e-3)
    assert verify_envelope(env, get_public_key()) is True


@pytest.mark.asyncio
async def test_scan_envelope_case_a_zero_score_none(db):
    owner, repo = "ownr", f"repo-{uuid.uuid4().hex[:8]}"
    env = await _build_scan_envelope(owner, repo, {"trust_score": 0}, db)
    assert env is None  # nothing to attest


@pytest.mark.asyncio
async def test_scan_envelope_case_b_known_entity(db, monkeypatch):
    owner, repo = "kb", f"repo-{uuid.uuid4().hex[:8]}"
    did = f"did:web:kb-{uuid.uuid4().hex[:8]}"
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="KnownBot",
        did_web=did,
        is_active=True,
        source_url=f"https://github.com/{owner}/{repo}",
    )
    db.add(entity)
    await db.flush()

    async def fake_compute(db_, entity_id):
        return SimpleNamespace(
            id=entity_id, components={"verification": 0.6, "scan_score": 0.5}
        )

    monkeypatch.setattr(score_mod, "compute_trust_score", fake_compute)

    env = await _build_scan_envelope(owner, repo, {"trust_score": 50}, db)
    assert env is not None
    assert env["subject_did"] == did  # resolved to the entity, not synthetic
    expected = VERIFICATION_WEIGHT * 0.6 + SCAN_WEIGHT * 0.5
    assert env["trust_score"] == pytest.approx(expected, abs=1e-3)
    assert verify_envelope(env, get_public_key()) is True
