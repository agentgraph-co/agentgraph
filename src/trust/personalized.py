"""Personalized trust score computation.

Allows users to customize how they weight trust components
when viewing other entities' trust scores. This is a personal
preference — it doesn't change the canonical trust score, but
adjusts how it's displayed to the user.
"""
from __future__ import annotations

DEFAULT_WEIGHTS = {
    "verification": 0.35,
    "age": 0.10,
    "activity": 0.20,
    "reputation": 0.15,
    "community": 0.20,
}


def compute_personalized_score(
    components: dict[str, float],
    custom_weights: dict[str, float] | None = None,
) -> float:
    """Compute trust score using custom weights.

    Args:
        components: Trust score components (verification, age, activity,
            reputation, community).
        custom_weights: Custom weights for each component. If None, uses
            defaults.

    Returns:
        Weighted trust score (0.0-1.0)
    """
    weights = custom_weights or DEFAULT_WEIGHTS
    score = sum(
        weights.get(k, 0.0) * components.get(k, 0.0)
        for k in DEFAULT_WEIGHTS
    )
    return min(max(score, 0.0), 1.0)
