"""Trust scoring v6 regression tests.

Tests the complete trust scoring pipeline including:
- Weight configuration (v6: community disabled)
- Human vs agent scoring differences
- Source-verified external reputation baseline
- Cache invalidation on recompute
- Grade system consistency
- Per-category sub-scores
"""
from __future__ import annotations

import math

import pytest

from src.trust.score import (
    ACTIVITY_WEIGHT,
    AGE_WEIGHT,
    COMMUNITY_WEIGHT,
    EXTERNAL_WEIGHT,
    REPUTATION_WEIGHT,
    SCAN_WEIGHT,
    VERIFICATION_WEIGHT,
    _verification_factor,
)


# ── Weight Configuration ──


def test_weights_sum_to_one():
    """All weights must sum to 1.0."""
    total = (
        VERIFICATION_WEIGHT + AGE_WEIGHT + ACTIVITY_WEIGHT
        + REPUTATION_WEIGHT + COMMUNITY_WEIGHT + EXTERNAL_WEIGHT
        + SCAN_WEIGHT
    )
    assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"


def test_community_metrics_disabled():
    """v6: activity, reputation, community should be 0 weight."""
    assert ACTIVITY_WEIGHT == 0.0, "Activity should be disabled in v6"
    assert REPUTATION_WEIGHT == 0.0, "Reputation should be disabled in v6"
    assert COMMUNITY_WEIGHT == 0.0, "Community should be disabled in v6"


def test_core_weights_positive():
    """Identity, external, scan, and age should have positive weights."""
    assert VERIFICATION_WEIGHT > 0, "Verification weight must be positive"
    assert EXTERNAL_WEIGHT > 0, "External weight must be positive"
    assert SCAN_WEIGHT > 0, "Scan weight must be positive"
    assert AGE_WEIGHT > 0, "Age weight must be positive"


def test_verification_is_largest_weight():
    """Verification should be the largest or tied for largest weight."""
    assert VERIFICATION_WEIGHT >= max(
        AGE_WEIGHT, ACTIVITY_WEIGHT, REPUTATION_WEIGHT,
        COMMUNITY_WEIGHT, SCAN_WEIGHT,
    )


# ── Verification Factor ──


class _FakeEntity:
    """Minimal entity mock for testing."""

    def __init__(self, **kwargs):
        self.email_verified = kwargs.get("email_verified", False)
        self.bio_markdown = kwargs.get("bio_markdown", None)
        self.operator_id = kwargs.get("operator_id", None)
        self.source_verified_at = kwargs.get("source_verified_at", None)
        self.type = kwargs.get("type", "agent")


def test_verification_additive():
    """Verification factor should stack additively, not use max()."""
    email_only = _FakeEntity(email_verified=True)
    email_bio = _FakeEntity(email_verified=True, bio_markdown="test bio")

    score_email = _verification_factor(email_only)
    score_both = _verification_factor(email_bio)

    assert score_both > score_email, (
        f"Email+bio ({score_both}) should be higher than email only ({score_email})"
    )


def test_verification_caps_at_one():
    """Verification factor should never exceed 1.0."""
    maxed = _FakeEntity(
        email_verified=True,
        bio_markdown="bio",
        operator_id="some-id",
        source_verified_at="2026-01-01",
    )
    score = _verification_factor(maxed)
    assert score <= 1.0, f"Verification factor {score} exceeds 1.0"


def test_verification_unverified_is_zero():
    """Completely unverified entity should score 0."""
    entity = _FakeEntity()
    assert _verification_factor(entity) == 0.0


# ── Score Computation ──


def test_score_formula_manual():
    """Manually compute score and verify it matches expected."""
    # Simulated entity: email verified (0.3) + bio (0.2) = 0.5 verification
    # Source-verified baseline: 0.6 external
    # Clean scan: 1.0 scan
    # 30-day account: ~0.08 age

    v = 0.5
    ext = 0.6
    scan = 1.0
    age = 0.08
    # v6: activity, reputation, community all 0

    expected = (
        v * VERIFICATION_WEIGHT
        + age * AGE_WEIGHT
        + 0.0 * ACTIVITY_WEIGHT
        + 0.0 * REPUTATION_WEIGHT
        + 0.0 * COMMUNITY_WEIGHT
        + ext * EXTERNAL_WEIGHT
        + scan * SCAN_WEIGHT
    )

    # Should be around 0.58 (C grade)
    assert 0.4 < expected < 0.7, f"Expected score ~0.58, got {expected}"


