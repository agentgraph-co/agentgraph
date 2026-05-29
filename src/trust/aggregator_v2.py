"""Trust Score v2 aggregation engine (design §4).

Folds raw signals from every substrate source — CTEF attestations, ERC-8004
reputation, in-house security scans, third-party observers, community signals —
into the ``contributions`` list of a v2 score envelope, then hands off to
``envelope_v2.build_envelope`` (which owns the final floor + clamp).

The pipeline, per `docs/internal/trust-score-v2-design.md` §4:

    raw signals
       │  (1) per-claim_type cap        — bound each attestation's contribution
       │  (2) freshness decay           — exp half-life on attestation age
       │  (3) conflict resolution       — surface contested (claim_type, provider) pairs
       │  (4) provider-diversity weight  — discount single-source, reward corroboration
       ▼
    Contribution[]  ──►  build_envelope()  ──►  sign_envelope()

This module is PURE: it takes pre-fetched ``RawSignal`` objects and a clock,
and returns an unsigned envelope dict. It does NOT touch the DB, the chain, or
Redis. The live source adapters (ERC-8004 reader gated on #110, scan corpus
reader, community-signal reader off ``src/trust/score.py``) are wired in the
API layer (`src/api/trust_aggregate.py`, Jun 5-9 phase) and feed this engine.

All tunables live in `aggregation_params.py` — the single Decision-A surface.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from src.trust import aggregation_params as params
from src.trust.envelope_v2 import (
    CLAIM_TYPE_CAPS,
    VALID_CLAIM_TYPES,
    VALID_SOURCES,
    Contribution,
    EnvelopeError,
    build_envelope,
)


@dataclass(frozen=True)
class RawSignal:
    """A pre-fetched, source-agnostic input to aggregation.

    One per contributing piece of evidence (one attestation, one scan, one
    ERC-8004 reputation summary, one community-signal roll-up). The engine
    turns each admissible RawSignal into exactly one envelope ``Contribution``.

    ``raw_signal`` is the source's own 0-1 assessment (may be negative for
    ERC-8004 negative feedback). ``signed_at`` drives freshness decay;
    ``freshness_ttl_seconds`` is the hard expiry cutoff carried into the
    envelope. ``max_contribution`` overrides the default per-claim_type cap
    when a source has its own ceiling (e.g. scan, community) — when None and
    a ``claim_type`` is set, the §4 cap for that claim_type is used.
    """

    source: str
    raw_signal: float
    signed_at: datetime
    freshness_ttl_seconds: int
    claim_type: str | None = None
    source_provider_did: str | None = None
    source_attestation_hash: str | None = None
    evidence_type: str | None = None
    max_contribution: float | None = None
    metadata: dict | None = field(default=None)

    def __post_init__(self) -> None:
        if self.source not in VALID_SOURCES:
            raise EnvelopeError(f"invalid source: {self.source}")
        if self.claim_type is not None and self.claim_type not in VALID_CLAIM_TYPES:
            raise EnvelopeError(f"invalid claim_type: {self.claim_type}")


class SignalSource(Protocol):
    """Adapter interface for a live substrate source.

    Implemented in the API layer (Jun 5-9) by the ERC-8004 reader (#110),
    the scan-corpus reader, the third-party observer reader, and the
    community-signal reader. Each resolves a subject DID to zero or more
    ``RawSignal`` objects; the engine itself never knows where they came from.
    """

    async def signals_for(self, subject_did: str) -> list[RawSignal]:
        ...


# ---------------------------------------------------------------------------
# §4 primitives
# ---------------------------------------------------------------------------


def freshness_decay(age_seconds: float) -> float:
    """exp(-age / half_life) freshness multiplier, clamped to [0, 1].

    Age at or below zero (future-dated / just-signed) → 1.0. Older signals
    decay toward 0 with the configured half-life.
    """
    if age_seconds <= 0:
        return 1.0
    return math.exp(-age_seconds / params.FRESHNESS_HALF_LIFE_SECONDS)


def provider_diversity_weight(distinct_providers: int) -> float:
    """Global multiplier on provider-attributed signals by distinct-provider count.

    1 → 0.7 (single-source), 2-3 → 0.9, 4+ → 1.0. Zero providers → 1.0
    (nothing to discount; non-attestation signals are unaffected upstream).
    """
    if distinct_providers <= 0:
        return params.PROVIDER_DIVERSITY_WEIGHT_MANY
    if distinct_providers >= params.PROVIDER_DIVERSITY_MANY_THRESHOLD:
        return params.PROVIDER_DIVERSITY_WEIGHT_MANY
    if distinct_providers >= params.PROVIDER_DIVERSITY_FEW_THRESHOLD:
        return params.PROVIDER_DIVERSITY_WEIGHT_FEW
    return params.PROVIDER_DIVERSITY_WEIGHT_SINGLE


def _cap_for(sig: RawSignal) -> float:
    """The ceiling on this signal's contribution (before decay + diversity).

    Explicit ``max_contribution`` wins; else the §4 claim_type cap; else
    no cap (community / scan signals carry their own via max_contribution,
    so an uncapped, claim-less signal is bounded only by raw_signal itself).
    """
    if sig.max_contribution is not None:
        return sig.max_contribution
    if sig.claim_type is not None:
        return CLAIM_TYPE_CAPS.get(sig.claim_type, 0.0)
    return 1.0


def _is_expired(sig: RawSignal, now: datetime) -> bool:
    """True once the signal's own freshness TTL has elapsed (hard cutoff)."""
    age = (now - sig.signed_at).total_seconds()
    return age > sig.freshness_ttl_seconds


# ---------------------------------------------------------------------------
# §4 conflict pass
# ---------------------------------------------------------------------------


def _mark_conflicts(signals: list[RawSignal]) -> set[int]:
    """Return indices of signals that are part of a contested pair.

    Two signals conflict when they share (claim_type, source_provider_did) and
    their raw_signal values diverge by more than the §4 threshold. Conflicting
    signals are flagged ``contested_signal=True`` in the envelope and their
    retained weight is boosted to never silently drop the dissenting view.
    """
    contested: set[int] = set()
    groups: dict[tuple[str, str], list[int]] = {}
    for i, s in enumerate(signals):
        if s.claim_type is None or s.source_provider_did is None:
            continue
        groups.setdefault((s.claim_type, s.source_provider_did), []).append(i)

    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                ia, ib = idxs[a], idxs[b]
                if abs(signals[ia].raw_signal - signals[ib].raw_signal) > (
                    params.CONFLICT_DIVERGENCE_THRESHOLD
                ):
                    contested.add(ia)
                    contested.add(ib)
    return contested


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def aggregate(
    *,
    subject_did: str,
    subject_kind: str,
    signals: list[RawSignal],
    now: datetime | None = None,
    freshness_ttl_seconds: int = 3600,
    issuer: str | None = None,
) -> dict:
    """Aggregate raw signals into an UNSIGNED v2 score envelope.

    Pipeline (§4): drop expired → cap each contribution → apply freshness
    decay → mark + boost conflicts → apply global provider-diversity weight to
    attestation signals → build envelope (which sums, floors at -0.20, clamps
    to [0,1]). Caller signs the result with ``envelope_v2.sign_envelope``.

    Returns the unsigned envelope dict. Raises ``EnvelopeError`` if, after
    dropping expired signals, nothing admissible remains.
    """
    now = now or datetime.now(timezone.utc)

    live = [s for s in signals if not _is_expired(s, now)]
    if not live:
        raise EnvelopeError("no admissible (non-expired) signals for subject")

    contested = _mark_conflicts(live)

    # Distinct providers across attestation-style signals drives the global
    # diversity multiplier.
    distinct_providers = len({
        s.source_provider_did for s in live if s.source_provider_did is not None
    })
    diversity = provider_diversity_weight(distinct_providers)

    contributions: list[Contribution] = []
    for i, sig in enumerate(live):
        cap = _cap_for(sig)
        # (1) cap, preserving sign so negative ERC-8004 feedback can push down.
        capped = max(min(sig.raw_signal, cap), -cap)
        # (2) freshness decay on the magnitude.
        age = (now - sig.signed_at).total_seconds()
        weighted = capped * freshness_decay(age)
        # (4) provider-diversity discount applies only to provider-attributed
        # signals; in-house scan/community signals are not "corroboration".
        if sig.source_provider_did is not None:
            weighted *= diversity

        is_contested = i in contested
        # (3) conflict: never silently shrink a contested signal below its
        # retention floor relative to the cap it was bounded by.
        if is_contested:
            floor = params.CONFLICT_RETENTION_FACTOR * cap
            weighted = max(weighted, floor) if weighted >= 0 else min(weighted, -floor)

        contributions.append(
            Contribution(
                source=sig.source,
                raw_signal=sig.raw_signal,
                weighted_contribution=round(weighted, 4),
                freshness_ttl_seconds=sig.freshness_ttl_seconds,
                source_attestation_hash=sig.source_attestation_hash,
                claim_type=sig.claim_type,
                evidence_type=sig.evidence_type,
                source_provider_did=sig.source_provider_did,
                contested_signal=is_contested,
                metadata=sig.metadata,
            )
        )

    build_kwargs = {
        "subject_did": subject_did,
        "subject_kind": subject_kind,
        "contributions": contributions,
        "computed_at": now,
        "freshness_ttl_seconds": freshness_ttl_seconds,
    }
    if issuer is not None:
        build_kwargs["issuer"] = issuer
    return build_envelope(**build_kwargs)


__all__ = [
    "RawSignal",
    "SignalSource",
    "aggregate",
    "freshness_decay",
    "provider_diversity_weight",
]
