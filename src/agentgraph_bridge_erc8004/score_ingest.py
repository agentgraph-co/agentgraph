"""Map normalized ERC-8004 attestations to a 0-1 external-reputation contribution.

Folds into the existing `_source_reputation_score()` slot in `src/trust/score.py`
(EXTERNAL_WEIGHT = 0.35 of the composite). When ERC-8004 attestations are
present for an entity, this module produces a score that the trust recompute
job blends with the existing community-signal score (max-of-the-two).

Scoring philosophy — load-bearing decisions:

1. **Per-claim_type weighting.** Identity attestations are foundational
   (cryptographic proof of who); authority + continuity attestations are
   incremental (proof of permission + observed behavior). Identity is
   capped at 0.6 contribution alone; authority/continuity add up to 0.4
   on top. A bot with only identity attestations caps at 0.6; a bot with
   identity + authority + continuity can reach 1.0.

2. **Provider diversity matters.** Three attestations from the same
   provider DID is worth less than three attestations from three
   different providers. Distinct-provider count is the inner cap; raw
   attestation count beyond that has diminishing returns (log scale).

3. **Freshness gate.** Expired attestations do not contribute. Period.
   This is enforced upstream in `NormalizedAttestation.is_admissible`,
   but `score()` re-checks defensively.

4. **No claim_subtype semantics here.** Subtypes (e.g. `tier_upgrade`)
   may inform the consuming app's policy decision, but they do not
   affect the substrate-level external-reputation contribution.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Iterable

from agentgraph_bridge_erc8004.models import NormalizedAttestation

# Score contributions per claim_type, capped at the per-type maximum.
# These cap at additive 1.0 max when all three are present.
_IDENTITY_CAP = 0.60
_AUTHORITY_CAP = 0.25
_CONTINUITY_CAP = 0.15
# Transport claims are routing-level not trust-level — no score contribution.
_TRANSPORT_CAP = 0.0


def _attestation_strength(
    count: int, distinct_providers: int,
) -> float:
    """Map (attestation count, distinct provider count) → 0-1 strength.

    Provider diversity dominates: 3 attestations from 3 providers > 10
    attestations from 1 provider. Beyond 3 distinct providers the curve
    plateaus.

    >>> _attestation_strength(0, 0)
    0.0
    >>> _attestation_strength(1, 1)  # 1 attestation from 1 provider
    0.5
    >>> _attestation_strength(3, 3)  # 3 attestations from 3 providers
    1.0
    >>> _attestation_strength(10, 1) > _attestation_strength(1, 1)  # more, same provider
    True
    >>> _attestation_strength(10, 1) < _attestation_strength(3, 3)  # but less than diverse
    True
    """
    if count <= 0:
        return 0.0
    # Diversity component: 0.5 floor at 1 provider, scales to 1.0 at 3+
    diversity = min(0.5 + (distinct_providers - 1) * 0.25, 1.0)
    # Count component: log-scaled bonus, max +0.1 at 10 attestations
    count_bonus = min(math.log10(count + 1) / 10.0, 0.1) if count > 1 else 0.0
    return min(diversity + count_bonus, 1.0)


def score(attestations: Iterable[NormalizedAttestation]) -> float:
    """Compute the ERC-8004 external-reputation contribution.

    Returns a value in [0.0, 1.0] suitable to pass into the
    `external_reputation` slot of the composite trust score.

    Empty input → 0.0 (no contribution, behavior unchanged for entities
    with no ERC-8004 attestations).

    Only admissible attestations (both signature layers verified,
    not expired) contribute. Non-admissible attestations are silently
    filtered; they're inspected via observability layers elsewhere.
    """
    admissible = [a for a in attestations if a.is_admissible]
    if not admissible:
        return 0.0

    by_type: dict[str, list[NormalizedAttestation]] = {
        "identity": [],
        "authority": [],
        "continuity": [],
        "transport": [],
    }
    for att in admissible:
        if att.claim_type in by_type:
            by_type[att.claim_type].append(att)

    contribution = 0.0
    for claim_type, cap in (
        ("identity", _IDENTITY_CAP),
        ("authority", _AUTHORITY_CAP),
        ("continuity", _CONTINUITY_CAP),
        ("transport", _TRANSPORT_CAP),
    ):
        if cap == 0.0:
            continue
        atts = by_type[claim_type]
        if not atts:
            continue
        count = len(atts)
        distinct = len(set(a.provider_did for a in atts))
        strength = _attestation_strength(count, distinct)
        contribution += cap * strength

    return round(min(contribution, 1.0), 4)


def blend_with_community_signals(
    erc8004_score: float, community_score: float,
) -> float:
    """Combine the ERC-8004 score with the existing community-signal score.

    Strategy: max-of-the-two. The two scores measure overlapping but
    distinct things; taking the max means an entity with strong on-chain
    attestations doesn't penalize one with strong GitHub signals (and
    vice versa). When both are present, the higher of the two dominates.

    This is intentionally NOT additive — additive blending would let an
    entity stack on-chain + GitHub signals to dominate the external
    slot, violating the per-signal weight isolation invariant in
    src/trust/score.py.
    """
    return round(max(erc8004_score, community_score), 4)


def score_breakdown(attestations: Iterable[NormalizedAttestation]) -> dict:
    """Diagnostic breakdown of the score components for observability.

    Returns a dict suitable for logging or surfacing in profile pages:
        {
          "total": 0.65,
          "by_claim_type": {
            "identity": {"count": 3, "distinct_providers": 2, "contribution": 0.5},
            "authority": {"count": 1, "distinct_providers": 1, "contribution": 0.125},
            ...
          },
          "non_admissible_filtered": 2  # how many entries we dropped
        }

    Does not include any signature material — diagnostic only, safe to
    surface in user-visible profile pages.
    """
    all_atts = list(attestations)
    admissible = [a for a in all_atts if a.is_admissible]

    breakdown: dict = {
        "total": score(admissible),
        "by_claim_type": {},
        "non_admissible_filtered": len(all_atts) - len(admissible),
    }

    type_counts = Counter(a.claim_type for a in admissible)
    for claim_type in ("identity", "authority", "continuity", "transport"):
        atts = [a for a in admissible if a.claim_type == claim_type]
        if not atts:
            continue
        count = len(atts)
        distinct = len(set(a.provider_did for a in atts))
        cap = {
            "identity": _IDENTITY_CAP,
            "authority": _AUTHORITY_CAP,
            "continuity": _CONTINUITY_CAP,
            "transport": _TRANSPORT_CAP,
        }[claim_type]
        contribution = round(cap * _attestation_strength(count, distinct), 4)
        breakdown["by_claim_type"][claim_type] = {
            "count": count,
            "distinct_providers": distinct,
            "contribution": contribution,
        }

    return breakdown


__all__ = [
    "blend_with_community_signals",
    "score",
    "score_breakdown",
]
