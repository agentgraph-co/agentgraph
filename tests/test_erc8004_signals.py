"""Tests for the ERC-8004 → v2 RawSignal adapter scaffold (#110).

Pure mapping tests + the inert (unconfigured) SignalSource. The live on-chain
path is gated on the sync job and not exercised here.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

# The bridge package is imported top-level (not src.-prefixed) and is only on
# path in the app/prod env; add src/ so these unit tests can construct its models.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agentgraph_bridge_erc8004.models import NormalizedAttestation  # noqa: E402
from agentgraph_bridge_erc8004.reputation_registry import ReputationSummary  # noqa: E402
from src.trust.erc8004_signals import (
    Erc8004SignalSource,
    attestation_to_signal,
    reputation_summary_to_signal,
)

# Anchored to the real clock: NormalizedAttestation.is_admissible compares
# expires_at against wall-clock now(), so a frozen fixture date rots — the
# original datetime(2026, 6, 1) started failing the moment it "expired" Jun 2.
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _att(**kw) -> NormalizedAttestation:
    base = dict(
        source_urn="urn:erc8004:reputation:42",
        claim_type="authority",
        subject_did="did:web:agent.example",
        provider_did="did:web:issuer.example",
        payload={"attestation": {"confidence": 0.9}},
        signature_verified=True,
        registry_signature_verified=True,
        issued_at=NOW,
        expires_at=NOW + timedelta(days=1),
        freshness_ttl_remaining_seconds=86400,
    )
    base.update(kw)
    return NormalizedAttestation(**base)


def test_attestation_maps_to_signal():
    sig = attestation_to_signal(_att())
    assert sig is not None
    assert sig.source == "ctef_attestation"
    assert sig.raw_signal == pytest.approx(0.9)
    assert sig.claim_type == "authority"
    assert sig.source_provider_did == "did:web:issuer.example"


def test_inadmissible_attestation_dropped():
    assert attestation_to_signal(_att(signature_verified=False)) is None


def test_attestation_default_confidence_when_absent():
    sig = attestation_to_signal(_att(payload={}))
    assert sig is not None
    assert sig.raw_signal == 1.0


def test_reputation_summary_positive():
    # Mirrors real agent 1: summaryValue=51, count=6, decimals=0 -> 51/100 = 0.51.
    s = ReputationSummary(
        agent_id=42, feedback_count=6, aggregate_score=51,
        recent_indicator=0, distinct_clients=2, source_urn="urn:erc8004:reputation:42",
    )
    sig = reputation_summary_to_signal(s, now=NOW)
    assert sig is not None
    assert sig.source == "erc8004_reputation"
    assert sig.raw_signal == pytest.approx(0.51, abs=1e-4)


def test_reputation_summary_decimals_scale_the_value():
    # 0-100 score with sub-integer precision: 5100/10^2 = 51.0 -> 0.51
    base = dict(agent_id=1, feedback_count=4, distinct_clients=2,
                source_urn="urn:erc8004:reputation:1")
    s2 = reputation_summary_to_signal(
        ReputationSummary(aggregate_score=5100, recent_indicator=2, **base), now=NOW)
    s3 = reputation_summary_to_signal(
        ReputationSummary(aggregate_score=5100, recent_indicator=3, **base), now=NOW)
    assert s2.raw_signal == pytest.approx(0.51, abs=1e-4)   # 51.0/100
    assert s3.raw_signal == pytest.approx(0.051, abs=1e-4)  # 5.1/100


def test_reputation_summary_negative_allowed():
    # negative aggregate score (-80) pushes a trust signal down: -80/100 = -0.8
    s = ReputationSummary(
        agent_id=7, feedback_count=4, aggregate_score=-80,
        recent_indicator=0, distinct_clients=3, source_urn="urn:erc8004:reputation:7",
    )
    sig = reputation_summary_to_signal(s, now=NOW)
    assert sig is not None
    assert sig.raw_signal == pytest.approx(-0.8, abs=1e-4)


def test_reputation_summary_no_feedback_none():
    s = ReputationSummary(
        agent_id=1, feedback_count=0, aggregate_score=0,
        recent_indicator=0, distinct_clients=0, source_urn="urn:erc8004:reputation:1",
    )
    assert reputation_summary_to_signal(s, now=NOW) is None


@pytest.mark.asyncio
async def test_unconfigured_source_is_inert():
    src = Erc8004SignalSource(reputation_reader=None)
    assert await src.signals_for("did:web:agent.example") == []
