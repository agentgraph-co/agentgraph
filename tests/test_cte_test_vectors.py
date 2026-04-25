"""Regression test for /.well-known/cte-test-vectors.json (CTEF v0.3.1).

Partners implementing CTEF v0.3.1 verifiers (APS, AgentID, MoltBridge,
Verascore, Concordia, Hive, ...) reproduce the canonical bytes + SHA-256
locally from this document and compare byte-for-byte. If our canonical
form drifts without the spec version bumping, partners break silently.
Pin the expected canonical output.

Companion to ``tests/test_jcs_canonicalize_aps_interop.py`` (APS
bilateral-delegation fixture, snapshot) and
``tests/test_aps_rotation_attestation_interop.py`` (APS continuity
rotation, live-fetch). Together these three tests close the
canonicalization loop across APS bilateral delegation, APS continuity
rotation, and our own published CTEF envelope/verdict/negative shapes.

v0.3.1 additions tested here:
  - ``claim_type`` closed-set discriminator on the envelope.
  - ``composition_rules`` per-layer declaration.
  - ``INVALID_CLAIM_SCOPE`` / ``INVALID_COMPOSITION`` error codes with
    structural-failure-precedes-semantic-evaluation ordering.
  - Negative-path test vectors (scope_violation, composition_failure)
    reproducible byte-for-byte; partner verifiers check their verdict
    against the ``expected_error_code`` field.
  - Reserved values for ``claim_type.envelope`` (regulatory-envelope
    attestation, Hive contribution) and
    ``evidence_basis.evidence_type.payment_execution`` (HiveCompute
    x402 receipt contribution).
"""
from __future__ import annotations

import asyncio
import hashlib
import json

_CLAIM_TYPE_CLOSED_SET = {"identity", "transport", "authority", "continuity"}
_ADMISSIBILITY_CLOSED_SET = {
    "allow",
    "conditional_allow",
    "provisional_allow",
    "block",
    "refer",
}
_BINDING_MODE_CLOSED_SET = {
    "authority_within_window_evidence_after",
    "authority_within_window_expired_after",
    "sequence_bound",
}
_FORWARDABILITY_CLOSED_SET = {"local", "bounded", "delegatable"}


def test_cte_test_vectors_reproducible():
    from src.api.jwks_router import cte_test_vectors
    from src.signing import canonicalize_jcs_strict

    resp = asyncio.run(cte_test_vectors())
    doc = json.loads(resp.body)

    # Spec identity must not drift silently.
    assert doc["version"] == "0.3.1"
    assert doc["spec"] == "CTEF (Composable Trust Evidence Format)"

    # Canonicalization contract — partners rely on these strings to pick
    # the correct canonicalizer implementation on their side.
    assert doc["contract"]["canonicalization"] == (
        "RFC 8785 (JSON Canonicalization Scheme)"
    )
    assert doc["contract"]["hash_algorithm"] == "SHA-256"

    # Reproduce the envelope vector locally from its declared input.
    # This must be byte-identical to what we published, or a partner
    # using our same canonicalizer will see divergence.
    env = doc["envelope_vector"]
    env_canonical = canonicalize_jcs_strict(env["input_object"])
    assert env_canonical.decode("utf-8") == env["canonical_bytes_utf8"]
    assert hashlib.sha256(env_canonical).hexdigest() == env["canonical_sha256"]
    assert env["expected_result"] == "pass"

    # v0.3.1: envelope MUST declare claim_type from the closed set.
    assert "claim_type" in env["input_object"]
    assert env["input_object"]["claim_type"] in _CLAIM_TYPE_CLOSED_SET
    # The happy-path envelope carries authority-layer delegation.
    assert env["input_object"]["claim_type"] == "authority"

    # Envelope must carry the v0.3 delegation composition field.
    assert "delegation" in env["input_object"]
    assert "delegation_chain_root" in env["input_object"]["delegation"]
    assert env["input_object"]["delegation"]["canonicalization"] == "RFC-8785"

    # Reproduce the verdict vector locally.
    verdict = doc["verdict_vector"]
    v_canonical = canonicalize_jcs_strict(verdict["input_object"])
    assert v_canonical.decode("utf-8") == verdict["canonical_bytes_utf8"]
    assert hashlib.sha256(v_canonical).hexdigest() == verdict["canonical_sha256"]
    assert verdict["expected_result"] == "pass"

    # Verdict must carry all 5 required claim-model dimensions per §6.3.
    claim = verdict["input_object"]["claim"]
    assert set(claim.keys()) >= {
        "action",
        "evidence_basis",
        "admissibility_result",
        "validity_window",
        "forwardability",
    }
    # And the verdict family must be from the closed v0.3.1 set (§6.1/§6.4).
    assert claim["admissibility_result"] in _ADMISSIBILITY_CLOSED_SET
    # validity_window binding_mode must be from the closed v0.3.1 set.
    assert claim["validity_window"]["binding_mode"] in _BINDING_MODE_CLOSED_SET
    # forwardability mode must be from the closed v0.3.1 set.
    assert claim["forwardability"]["mode"] in _FORWARDABILITY_CLOSED_SET


