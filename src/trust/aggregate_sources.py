"""Map the existing v1 composite into v2 envelope ``Contribution`` objects.

P1 bridge: the v1 composite (``src/trust/score.py``) blends seven raw
per-dimension signals into a single score via fixed weights. ``compute_trust_score``
stores the **raw** per-dimension values in ``TrustScore.components`` and the
weighted composite in ``TrustScore.score``. This module re-expresses that as v2
envelope contributions so the score wraps into a signed, methodology-transparent
v2 envelope whose ``trust_score`` equals the v1 composite.

Crucially, each contribution's ``weighted_contribution`` is ``weight × raw``
(the dimension's actual share of the composite), while ``raw_signal`` carries
the dimension's raw 0-1 value — so the breakdown reads honestly ("verification
raw 0.90 → +0.32 at 35% weight") and the contributions sum to the composite.

The weights mirror ``score.py`` exactly, including the human/agent adjustments
(humans get +0.10 verification & external, no scan weight) and the per-entity
``framework_trust_modifier`` that scales the whole score. When the per-attestation
substrate readers land (ERC-8004 #110, CTEF, observer), they feed the §4
``aggregator_v2.aggregate`` engine as ``RawSignal`` objects and their resulting
contributions are merged with these — this is the in-house path, that is the
substrate path, both produce ``Contribution`` objects for one envelope.
"""
from __future__ import annotations

from src.trust.envelope_v2 import Contribution
from src.trust.score import (
    ACTIVITY_WEIGHT,
    AGE_WEIGHT,
    COMMUNITY_WEIGHT,
    EXTERNAL_WEIGHT,
    REPUTATION_WEIGHT,
    SCAN_WEIGHT,
    VERIFICATION_WEIGHT,
)

# Human bonus applied to verification & external weights (score.py §645-647).
_HUMAN_WEIGHT_BONUS = 0.10

# component key → (v2 source, base weight, gets human bonus, zeroed for humans).
# Keys MUST match the dict built in score.py:664-672.
_COMPONENT_META = {
    "verification": ("self_attested", VERIFICATION_WEIGHT, True, False),
    "age": ("community_signal", AGE_WEIGHT, False, False),
    "activity": ("community_signal", ACTIVITY_WEIGHT, False, False),
    "reputation": ("community_signal", REPUTATION_WEIGHT, False, False),
    "community": ("community_signal", COMMUNITY_WEIGHT, False, False),
    "external_reputation": ("erc8004_reputation", EXTERNAL_WEIGHT, True, False),
    "scan_score": ("scan_corpus", SCAN_WEIGHT, False, True),
}

_DEFAULT_TTL_SECONDS = 3600


def components_to_contributions(
    components: dict | None,
    *,
    is_human: bool = False,
    framework_modifier: float | None = None,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> list[Contribution]:
    """Convert a v1 ``TrustScore.components`` dict into v2 envelope Contributions.

    ``weighted_contribution`` = effective_weight × raw × framework_modifier,
    matching ``score.py``'s composite so the contributions sum to the v1 score.
    Zero-weight or zero-raw dimensions are dropped (they'd add nothing and clutter
    the breakdown). Distributing ``framework_modifier`` across contributions is
    equivalent to score.py applying it to the total (both scale the sum equally).
    """
    modifier = framework_modifier if framework_modifier else 1.0
    out: list[Contribution] = []
    for key, (source, base_w, human_bonus, zero_for_human) in _COMPONENT_META.items():
        raw = (components or {}).get(key)
        if not isinstance(raw, (int, float)) or raw == 0:
            continue
        weight = base_w + (_HUMAN_WEIGHT_BONUS if (human_bonus and is_human) else 0.0)
        if zero_for_human and is_human:
            weight = 0.0
        weighted = weight * float(raw) * modifier
        if weighted == 0:
            continue
        out.append(
            Contribution(
                source=source,
                raw_signal=float(raw),
                weighted_contribution=round(weighted, 4),
                freshness_ttl_seconds=ttl_seconds,
                metadata={"v1_component": key, "v1_weight": round(weight, 4)},
            )
        )
    return out


__all__ = ["components_to_contributions"]
