"""Trust Score v2 aggregation parameters — the single Decision-A review surface.

Every tunable in the §4 aggregation algorithm lives here so the values can be
reviewed/approved in one place (design doc `docs/internal/trust-score-v2-design.md`
§4, "Pending Kenne decision A"). `aggregator_v2.py` imports from this module and
nothing else hard-codes these numbers.

Two of the §4 constants — the per-claim_type caps and the negative-feedback floor
— are already published in the merged Trust Score Envelope v2.0 spec
(`envelope_v2.py`, PR #26). We RE-EXPORT them here rather than redefine, so the
aggregator's view of the caps can never drift from the signed-envelope spec.

The remaining constants (provider-diversity weights, freshness half-life, conflict
thresholds, community cap) are NEW for the aggregator and have no published home
yet — these are the values Decision A signs off on. Each carries the design-doc
provenance inline.
"""
from __future__ import annotations

# Re-exported from the published v2 envelope spec (PR #26) — DO NOT redefine.
# These are the per-claim_type contribution caps and the negative-feedback floor.
from src.trust.envelope_v2 import (  # noqa: F401  (re-export is intentional)
    CLAIM_TYPE_CAPS,
    NEGATIVE_FEEDBACK_FLOOR,
)

# ---------------------------------------------------------------------------
# Provider-diversity weighting (design §4, NEW for v2 — pending Decision A)
#
# Penalizes single-source dependency, rewards independent corroboration. The
# weight is a multiplier applied to provider-attributed (attestation) signals
# based on how many DISTINCT source_provider_did values contribute.
#
#   1 distinct provider   → 0.7   (single-source: discounted)
#   2-3 distinct providers → 0.9
#   4+ distinct providers  → 1.0   (well-corroborated: full weight)
# ---------------------------------------------------------------------------
PROVIDER_DIVERSITY_WEIGHT_SINGLE = 0.7
PROVIDER_DIVERSITY_WEIGHT_FEW = 0.9      # 2-3 distinct providers
PROVIDER_DIVERSITY_WEIGHT_MANY = 1.0     # 4+ distinct providers
PROVIDER_DIVERSITY_FEW_THRESHOLD = 2     # >= this many → "few" tier
PROVIDER_DIVERSITY_MANY_THRESHOLD = 4    # >= this many → "many" tier

# ---------------------------------------------------------------------------
# Freshness decay (design §4, NEW for v2 — pending Decision A)
#
#   freshness_decay(age) = exp(-age_seconds / FRESHNESS_HALF_LIFE_SECONDS)
#
# Applied as a multiplier on each contribution's weight, using the age of the
# underlying attestation (now - signed_at). Default 1-day half-life. A signal
# is "expired" (zero contribution) once its own freshness_ttl_seconds elapses;
# decay shapes the curve up to that hard cutoff.
# ---------------------------------------------------------------------------
FRESHNESS_HALF_LIFE_SECONDS = 86_400  # 1 day

# ---------------------------------------------------------------------------
# Conflict resolution (design §4, NEW for v2 — pending Decision A)
#
# When two attestations with the same (claim_type, source_provider_did)
# disagree by more than CONFLICT_DIVERGENCE_THRESHOLD on raw_signal, the pair
# is surfaced as a contested_signal in the methodology and the retained
# contribution is:
#       max(weighted_contribution, CONFLICT_RETENTION_FACTOR * conflicting)
# Never silent averaging, never silent dropping — forces visibility.
# ---------------------------------------------------------------------------
CONFLICT_DIVERGENCE_THRESHOLD = 0.30
CONFLICT_RETENTION_FACTOR = 0.50

# ---------------------------------------------------------------------------
# Community-signal cap (design §4 — matches existing in-house weighting)
#
# In-house votes + follows + peer reviews contribute at most this much of the
# final score. Mirrors the intent of the disabled COMMUNITY_WEIGHT slot in
# src/trust/score.py; kept explicit here so the aggregator's community ceiling
# is reviewed alongside the rest of §4.
# ---------------------------------------------------------------------------
COMMUNITY_SIGNAL_CAP = 0.10

__all__ = [
    "CLAIM_TYPE_CAPS",
    "NEGATIVE_FEEDBACK_FLOOR",
    "PROVIDER_DIVERSITY_WEIGHT_SINGLE",
    "PROVIDER_DIVERSITY_WEIGHT_FEW",
    "PROVIDER_DIVERSITY_WEIGHT_MANY",
    "PROVIDER_DIVERSITY_FEW_THRESHOLD",
    "PROVIDER_DIVERSITY_MANY_THRESHOLD",
    "FRESHNESS_HALF_LIFE_SECONDS",
    "CONFLICT_DIVERGENCE_THRESHOLD",
    "CONFLICT_RETENTION_FACTOR",
    "COMMUNITY_SIGNAL_CAP",
]
