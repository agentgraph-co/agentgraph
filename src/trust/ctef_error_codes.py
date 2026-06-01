"""CTEF unified error vocabulary — CTEF-side contribution (v0.3.3 Artifact 2).

The cross-spec error vocabulary consolidating CTEF + A2A #1496 §5 + APS + AIM +
Hippo error codes, routed by layer (wire / identity / authority / continuity /
correlation). This module is the CTEF-side starting contribution to the umbrella
that aeoess hosts at `aeoess/agent-governance-vocabulary`.

Two normative invariants every code obeys:
  1. STRUCTURAL-BEFORE-SEMANTIC: these are structural failures — a conformant
     verifier MUST return them BEFORE any semantic/policy evaluation. Fail-closed.
  2. CONTENT-ADDRESSED CONTEXT: where a code concerns a specific artifact (a
     claim, a delegation chain, an action_ref), the error names the
     content-addressed identifier so the failure is independently checkable.

Served at /.well-known/ctef-error-codes.json (reader-runnable) and pinned at
docs/standards/ctef-error-codes-v0.json. Same publication discipline as the CTEF
test vectors + action_ref near-miss vectors.
"""
from __future__ import annotations

SPEC = "CTEF unified error vocabulary (CTEF-side contribution)"
SPEC_VERSION = "v0"
UMBRELLA_TARGET = "aeoess/agent-governance-vocabulary"

# layer -> list of (code, triggers_on). Every code is fail-closed, structural,
# returned before semantic evaluation.
_LAYERS: dict[str, list[tuple[str, str]]] = {
    "wire": [
        ("INVALID_SIGNATURE_INPUT",
         "RFC 9421 Signature-Input line malformed or missing a required "
         "component (@method, @path, content-digest, created, nonce, keyid)."),
        ("CANONICALIZATION_MISMATCH",
         "Recomputed canonical bytes differ from the signed bytes (JCS RFC 8785 "
         "for structured fields, or RFC 9530 content-digest for wire bytes)."),
        ("CONTENT_DIGEST_MISMATCH",
         "RFC 9530 content-digest does not match the received wire body."),
        ("STALE_NONCE",
         "Nonce outside the freshness window (RECOMMENDED ≤300s) or replayed "
         "within it. Deterministic nonces (hash(created+keyid)) are prohibited."),
    ],
    "identity": [
        ("DID_RESOLUTION_FAILED",
         "Subject or issuer DID cannot be resolved by its method's rule "
         "(including resolve-at-time for ledger-anchored methods)."),
        ("JWKS_UNREACHABLE",
         "Issuer JWKS endpoint unreachable during verification."),
        ("KEY_NOT_IN_JWKS",
         "The kid referenced by verificationMethod is not present in the "
         "resolved JWKS at the relevant (resolve-at-time) point."),
        ("IDENTITY_BINDING_INVALID",
         "verificationMethod key does not bind to the claimed identity "
         "(claim_type=identity composition failure)."),
    ],
    "authority": [
        ("INVALID_CLAIM_SCOPE",
         "A claim carries fields outside its declared claim_type "
         "(e.g. identity-typed claim carrying authority-layer delegation)."),
        ("SCOPE_EXPANSION",
         "A child scope expands a parent scope — violates monotonic narrowing; "
         "effective scope is the greatest lower bound of the chain."),
        ("DELEGATION_DEPTH_EXCEEDED",
         "Delegation chain depth exceeds the declared maximum."),
        ("INVALID_COMPOSITION",
         "Well-typed claims at each layer cannot be combined under the layer's "
         "composition rule (e.g. disjoint authority scopes)."),
    ],
    "continuity": [
        ("ROTATION_GAP",
         "Rotation-attestation chain has a gap — a kid transition is "
         "unaccounted for in the history."),
        ("EPOCH_MISMATCH",
         "session_epoch in the claim does not match the resolved epoch."),
        ("SEQUENCE_VIOLATION",
         "Sequence number out of order in the rotation/continuity record."),
    ],
    "correlation": [
        ("AMBIGUOUS_ISSUER_BINDING",
         "The same action_ref + subject + (claim_type, evidenceType) is bound "
         "to more than one issuer with disjoint verdicts — non-injective "
         "discrimination tuple. See action-ref-near-miss-vectors.json."),
        ("RESCOPED_REPLAY",
         "Presented scope is not bound by the embedded action_ref; recomputing "
         "action_ref over the presented tuple diverges from the embedded value."),
        ("SEMANTIC_DRIFT",
         "action_type or a field's semantics differ between issuance and "
         "verification, yielding divergent action_refs for one logical action."),
    ],
}

# Codes that originate elsewhere; CTEF references rather than owns them.
_CROSS_SPEC_REFERENCES = {
    "A2A #1496 §5": [
        "SCOPE_EXPANSION", "DELEGATION_DEPTH_EXCEEDED",
        "INVALID_SIGNATURE_INPUT (signature substitution)", "ROTATION_GAP (expired chain)",
    ],
    "action_ref I-D (draft-giskard-aeoess-action-ref)": [
        "AMBIGUOUS_ISSUER_BINDING", "RESCOPED_REPLAY", "SEMANTIC_DRIFT",
    ],
}


def build_vocabulary() -> dict:
    """Assemble the published error-vocabulary artifact."""
    layers = {
        layer: [
            {"code": code, "layer": layer, "triggers_on": triggers,
             "fail_closed": True, "ordering": "structural-before-semantic"}
            for code, triggers in entries
        ]
        for layer, entries in _LAYERS.items()
    }
    return {
        "spec": SPEC,
        "version": SPEC_VERSION,
        "umbrella_target": UMBRELLA_TARGET,
        "ordering_invariant": (
            "Every code is a STRUCTURAL failure returned BEFORE any semantic or "
            "policy evaluation. Fail-closed by construction (CTEF v0.3.1 §ordering)."
        ),
        "canonicalization": "RFC 8785 (JCS) for structured fields; RFC 9530 for wire bytes",
        "layers": layers,
        "cross_spec_references": _CROSS_SPEC_REFERENCES,
        "reference_implementation": (
            "src.trust.ctef_error_codes (agentgraph-co/agentgraph)"
        ),
    }


def all_codes() -> set[str]:
    """Flat set of every code defined here (for uniqueness checks)."""
    return {code for entries in _LAYERS.values() for code, _ in entries}


__all__ = ["build_vocabulary", "all_codes", "SPEC", "SPEC_VERSION"]
