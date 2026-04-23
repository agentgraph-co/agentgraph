"""Regression test for /.well-known/cte-test-vectors.json (CTEF v0.3).

Partners implementing CTEF v0.3 verifiers (APS, AgentID, MoltBridge,
Verascore, Concordia, ...) reproduce the canonical bytes + SHA-256
locally from this document and compare byte-for-byte. If our canonical
form drifts without the spec version bumping, partners break silently.
Pin the expected canonical output.

Companion to ``tests/test_jcs_canonicalize_aps_interop.py`` which locks
the canonicalizer itself against the APS bilateral-delegation fixture.
This test locks the *published* test vectors against that same
canonicalizer — closing the loop so a partner fetching our well-known
endpoint sees output that matches APS's fixture semantics.
"""
from __future__ import annotations

import asyncio
import hashlib
import json


def test_cte_test_vectors_reproducible():
    from src.api.jwks_router import cte_test_vectors
    from src.signing import canonicalize_jcs_strict

    resp = asyncio.run(cte_test_vectors())
    doc = json.loads(resp.body)

    # Spec identity must not drift silently.
    assert doc["version"] == "0.3.0"
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

    # Envelope must carry the v0.3 delegation composition field.
    assert "delegation" in env["input_object"]
    assert "delegation_chain_root" in env["input_object"]["delegation"]
    assert env["input_object"]["delegation"]["canonicalization"] == "RFC-8785"

    # Reproduce the verdict vector locally.
    verdict = doc["verdict_vector"]
    v_canonical = canonicalize_jcs_strict(verdict["input_object"])
    assert v_canonical.decode("utf-8") == verdict["canonical_bytes_utf8"]
    assert hashlib.sha256(v_canonical).hexdigest() == verdict["canonical_sha256"]

    # Verdict must carry all 5 required claim-model dimensions per §6.3.
    claim = verdict["input_object"]["claim"]
    assert set(claim.keys()) >= {
        "action",
        "evidence_basis",
        "admissibility_result",
        "validity_window",
        "forwardability",
    }
    # And the verdict family must be from the closed v0.3 set (§6.1/§6.4).
    assert claim["admissibility_result"] in {
        "allow",
        "conditional_allow",
        "provisional_allow",
        "block",
        "refer",
    }
    # validity_window binding_mode must be from the closed v0.3 set.
    assert claim["validity_window"]["binding_mode"] in {
        "authority_within_window_evidence_after",
        "authority_within_window_expired_after",
        "sequence_bound",
    }
    # forwardability mode must be from the closed v0.3 set.
    assert claim["forwardability"]["mode"] in {"local", "bounded", "delegatable"}