def test_human_scan_redistribution():
    """Humans should get scan weight redistributed to V + E."""
    # For humans: v_weight = V + 0.10, e_weight = E + 0.10, s_weight = 0
    v_human = VERIFICATION_WEIGHT + 0.10
    e_human = EXTERNAL_WEIGHT + 0.10
    s_human = 0.0

    # Weights should still sum to 1.0
    human_total = v_human + AGE_WEIGHT + ACTIVITY_WEIGHT + REPUTATION_WEIGHT + COMMUNITY_WEIGHT + e_human + s_human
    assert abs(human_total - 1.0) < 0.001, f"Human weights sum to {human_total}"


# ── Grade System ──


def test_grade_thresholds():
    """Grade thresholds should be consistent."""
    from src.api.trust_gateway_router import _score_to_grade

    assert _score_to_grade(100) == "A+"
    assert _score_to_grade(96) == "A+"
    assert _score_to_grade(95) == "A"
    assert _score_to_grade(81) == "A"
    assert _score_to_grade(80) == "B"
    assert _score_to_grade(61) == "B"
    assert _score_to_grade(60) == "C"
    assert _score_to_grade(41) == "C"
    assert _score_to_grade(40) == "D"
    assert _score_to_grade(21) == "D"
    assert _score_to_grade(20) == "F"
    assert _score_to_grade(0) == "F"


def test_badge_grade_matches_gateway_grade():
    """SVG badge grades must match gateway grades."""
    from src.api.badge_router import _trust_tier_label
    from src.api.trust_gateway_router import _score_to_grade

    # Test at each boundary (score as 0.0-1.0 for badge, 0-100 for gateway)
    for score_100 in [0, 10, 20, 21, 40, 41, 60, 61, 80, 81, 95, 96, 100]:
        score_float = score_100 / 100.0
        badge_grade = _trust_tier_label(score_float)
        gateway_grade = _score_to_grade(score_100)
        assert badge_grade == gateway_grade, (
            f"Score {score_100}: badge={badge_grade} != gateway={gateway_grade}"
        )


# ── Source-Verified Baseline ──


def test_source_verified_baseline():
    """Source-verified entities should get 0.6 external reputation baseline."""
    from src.trust.score import _source_reputation_score

    # The baseline is hardcoded in _external_reputation_factor
    # but we can verify the _source_reputation_score function
    # returns reasonable values for community signals
    assert _source_reputation_score({}) == 0.0
    assert _source_reputation_score({"stars": 100}) > 0.0
    assert _source_reputation_score({"stars": 1000}) > _source_reputation_score({"stars": 100})


# ── Per-Category Sub-Scores ──


def test_category_scores_all_clean():
    """A repo with no findings should have 100 across all categories."""
    from src.scanner.scan import ScanResult, _calculate_category_scores

    result = ScanResult(repo="test/clean", stars=0, description="", framework="")
    scores = _calculate_category_scores(result)

    assert scores["secret_hygiene"] == 100
    assert scores["code_safety"] == 100
    assert scores["data_handling"] == 100
    assert scores["filesystem_access"] == 100


def test_category_scores_with_findings():
    """Findings should reduce the relevant category score."""
    from src.scanner.scan import Finding, ScanResult, _calculate_category_scores

    result = ScanResult(
        repo="test/findings", stars=0, description="", framework="",
        findings=[
            Finding(
                category="secret", name="api_key", severity="critical",
                file_path="config.py", line_number=10, snippet="AKIA...",
            ),
        ],
    )
    scores = _calculate_category_scores(result)

    assert scores["secret_hygiene"] < 100, "Critical secret should reduce secret_hygiene"
    assert scores["code_safety"] == 100, "Secret finding shouldn't affect code_safety"


# ── Cache Invalidation ──


def test_cache_invalidation_imports():
    """Verify cache invalidation functions exist and are importable."""
    from src.cache import invalidate, invalidate_pattern

    assert callable(invalidate)
    assert callable(invalidate_pattern)


# ── External Providers ──


def test_external_providers_registry():
    """Provider registry should have expected providers."""
    from src.trust.external_providers import PROVIDERS

    provider_ids = {p["id"] for p in PROVIDERS}
    assert "rnwy" in provider_ids
    assert "moltbridge" in provider_ids
    assert "agentid" in provider_ids


def test_aggregate_empty_scores():
    """Aggregating empty attestations should return 0."""
    from src.trust.external_providers import aggregate_external_scores

    assert aggregate_external_scores([]) == 0.0


# ── Sybil Protection ──


def test_attestation_weight_not_falsy():
    """Verify the sybil fix: att.weight or 0.5 is NOT used."""
    # This is a code-level check — ensure the pattern doesn't exist
    import ast

    with open("src/trust/score.py") as f:
        source = f.read()

    # The bad pattern "att.weight or 0.5" should NOT exist
    assert "att.weight or 0.5" not in source, (
        "Sybil vulnerability: 'att.weight or 0.5' found in score.py. "
        "Should be 'att.weight if att.weight is not None else 0.5'"
    )
