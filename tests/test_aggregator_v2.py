"""Tests for the Trust Score v2 aggregation engine (src/trust/aggregator_v2.py).

Pure-function tests — no DB, no app fixtures. Covers the §4 pipeline:
caps, freshness decay, provider-diversity weighting, conflict resolution,
the negative-feedback floor, and an end-to-end sign/verify round-trip.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.trust import aggregation_params as params
from src.trust.aggregator_v2 import (
    RawSignal,
    aggregate,
    freshness_decay,
    provider_diversity_weight,
)
from src.trust.envelope_v2 import (
    EnvelopeError,
    sign_envelope,
    verify_envelope,
)

NOW = datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc)


def _sig(**kw) -> RawSignal:
    """RawSignal with sensible fresh defaults; override per test."""
    base = dict(
        source="ctef_attestation",
        raw_signal=0.5,
        signed_at=NOW,
        freshness_ttl_seconds=86_400,
        claim_type="identity",
        source_provider_did="did:web:issuer-a.example",
    )
    base.update(kw)
    return RawSignal(**base)


# ---- freshness_decay ----


def test_freshness_decay_zero_age_is_one():
    assert freshness_decay(0) == 1.0
    assert freshness_decay(-100) == 1.0


def test_freshness_decay_one_half_life():
    decayed = freshness_decay(params.FRESHNESS_HALF_LIFE_SECONDS)
    assert decayed == pytest.approx(math.exp(-1), rel=1e-6)


def test_freshness_decay_monotonic_decreasing():
    assert freshness_decay(100) > freshness_decay(1000) > freshness_decay(100_000)


# ---- provider_diversity_weight ----


@pytest.mark.parametrize(
    "n,expected",
    [
        (0, params.PROVIDER_DIVERSITY_WEIGHT_MANY),
        (1, params.PROVIDER_DIVERSITY_WEIGHT_SINGLE),
        (2, params.PROVIDER_DIVERSITY_WEIGHT_FEW),
        (3, params.PROVIDER_DIVERSITY_WEIGHT_FEW),
        (4, params.PROVIDER_DIVERSITY_WEIGHT_MANY),
        (10, params.PROVIDER_DIVERSITY_WEIGHT_MANY),
    ],
)
def test_provider_diversity_tiers(n, expected):
    assert provider_diversity_weight(n) == expected


# ---- aggregate: basic shape ----


def test_aggregate_produces_valid_envelope():
    env = aggregate(
        subject_did="did:web:agent.example",
        subject_kind="agent",
        signals=[_sig(raw_signal=0.8)],
        now=NOW,
    )
    assert env["subject_did"] == "did:web:agent.example"
    assert env["score_version"] == "v2.0"
    assert env["shape_version"] == "trust-score-envelope-v2.0"
    assert len(env["contributions"]) == 1
    assert "proof" not in env  # unsigned
    assert 0.0 <= env["trust_score"] <= 1.0


def test_aggregate_empty_raises():
    with pytest.raises(EnvelopeError):
        aggregate(
            subject_did="did:web:x.example",
            subject_kind="agent",
            signals=[],
            now=NOW,
        )


# ---- §4 (1): per-claim_type cap ----


def test_identity_cap_bounds_contribution():
    # raw_signal 0.99 but identity cap is 0.60; single provider → 0.7 diversity.
    env = aggregate(
        subject_did="did:web:agent.example",
        subject_kind="agent",
        signals=[_sig(raw_signal=0.99, claim_type="identity")],
        now=NOW,
    )
    wc = env["contributions"][0]["weighted_contribution"]
    # capped 0.60 * decay(0)=1.0 * diversity(1)=0.7
    assert wc == pytest.approx(0.60 * params.PROVIDER_DIVERSITY_WEIGHT_SINGLE, abs=1e-4)


def test_transport_claim_contributes_zero():
    env = aggregate(
        subject_did="did:web:agent.example",
        subject_kind="agent",
        signals=[
            _sig(raw_signal=0.5, claim_type="identity"),
            _sig(raw_signal=0.9, claim_type="transport",
                 source_provider_did="did:web:issuer-b.example"),
        ],
        now=NOW,
    )
    transport = [c for c in env["contributions"] if c["claim_type"] == "transport"][0]
    assert transport["weighted_contribution"] == 0.0


# ---- §4 (2): freshness decay ----


def test_aged_signal_decays():
    old = _sig(raw_signal=0.5, signed_at=NOW - timedelta(days=1))
    env = aggregate(
        subject_did="did:web:agent.example",
        subject_kind="agent",
        signals=[old],
        now=NOW,
    )
    wc = env["contributions"][0]["weighted_contribution"]
    # min(0.5, 0.60 cap)=0.5 * decay(1 day)=e^-1 * diversity(1)=0.7
    expected = 0.5 * math.exp(-1) * params.PROVIDER_DIVERSITY_WEIGHT_SINGLE
    assert wc == pytest.approx(round(expected, 4), abs=1e-4)


def test_expired_signal_dropped():
    expired = _sig(freshness_ttl_seconds=3600, signed_at=NOW - timedelta(hours=2))
    fresh = _sig(raw_signal=0.4, source_provider_did="did:web:issuer-b.example")
    env = aggregate(
        subject_did="did:web:agent.example",
        subject_kind="agent",
        signals=[expired, fresh],
        now=NOW,
    )
    assert len(env["contributions"]) == 1


def test_all_expired_raises():
    expired = _sig(freshness_ttl_seconds=3600, signed_at=NOW - timedelta(hours=5))
    with pytest.raises(EnvelopeError):
        aggregate(
            subject_did="did:web:agent.example",
            subject_kind="agent",
            signals=[expired],
            now=NOW,
        )


# ---- §4 (3): conflict resolution ----


def test_conflicting_signals_marked_contested():
    # Same (claim_type, provider) diverging by > 0.30 → both contested.
    a = _sig(raw_signal=0.9, claim_type="authority")
    b = _sig(raw_signal=0.2, claim_type="authority")
    env = aggregate(
        subject_did="did:web:agent.example",
        subject_kind="agent",
        signals=[a, b],
        now=NOW,
    )
    assert all(c.get("contested_signal") for c in env["contributions"])


def test_non_conflicting_same_provider_not_contested():
    a = _sig(raw_signal=0.5, claim_type="authority")
    b = _sig(raw_signal=0.55, claim_type="authority")  # within threshold
    env = aggregate(
        subject_did="did:web:agent.example",
        subject_kind="agent",
        signals=[a, b],
        now=NOW,
    )
    assert not any(c.get("contested_signal") for c in env["contributions"])


def test_different_providers_never_conflict():
    a = _sig(raw_signal=0.9, claim_type="authority",
             source_provider_did="did:web:issuer-a.example")
    b = _sig(raw_signal=0.2, claim_type="authority",
             source_provider_did="did:web:issuer-b.example")
    env = aggregate(
        subject_did="did:web:agent.example",
        subject_kind="agent",
        signals=[a, b],
        now=NOW,
    )
    assert not any(c.get("contested_signal") for c in env["contributions"])


# ---- §4 (4): provider diversity vs in-house ----


def test_in_house_signal_not_diversity_discounted():
    # community signal has no provider DID → diversity multiplier must not apply.
    sig = _sig(
        source="community_signal",
        claim_type=None,
        source_provider_did=None,
        raw_signal=0.08,
        max_contribution=params.COMMUNITY_SIGNAL_CAP,
    )
    env = aggregate(
        subject_did="did:web:agent.example",
        subject_kind="agent",
        signals=[sig],
        now=NOW,
    )
    wc = env["contributions"][0]["weighted_contribution"]
    assert wc == pytest.approx(0.08, abs=1e-4)  # no 0.7 discount


def test_four_providers_get_full_weight():
    sigs = [
        _sig(raw_signal=0.5, claim_type="identity",
             source_provider_did=f"did:web:issuer-{i}.example")
        for i in range(4)
    ]
    env = aggregate(
        subject_did="did:web:agent.example",
        subject_kind="agent",
        signals=sigs,
        now=NOW,
    )
    # 4 distinct providers → diversity 1.0, so each = min(0.5,0.60)*1.0*1.0
    for c in env["contributions"]:
        assert c["weighted_contribution"] == pytest.approx(0.5, abs=1e-4)


# ---- negative feedback floor ----


def test_negative_feedback_floored_not_unbounded():
    neg = _sig(
        source="erc8004_reputation",
        claim_type=None,
        source_provider_did=None,
        raw_signal=-0.9,
        max_contribution=1.0,
    )
    env = aggregate(
        subject_did="did:web:agent.example",
        subject_kind="agent",
        signals=[neg],
        now=NOW,
    )
    # build_envelope floors the SUM at -0.20 then clamps to [0,1] → 0.0
    assert env["trust_score"] == 0.0


# ---- end-to-end sign/verify ----


def test_aggregate_then_sign_then_verify():
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    env = aggregate(
        subject_did="did:web:agent.example",
        subject_kind="agent",
        signals=[
            _sig(raw_signal=0.8, claim_type="identity"),
            _sig(raw_signal=0.6, claim_type="authority",
                 source_provider_did="did:web:issuer-b.example"),
        ],
        now=NOW,
    )
    signed = sign_envelope(env, priv)
    assert verify_envelope(signed, pub) is True
