"""ERC-8004 → Trust Score v2 ``RawSignal`` adapter (#110 scaffold).

Bridges the on-chain ERC-8004 read layer (``src/agentgraph_bridge_erc8004``)
into the §4 aggregation engine: a ``SignalSource`` that resolves a subject DID
to ``RawSignal`` objects the engine can aggregate alongside scan / community /
observer signals.

STATUS: scaffold. The pure mapping functions (attestation → RawSignal, summary
→ RawSignal) are complete and unit-tested. The live on-chain fetch is gated on
the #110 sync job — ``Erc8004SignalSource.signals_for`` returns ``[]`` until
``ETH_RPC_URL`` + the registry contract addresses are configured, so wiring it
into the endpoint is safe before the sync ships. Monday's #110 work is: provide
env config + apply the (separate) erc8004 cache migration → signals flow.

NORMALIZATION (resolved against REAL mainnet data, 2026-06-01): the v2
ReputationRegistry `getSummary(...)` returns
`(count uint64, summaryValue int128, summaryValueDecimals uint8)`. Read live,
agent 1 = `summaryValue=51, count=6, decimals=0`; agents 2/3 = 55/58 — i.e.
`summaryValue` is an AGGREGATE SCORE on a 0-100 scale (NOT a sum to divide by
count), with `decimals` giving sub-integer precision. So:
`raw_signal = clamp((summaryValue / 10**decimals) / 100, -1, 1)` → 0.51/0.55/0.58
for agents 1/2/3. Negative values push a score down. NOTE: the reader stores
`summaryValueDecimals` in `ReputationSummary.recent_indicator` (positional
mapping; field name predates the v2 ABI — see reputation_registry.py).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.trust.aggregator_v2 import RawSignal

if TYPE_CHECKING:  # the bridge package is only on path in app/prod, not bare tests
    from agentgraph_bridge_erc8004.models import NormalizedAttestation
    from agentgraph_bridge_erc8004.reputation_registry import ReputationSummary

logger = logging.getLogger(__name__)


def attestation_to_signal(att: NormalizedAttestation) -> RawSignal | None:
    """Map one normalized CTEF/ERC-8004 attestation to a v2 RawSignal.

    Returns None for inadmissible attestations (caller filters). raw_signal is
    the attestation's confidence (CTEF ``attestation.confidence``), defaulting
    to 1.0 for an admissible attestation that omits it. claim_type and provider
    flow through so the §4 engine's caps + diversity + conflict pass apply.
    """
    if not att.is_admissible:
        return None
    confidence = 1.0
    payload = att.payload or {}
    inner = payload.get("attestation") if isinstance(payload, dict) else None
    if isinstance(inner, dict) and isinstance(inner.get("confidence"), (int, float)):
        confidence = float(inner["confidence"])
    ttl = att.freshness_ttl_remaining_seconds
    return RawSignal(
        source="ctef_attestation",
        raw_signal=max(0.0, min(1.0, confidence)),
        signed_at=att.issued_at,
        freshness_ttl_seconds=int(ttl) if ttl is not None else 86_400,
        claim_type=att.claim_type if att.claim_type in (
            "identity", "authority", "continuity", "transport"
        ) else None,
        source_provider_did=att.provider_did,
        source_attestation_hash=None,
        metadata={"source_urn": att.source_urn},
    )


def reputation_summary_to_signal(
    summary: ReputationSummary, *, now: datetime | None = None
) -> RawSignal | None:
    """Map a Reputation Registry summary to a single v2 RawSignal.

    Negative aggregate (bad on-chain reputation) maps to a negative raw_signal,
    which the §4 floor (−0.20) lets push a score down rather than be masked by
    in-house signals. Returns None when there's no feedback to represent.
    """
    if summary.feedback_count <= 0:
        return None
    now = now or datetime.now(timezone.utc)
    # Validated against real mainnet data (2026-06-01): summaryValue is an
    # AGGREGATE SCORE on a 0-100 scale (e.g. agent 1 = 51 over 6 feedbacks, NOT a
    # sum), with summaryValueDecimals (stored in recent_indicator) giving
    # sub-integer precision. Normalize 0-100 → 0-1; do NOT divide by count.
    decimals = max(0, int(summary.recent_indicator))
    score_0_100 = summary.aggregate_score / (10 ** decimals)
    raw = max(-1.0, min(1.0, score_0_100 / 100.0))
    return RawSignal(
        source="erc8004_reputation",
        raw_signal=round(raw, 4),
        signed_at=now,  # on-chain summary has no per-entry timestamp; treat as fresh
        freshness_ttl_seconds=3600,
        metadata={
            "agent_id": summary.agent_id,
            "feedback_count": summary.feedback_count,
            "distinct_clients": summary.distinct_clients,
            "source_urn": summary.source_urn,
        },
    )


class Erc8004SignalSource:
    """SignalSource adapter for ERC-8004 on-chain reputation (#110 scaffold).

    Resolves a subject DID to ERC-8004-derived RawSignals. Until the sync job
    + env config land, ``signals_for`` returns ``[]`` (logged), so the engine
    simply aggregates without on-chain input — safe to wire in now.
    """

    def __init__(self, reputation_reader=None) -> None:
        self._reader = reputation_reader

    @classmethod
    def from_env(cls) -> Erc8004SignalSource:
        """Build from env (ETH_RPC_URL + contract addresses), else inert."""
        try:
            from agentgraph_bridge_erc8004.reputation_registry import (
                make_reputation_reader_from_env,
            )

            return cls(reputation_reader=make_reputation_reader_from_env())
        except Exception:
            logger.debug("ERC-8004 reader not configured; signals inert", exc_info=True)
            return cls(reputation_reader=None)

    async def signals_for(self, subject_did: str) -> list[RawSignal]:
        if self._reader is None:
            return []
        # TODO(#110): resolve subject_did → agent_id (IdentityRegistry), call
        # reader.get_summary(agent_id), normalize, and read normalized
        # attestations. Gated on the sync job; left explicit so wiring is a
        # drop-in, not a rewrite.
        logger.debug("ERC-8004 signals_for not yet live (sync job pending)")
        return []


__all__ = [
    "attestation_to_signal",
    "reputation_summary_to_signal",
    "Erc8004SignalSource",
]
