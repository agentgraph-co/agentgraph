"""Map existing trust-score inputs into v2 ``RawSignal`` objects.

P1 bridge: the v1 composite (``src/trust/score.py``) already blends scan,
external/ERC-8004, and community signals into a ``components`` dict. This
module re-expresses those components as v2 ``RawSignal`` objects so the
aggregation engine can wrap them in a signed, methodology-transparent v2
envelope WITHOUT re-deriving the underlying score.

Because v1 components are already individually weighted (they sum to the
composite), each maps to a RawSignal with ``max_contribution=1.0`` (no further
cap), no ``claim_type`` and no ``source_provider_did`` (so the engine's
diversity discount and conflict pass are inert), and ``signed_at=now`` (decay
≈ 1.0). The v2 ``trust_score`` therefore equals the v1 composite — a faithful
re-shaping, not a re-scoring.

When the per-attestation readers land (ERC-8004 sync #110, CTEF attestation
reader, Dominion Observatory), they emit RawSignals with real
``source_provider_did`` / ``claim_type`` / ``signed_at`` and the engine's full
§4 machinery (caps, diversity, decay, conflict) engages on those. This module
is the in-house-data path; those are the substrate-data paths. Both feed one
engine.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.trust.aggregator_v2 import RawSignal

# v1 component name → v2 envelope source. Components come from the WEIGHTS in
# src/trust/score.py: verification, age, activity, reputation, community,
# external, scan. Anything unmapped falls back to community_signal.
_COMPONENT_SOURCE = {
    "scan": "scan_corpus",
    "external": "erc8004_reputation",
    "verification": "self_attested",
}
_DEFAULT_SOURCE = "community_signal"

# Components are already-weighted contributions; don't re-cap them.
_PASS_THROUGH_CAP = 1.0
# In-house signals get the standard envelope TTL.
_DEFAULT_TTL_SECONDS = 3600


def components_to_signals(
    components: dict | None,
    *,
    now: datetime | None = None,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> list[RawSignal]:
    """Convert a v1 ``TrustScore.components`` dict into v2 RawSignals.

    Zero / missing / non-numeric component values are skipped (they add
    nothing and would clutter the methodology breakdown). The v1 component
    name is preserved in each signal's metadata for traceability.
    """
    now = now or datetime.now(timezone.utc)
    signals: list[RawSignal] = []
    for name, value in (components or {}).items():
        if not isinstance(value, (int, float)):
            continue
        if value == 0:
            continue
        source = _COMPONENT_SOURCE.get(name, _DEFAULT_SOURCE)
        signals.append(
            RawSignal(
                source=source,
                raw_signal=float(value),
                signed_at=now,
                freshness_ttl_seconds=ttl_seconds,
                max_contribution=_PASS_THROUGH_CAP,
                metadata={"v1_component": name},
            )
        )
    return signals


__all__ = ["components_to_signals"]
