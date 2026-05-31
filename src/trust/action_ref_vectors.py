"""CTEF action_ref near-miss conformance vectors (A2A #1734 / #1850).

Contributed to the ``action_ref`` joint IETF I-D (draft-giskard-aeoess-action-ref)
and the substrate-attestation conformance suite. ``action_ref`` correlates a
receipt back to the original agent action without trusting the operator:

    action_ref = "sha256:" + hex(SHA-256(JCS({agent_id, action_type, scope, timestamp_ms})))

These three near-miss vectors are the failure modes that correlation MUST catch
— each is structurally plausible and only fails on the binding semantics:

1. AMBIGUOUS_ISSUER_BINDING — two attestations share the same action_ref +
   subject + (claim_type, evidenceType) but differ in source_provider_did and
   disagree on the verdict. The action_ref four-tuple alone can't say which
   issuer is authoritative. A conformant verifier MUST NOT pick arbitrarily.
   This is exactly the C1 discrimination-tuple injectivity boundary.

2. RESCOPED_REPLAY — an attestation issued for scope S1 is presented against
   scope S2. Since scope is in the action_ref preimage, recomputing over the
   presented tuple yields a different hash than the embedded action_ref. The
   scope→action_ref binding breaks; a verifier MUST reject rather than honor
   the stale reference.

3. SEMANTIC_DRIFT — the same logical action carries an action_type that drifted
   between issuance and verification (e.g. "behavioral_eval" vs "behavioral").
   Different preimage → different action_ref for what is semantically one action.
   This is why action_type MUST be a closed vocabulary with canonical values;
   otherwise correlation fails silently across spec/version boundaries.

Format per the suite's request: preimage JSON + expected receipt fields +
failure-mode label, each with byte-reproducible canonical bytes + SHA-256 so any
party can recompute independently (same discipline as our CTEF v0.3.x vectors at
agentgraph.co/.well-known/cte-test-vectors.json).
"""
from __future__ import annotations

import hashlib

from src.signing import canonicalize_jcs_strict

SPEC = "CTEF action_ref near-miss conformance vectors"
SPEC_VERSION = "v0"
ID_REF = "draft-giskard-aeoess-action-ref"

# Fixed, deterministic sample data (no clocks — vectors must be reproducible).
_AGENT = "did:web:agent.example"
_TS_MS = 1_748_736_000_000  # fixed epoch-ms; arbitrary but pinned
_ISSUER_A = "did:web:issuer-a.example"
_ISSUER_B = "did:web:issuer-b.example"


def compute_action_ref(
    *, agent_id: str, action_type: str, scope: str, timestamp_ms: int
) -> str:
    """action_ref = sha256:hex(SHA-256(JCS({agent_id, action_type, scope, timestamp_ms}))).

    JCS sorts keys, so preimage key order is irrelevant — byte-identical across
    any RFC 8785 canonicalizer.
    """
    preimage = {
        "agent_id": agent_id,
        "action_type": action_type,
        "scope": scope,
        "timestamp_ms": timestamp_ms,
    }
    return "sha256:" + hashlib.sha256(canonicalize_jcs_strict(preimage)).hexdigest()


def _preimage_block(preimage: dict) -> dict:
    """A preimage with its canonical bytes + hash + derived action_ref."""
    canonical = canonicalize_jcs_strict(preimage)
    return {
        "preimage": preimage,
        "canonical_bytes_utf8": canonical.decode("utf-8"),
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "action_ref": "sha256:" + hashlib.sha256(canonical).hexdigest(),
    }


def _ctef_envelope(*, claim_type: str, provider_did: str, action_ref: str,
                   scope: str, verdict: str) -> dict:
    """Minimal CTEF v0.3.x envelope carrying an action_ref (negative-path shape)."""
    return {
        "@context": [
            "https://www.w3.org/ns/credentials/v2",
            "https://agentgraph.co/ns/trust-evidence/v1",
        ],
        "type": "TrustAttestation",
        "version": "0.3.2",
        "claim_type": claim_type,
        "provider": {"id": provider_did, "category": "behavioral_eval"},
        "subject": {"did": _AGENT, "scope": scope},
        "evidence_basis": {"action_ref": action_ref, "evidenceType": "third-party"},
        "attestation": {
            "type": "BehavioralAttestation",
            "confidence": 0.9,
            "admissibility_result": verdict,
        },
        "issued_at": "2026-06-01T00:00:00Z",
        "expires_at": "2026-06-01T01:00:00Z",
    }


