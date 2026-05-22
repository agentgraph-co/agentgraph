"""Tests for ERC-8004 score ingestion logic.

Pure-Python scoring math, no I/O. Uses fixture `NormalizedAttestation`
instances with `signature_verified=True` and far-future expiry to
isolate the scoring math from the upstream verification.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agentgraph_bridge_erc8004.models import NormalizedAttestation
from agentgraph_bridge_erc8004.score_ingest import (
    blend_with_community_signals,
    score,
    score_breakdown,
)


_FUTURE = datetime.now(timezone.utc) + timedelta(days=365)
_PAST = datetime.now(timezone.utc) - timedelta(days=1)


def _att(
    claim_type: str,
    provider_did: str,
    *,
    expires_at=_FUTURE,
    sig_verified: bool = True,
    reg_verified: bool = True,
) -> NormalizedAttestation:
    return NormalizedAttestation(
        source_urn=f"urn:erc8004:identity:{hash(provider_did) % 1000}",
        claim_type=claim_type,
        subject_did="did:web:agent.example.com",
        provider_did=provider_did,
        payload={},
        signature_verified=sig_verified,
        registry_signature_verified=reg_verified,
        issued_at=datetime(2026, 5, 22, tzinfo=timezone.utc),
        expires_at=expires_at,
    )


# ────────────────────────────────────────────────────────────────────
# score() — base behavior
# ────────────────────────────────────────────────────────────────────


class TestScoreBase:
    def test_no_attestations_returns_zero(self):
        assert score([]) == 0.0

    def test_only_inadmissible_returns_zero(self):
        atts = [_att("identity", "did:web:x.com", sig_verified=False)]
        assert score(atts) == 0.0

    def test_only_expired_returns_zero(self):
        atts = [_att("identity", "did:web:x.com", expires_at=_PAST)]
        assert score(atts) == 0.0


# ────────────────────────────────────────────────────────────────────
# score() — per-claim_type caps
# ────────────────────────────────────────────────────────────────────


class TestClaimTypeCaps:
    def test_identity_alone_caps_at_0_6(self):
        # 1 identity from 1 provider = 0.5 strength × 0.6 cap = 0.3
        atts = [_att("identity", "did:web:x.com")]
        assert score(atts) == 0.3

        # 3 identity from 3 providers = 1.0 strength × 0.6 cap = 0.6
        atts = [
            _att("identity", "did:web:a.com"),
            _att("identity", "did:web:b.com"),
            _att("identity", "did:web:c.com"),
        ]
        assert score(atts) == 0.6

    def test_authority_alone_caps_at_0_25(self):
        atts = [
            _att("authority", "did:web:a.com"),
            _att("authority", "did:web:b.com"),
            _att("authority", "did:web:c.com"),
        ]
        assert score(atts) == 0.25

    def test_continuity_alone_caps_at_0_15(self):
        atts = [
            _att("continuity", "did:web:a.com"),
            _att("continuity", "did:web:b.com"),
            _att("continuity", "did:web:c.com"),
        ]
        assert score(atts) == 0.15

    def test_transport_does_not_contribute(self):
        atts = [
            _att("transport", "did:web:a.com"),
            _att("transport", "did:web:b.com"),
            _att("transport", "did:web:c.com"),
        ]
        assert score(atts) == 0.0

    def test_all_three_can_reach_one(self):
        atts = []
        for ct in ("identity", "authority", "continuity"):
            for p in ("a.com", "b.com", "c.com"):
                atts.append(_att(ct, f"did:web:{p}"))
        assert score(atts) == 1.0


# ────────────────────────────────────────────────────────────────────
# score() — provider diversity matters
# ────────────────────────────────────────────────────────────────────


class TestProviderDiversity:
    def test_diversity_dominates_count(self):
        # 10 attestations from 1 provider vs 3 from 3
        many_same = [_att("identity", "did:web:x.com") for _ in range(10)]
        few_diverse = [
            _att("identity", "did:web:a.com"),
            _att("identity", "did:web:b.com"),
            _att("identity", "did:web:c.com"),
        ]
        assert score(few_diverse) > score(many_same)

    def test_count_provides_modest_bonus(self):
        # 1 attestation from 1 provider vs 10 from 1
        one = [_att("identity", "did:web:x.com")]
        ten = [_att("identity", "did:web:x.com") for _ in range(10)]
        # Modest bonus from count, but doesn't double the score
        assert score(ten) > score(one)
        assert score(ten) < score(one) * 1.5


# ────────────────────────────────────────────────────────────────────
# Inadmissible filtering
# ────────────────────────────────────────────────────────────────────


class TestInadmissibleFiltering:
    def test_mixed_admissible_and_not(self):
        atts = [
            _att("identity", "did:web:a.com"),  # admissible
            _att("identity", "did:web:b.com", sig_verified=False),  # filtered
            _att("identity", "did:web:c.com", expires_at=_PAST),  # filtered
        ]
        # Only 1 admissible → 1 provider → 0.5 × 0.6 = 0.3
        assert score(atts) == 0.3


# ────────────────────────────────────────────────────────────────────
# blend_with_community_signals — max strategy
# ────────────────────────────────────────────────────────────────────


class TestBlendWithCommunity:
    def test_max_strategy(self):
        assert blend_with_community_signals(0.6, 0.4) == 0.6
        assert blend_with_community_signals(0.3, 0.5) == 0.5
        assert blend_with_community_signals(0.7, 0.7) == 0.7

    def test_zero_erc_returns_community(self):
        assert blend_with_community_signals(0.0, 0.45) == 0.45

    def test_zero_community_returns_erc(self):
        assert blend_with_community_signals(0.65, 0.0) == 0.65

    def test_both_zero(self):
        assert blend_with_community_signals(0.0, 0.0) == 0.0


# ────────────────────────────────────────────────────────────────────
# score_breakdown — diagnostics
# ────────────────────────────────────────────────────────────────────


class TestScoreBreakdown:
    def test_includes_per_type_breakdown(self):
        atts = [
            _att("identity", "did:web:a.com"),
            _att("identity", "did:web:b.com"),
            _att("authority", "did:web:a.com"),
        ]
        bd = score_breakdown(atts)
        assert bd["total"] == score(atts)
        assert bd["by_claim_type"]["identity"]["count"] == 2
        assert bd["by_claim_type"]["identity"]["distinct_providers"] == 2
        assert bd["by_claim_type"]["authority"]["count"] == 1
        assert "continuity" not in bd["by_claim_type"]  # no continuity atts
        assert bd["non_admissible_filtered"] == 0

    def test_counts_non_admissible(self):
        atts = [
            _att("identity", "did:web:a.com"),
            _att("identity", "did:web:b.com", expires_at=_PAST),
            _att("identity", "did:web:c.com", sig_verified=False),
        ]
        bd = score_breakdown(atts)
        assert bd["non_admissible_filtered"] == 2