def test_cte_v031_claim_model_contract():
    """v0.3.1 claim-model contract published in the document itself.

    Partners building verifiers load these values from the document to
    pick their closed sets. If we widen a set silently, partners widen
    with us or go out of date — pin the set so widening requires a spec
    bump that partners can decide to track.
    """
    from src.api.jwks_router import cte_test_vectors

    resp = asyncio.run(cte_test_vectors())
    doc = json.loads(resp.body)

    claim_model = doc["claim_model"]
    assert set(claim_model["claim_type"]["closed_set"]) == (
        _CLAIM_TYPE_CLOSED_SET
    )
    assert claim_model["claim_type"]["required_on_envelope"] is True

    # Composition rule must be declared for every layer in the closed set.
    rules = claim_model["composition_rules"]
    assert set(rules.keys()) == _CLAIM_TYPE_CLOSED_SET


def test_cte_v031_error_codes_declared():
    """v0.3.1 error codes must be published and both must fire before
    semantic evaluation (ordering constraint from §6.4)."""
    from src.api.jwks_router import cte_test_vectors

    resp = asyncio.run(cte_test_vectors())
    doc = json.loads(resp.body)

    error_codes = doc["error_codes"]
    assert "INVALID_CLAIM_SCOPE" in error_codes
    assert "INVALID_COMPOSITION" in error_codes
    for code in ("INVALID_CLAIM_SCOPE", "INVALID_COMPOSITION"):
        assert "Structural failure precedes semantic evaluation" in (
            error_codes[code]["ordering"]
        )


def test_cte_v031_scope_violation_vector_reproduces():
    """Negative-path scope-violation vector must reproduce byte-exact
    and structurally carry the violation condition."""
    from src.api.jwks_router import cte_test_vectors
    from src.signing import canonicalize_jcs_strict

    resp = asyncio.run(cte_test_vectors())
    doc = json.loads(resp.body)

    sv = doc["scope_violation_vector"]
    canonical = canonicalize_jcs_strict(sv["input_object"])
    assert canonical.decode("utf-8") == sv["canonical_bytes_utf8"]
    assert hashlib.sha256(canonical).hexdigest() == sv["canonical_sha256"]

    # Fail-closed expectation + error-code contract.
    assert sv["expected_result"] == "fail-closed"
    assert sv["expected_error_code"] == "INVALID_CLAIM_SCOPE"

    # Structural condition: claim_type=identity but carries
    # authority-layer delegation. A conformant verifier MUST detect this
    # structurally before any semantic evaluation.
    obj = sv["input_object"]
    assert obj["claim_type"] == "identity"
    assert "delegation" in obj
    assert "delegation_chain_root" in obj["delegation"]


def test_cte_v031_composition_failure_vector_reproduces():
    """Negative-path composition-failure vector must reproduce byte-exact
    and structurally carry the disjoint-scope condition."""
    from src.api.jwks_router import cte_test_vectors
    from src.signing import canonicalize_jcs_strict

    resp = asyncio.run(cte_test_vectors())
    doc = json.loads(resp.body)

    cf = doc["composition_failure_vector"]
    canonical = canonicalize_jcs_strict(cf["input_object"])
    assert canonical.decode("utf-8") == cf["canonical_bytes_utf8"]
    assert hashlib.sha256(canonical).hexdigest() == cf["canonical_sha256"]

    # Fail-closed expectation + error-code contract.
    assert cf["expected_result"] == "fail-closed"
    assert cf["expected_error_code"] == "INVALID_COMPOSITION"

    # Structural condition: two authority chains with disjoint scopes.
    # Monotonic narrowing produces an empty intersection, so a conformant
    # verifier cannot compose to a single effective scope.
    obj = cf["input_object"]
    assert obj["claim_type"] == "authority"
    chains = obj["delegation"]["chains"]
    assert len(chains) >= 2
    scopes = [c["scope"] for c in chains]
    # The two scopes must be distinct so the greatest-lower-bound
    # intersection is empty (for these string-identity scopes).
    assert len(set(scopes)) == len(scopes)


def test_cte_v031_reserved_values_published():
    """v0.3.1 reserved values for forthcoming spec extensions must be
    announced in the document so partners do not collide on the names
    before we ship the full spec."""
    from src.api.jwks_router import cte_test_vectors

    resp = asyncio.run(cte_test_vectors())
    doc = json.loads(resp.body)

    reserved = doc["reserved_values"]
    # Hive regulatory-envelope layer, committed on A2A#1672.
    assert "claim_type.envelope" in reserved
    assert reserved["claim_type.envelope"]["status"] == "reserved"
    # HiveCompute x402 payment-execution receipt, committed on
    # insumer-examples#1.
    assert "evidence_basis.evidence_type.payment_execution" in reserved
    assert (
        reserved["evidence_basis.evidence_type.payment_execution"]["status"]
        == "reserved"
    )