def _ambiguous_issuer_binding() -> dict:
    pre = _preimage_block({
        "agent_id": _AGENT, "action_type": "behavioral_eval",
        "scope": "urn:scope:read", "timestamp_ms": _TS_MS,
    })
    ar = pre["action_ref"]
    return {
        "name": "ambiguous_issuer_binding",
        "failure_mode": "AMBIGUOUS_ISSUER_BINDING",
        "description": (
            "Two attestations share action_ref + subject + (claim_type, "
            "evidenceType) but differ in source_provider_did and disagree on the "
            "verdict. The four-tuple cannot select an authoritative issuer."
        ),
        "preimage_block": pre,
        "envelopes": [
            _ctef_envelope(claim_type="authority", provider_did=_ISSUER_A,
                           action_ref=ar, scope="urn:scope:read",
                           verdict="allow"),
            _ctef_envelope(claim_type="authority", provider_did=_ISSUER_B,
                           action_ref=ar, scope="urn:scope:read",
                           verdict="block"),
        ],
        "expected_result": "fail-closed",
        "expected_error_code": "AMBIGUOUS_ISSUER_BINDING",
        "expected_receipt_fields": {
            "action_ref": ar,
            "conflicting_providers": [_ISSUER_A, _ISSUER_B],
            "resolution": "rejected: no authoritative issuer binding",
        },
        "rationale": (
            "C1 discrimination-tuple injectivity: (claim_type, evidenceType, "
            "source_provider_did) must uniquely bind a verdict to an issuer. "
            "Same action_ref with two issuers and disjoint verdicts is the "
            "non-injective case the boundary exists to reject."
        ),
    }


def _rescoped_replay() -> dict:
    issued = _preimage_block({
        "agent_id": _AGENT, "action_type": "behavioral_eval",
        "scope": "urn:scope:read", "timestamp_ms": _TS_MS,
    })
    presented = _preimage_block({
        "agent_id": _AGENT, "action_type": "behavioral_eval",
        "scope": "urn:scope:write", "timestamp_ms": _TS_MS,
    })
    return {
        "name": "rescoped_replay",
        "failure_mode": "RESCOPED_REPLAY",
        "description": (
            "Attestation issued for scope 'urn:scope:read' is presented against "
            "'urn:scope:write'. Recomputing action_ref over the presented tuple "
            "diverges from the embedded action_ref — the scope binding is broken."
        ),
        "issued_preimage_block": issued,
        "presented_preimage_block": presented,
        "envelope": _ctef_envelope(
            claim_type="authority", provider_did=_ISSUER_A,
            action_ref=issued["action_ref"],   # stale: bound to read-scope
            scope="urn:scope:write",            # but presented for write-scope
            verdict="allow",
        ),
        "expected_result": "fail-closed",
        "expected_error_code": "RESCOPED_REPLAY",
        "expected_receipt_fields": {
            "embedded_action_ref": issued["action_ref"],
            "recomputed_action_ref": presented["action_ref"],
            "resolution": "rejected: presented scope not bound by action_ref",
        },
        "rationale": (
            "scope is in the action_ref preimage precisely so a rescoped "
            "presentation cannot reuse a stale reference. A verifier MUST "
            "recompute over the presented tuple and reject on mismatch."
        ),
    }


def _semantic_drift() -> dict:
    issuance = _preimage_block({
        "agent_id": _AGENT, "action_type": "behavioral_eval",
        "scope": "urn:scope:read", "timestamp_ms": _TS_MS,
    })
    verification = _preimage_block({
        "agent_id": _AGENT, "action_type": "behavioral",  # drifted vocab
        "scope": "urn:scope:read", "timestamp_ms": _TS_MS,
    })
    return {
        "name": "semantic_drift",
        "failure_mode": "SEMANTIC_DRIFT",
        "description": (
            "The same logical action carries action_type 'behavioral_eval' at "
            "issuance and 'behavioral' at verification (a real vocabulary drift "
            "from A2A #1786). Different preimage → different action_ref for one "
            "action."
        ),
        "issuance_preimage_block": issuance,
        "verification_preimage_block": verification,
        "expected_result": "fail-closed",
        "expected_error_code": "SEMANTIC_DRIFT",
        "expected_receipt_fields": {
            "issuance_action_ref": issuance["action_ref"],
            "verification_action_ref": verification["action_ref"],
            "resolution": "rejected: action_type not from closed canonical vocabulary",
        },
        "rationale": (
            "action_type MUST be a closed vocabulary with canonical values, or "
            "issuance and verification silently compute different action_refs. "
            "Normalizing-then-matching would mask the drift; fail-closed surfaces it."
        ),
    }


def build_artifact() -> dict:
    """Assemble the full published vectors artifact (byte-reproducible)."""
    return {
        "spec": SPEC,
        "version": SPEC_VERSION,
        "id_ref": ID_REF,
        "action_ref_definition": (
            'action_ref = "sha256:" + hex(SHA-256(JCS({agent_id, action_type, '
            "scope, timestamp_ms})))"
        ),
        "canonicalization": "RFC 8785 (JCS)",
        "reference_implementation": (
            "src.trust.action_ref_vectors.compute_action_ref over "
            "src.signing.canonicalize_jcs_strict (agentgraph-co/agentgraph)"
        ),
        "error_codes": {
            "AMBIGUOUS_ISSUER_BINDING": (
                "Same action_ref bound to >1 issuer with disjoint verdicts; "
                "no injective (claim_type, evidenceType, source_provider_did)."
            ),
            "RESCOPED_REPLAY": (
                "Presented scope not bound by the embedded action_ref."
            ),
            "SEMANTIC_DRIFT": (
                "action_type / field semantics differ between issuance and "
                "verification, yielding divergent action_refs for one action."
            ),
        },
        "vectors": [
            _ambiguous_issuer_binding(),
            _rescoped_replay(),
            _semantic_drift(),
        ],
    }


__all__ = ["compute_action_ref", "build_artifact", "SPEC", "SPEC_VERSION", "ID_REF"]
