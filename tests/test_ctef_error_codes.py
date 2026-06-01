"""Tests for the CTEF unified error vocabulary (v0.3.3 Artifact 2)."""
from __future__ import annotations

from src.trust.ctef_error_codes import all_codes, build_vocabulary


def test_codes_are_unique():
    codes = [c for entries in build_vocabulary()["layers"].values() for c in
             [e["code"] for e in entries]]
    assert len(codes) == len(set(codes)), "duplicate error code across layers"


def test_every_code_fail_closed_and_structural():
    for entries in build_vocabulary()["layers"].values():
        for e in entries:
            assert e["fail_closed"] is True
            assert e["ordering"] == "structural-before-semantic"
            assert e["triggers_on"]


def test_expected_layers_present():
    layers = build_vocabulary()["layers"]
    assert set(layers) == {"wire", "identity", "authority", "continuity", "correlation"}


def test_known_codes_present():
    codes = all_codes()
    # existing CTEF structural codes
    assert {"INVALID_CLAIM_SCOPE", "INVALID_COMPOSITION"} <= codes
    # action_ref near-miss codes
    assert {"AMBIGUOUS_ISSUER_BINDING", "RESCOPED_REPLAY", "SEMANTIC_DRIFT"} <= codes


def test_ordering_invariant_documented():
    v = build_vocabulary()
    assert "structural" in v["ordering_invariant"].lower()
    assert "fail-closed" in v["ordering_invariant"].lower()
