"""Tests for the CTEF action_ref near-miss conformance vectors (#1734/#1850).

Locks byte-reproducibility (any RFC 8785 canonicalizer must reproduce these) and
that each vector actually exhibits its failure mode.
"""
from __future__ import annotations

import hashlib

from src.signing import canonicalize_jcs_strict
from src.trust.action_ref_vectors import build_artifact, compute_action_ref


def test_action_ref_is_jcs_sorted_and_deterministic():
    # key order in the call must not matter (JCS sorts) — both compute the same.
    a = compute_action_ref(
        agent_id="did:web:x", action_type="t", scope="s", timestamp_ms=1
    )
    b = compute_action_ref(
        timestamp_ms=1, scope="s", action_type="t", agent_id="did:web:x"
    )
    assert a == b
    assert a.startswith("sha256:")
    # matches an independent recompute over the canonical preimage
    expected = "sha256:" + hashlib.sha256(
        canonicalize_jcs_strict(
            {"agent_id": "did:web:x", "action_type": "t", "scope": "s",
             "timestamp_ms": 1}
        )
    ).hexdigest()
    assert a == expected


def test_artifact_has_three_negative_vectors():
    art = build_artifact()
    names = [v["name"] for v in art["vectors"]]
    assert names == ["ambiguous_issuer_binding", "rescoped_replay", "semantic_drift"]
    for v in art["vectors"]:
        assert v["expected_result"] == "fail-closed"
        assert v["expected_error_code"] in art["error_codes"]


def test_ambiguous_issuer_binding_shares_action_ref():
    v = build_artifact()["vectors"][0]
    e0, e1 = v["envelopes"]
    # same action_ref + subject, different issuer, disjoint verdict
    assert e0["evidence_basis"]["action_ref"] == e1["evidence_basis"]["action_ref"]
    assert e0["provider"]["id"] != e1["provider"]["id"]
    assert e0["attestation"]["admissibility_result"] != e1["attestation"]["admissibility_result"]


def test_rescoped_replay_action_ref_diverges():
    v = build_artifact()["vectors"][1]
    assert (
        v["issued_preimage_block"]["action_ref"]
        != v["presented_preimage_block"]["action_ref"]
    )
    # envelope carries the stale (issued) ref but a different presented scope
    assert v["envelope"]["evidence_basis"]["action_ref"] == v["issued_preimage_block"]["action_ref"]
    assert v["envelope"]["subject"]["scope"] == "urn:scope:write"


def test_semantic_drift_action_ref_diverges():
    v = build_artifact()["vectors"][2]
    assert (
        v["issuance_preimage_block"]["action_ref"]
        != v["verification_preimage_block"]["action_ref"]
    )


def test_canonical_bytes_reproducible():
    # every preimage block's stated bytes must reproduce its stated hash
    art = build_artifact()
    blocks = []
    for v in art["vectors"]:
        blocks += [v[k] for k in v if k.endswith("preimage_block")]
    assert blocks
    for b in blocks:
        recomputed = hashlib.sha256(b["canonical_bytes_utf8"].encode("utf-8")).hexdigest()
        assert recomputed == b["canonical_sha256"]
        assert b["action_ref"] == "sha256:" + b["canonical_sha256"]
