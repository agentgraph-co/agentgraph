"""JWKS and well-known endpoints for AgentGraph's cryptographic identity."""
from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.signing import canonicalize_jcs_strict, get_jwk

router = APIRouter(tags=["jwks"])

# OATR (Open Agent Trust Registry) identity
_OATR_ISSUER_ID = "agentgraph"
_OATR_PUBLIC_KEY = "jWRrozl7KF08Cxjpu41FpdLMvXMC_L8U2ZYJUMvckgk"

# ── Webhook test vectors ──────────────────────────────────────────────
# Partners implementing the scan-change receiver (MoltBridge, Verascore,
# etc.) can fetch /.well-known/webhook-test-vectors.json, reproduce the
# HMAC locally, and confirm byte-for-byte agreement with our outbound
# signing path before we wire a live shared secret. These are fixed,
# deterministic, and intentionally use an obvious test-only key.
_TEST_VECTOR_SECRET = "TEST-ONLY-DO-NOT-USE-FOR-LIVE-VERIFICATION"
_TEST_VECTOR_TIMESTAMP = "2026-04-22T00:00:00+00:00"
_TEST_VECTOR_BODY_OBJ = {
    "type": "scan-change",
    "repo": "example-org/example-repo",
    "new_score": 82,
    "old_score": 71,
    "changed_at": _TEST_VECTOR_TIMESTAMP,
    "jws": "TEST-PLACEHOLDER-JWS-NOT-A-VALID-SIGNATURE",
}


@router.get("/.well-known/jwks.json")
async def jwks() -> JSONResponse:
    """Return the platform JWKS (RFC 7517) for attestation verification."""
    return JSONResponse(
        content={"keys": [get_jwk()]},
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/.well-known/webhook-test-vectors.json")
async def webhook_test_vectors() -> JSONResponse:
    """Publish deterministic test vectors for the partner scan-change webhook.

    Partners building a receive-side verifier for AgentGraph's outbound
    ``scan-change`` events can reproduce the HMAC locally and confirm
    byte-for-byte agreement with our sender before a live shared secret
    is exchanged. The canonical form is identical to what production
    emits from ``src.trust.outbound_webhooks``.

    Canonical form:
      ``body_bytes = json.dumps(body, separators=(",", ":"),
      sort_keys=True).encode("utf-8")``

    Signature:
      ``X-Partner-Signature: sha256=<hex>`` where
      ``hex = hmac_sha256(shared_secret, body_bytes).hexdigest()``

    Replay window: ``X-Partner-Timestamp`` (ISO-8601) must be within ±5
    minutes of receive time.
    """
    canonical_bytes = json.dumps(
        _TEST_VECTOR_BODY_OBJ, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    mac = hmac.new(
        _TEST_VECTOR_SECRET.encode("utf-8"),
        canonical_bytes,
        hashlib.sha256,
    ).hexdigest()

    return JSONResponse(
        content={
            "version": "1.0",
            "event": "scan-change",
            "contract": {
                "canonicalization": (
                    'json.dumps(body, separators=(",", ":"), sort_keys=True)'
                    ' encoded as UTF-8'
                ),
                "signature_algorithm": "HMAC-SHA256",
                "signature_header": "X-Partner-Signature",
                "signature_format": "sha256=<hex>",
                "timestamp_header": "X-Partner-Timestamp",
                "timestamp_format": "ISO-8601 (±5 minute window)",
                "event_header": "X-AgentGraph-Event",
                "content_type": "application/json",
                "jws_verification": (
                    "Body.jws is optionally verifiable via "
                    "/.well-known/jwks.json (kid agentgraph-security-v1,"
                    " Ed25519/EdDSA). The test vector uses a placeholder "
                    "jws string — real outbound events carry a valid JWS."
                ),
                "partner_docs": (
                    "https://agentgraph.co/api/v1/gateway/webhook/subscribe"
                ),
            },
            "test_vector": {
                "note": (
                    "Test-only shared secret — deterministic; do NOT use for"
                    " live signature verification. Partners should reproduce"
                    " canonical_bytes + signature locally and compare."
                ),
                "shared_secret": _TEST_VECTOR_SECRET,
                "body_object": _TEST_VECTOR_BODY_OBJ,
                "canonical_bytes_utf8": canonical_bytes.decode("utf-8"),
                "expected_headers": {
                    "Content-Type": "application/json",
                    "User-Agent": "AgentGraph-Webhook/1.0",
                    "X-AgentGraph-Event": "scan-change",
                    "X-Partner-Timestamp": _TEST_VECTOR_TIMESTAMP,
                    "X-Partner-Signature": f"sha256={mac}",
                },
                "expected_signature_hex": mac,
            },
        },
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── CTEF (Composable Trust Evidence Format) test vectors ─────────────
# Partners implementing CTEF v0.3 verifiers (APS, AgentID, MoltBridge,
# Verascore, Concordia, ...) can fetch /.well-known/cte-test-vectors.json,
# reproduce the canonical bytes + delegation_chain_root locally, and
# confirm byte-for-byte agreement with the AgentGraph canonicalizer
# before wiring a live bilateral composition. The canonical form is
# RFC 8785 JCS, identical to what src.signing.canonicalize_jcs_strict
# produces and byte-exact with the APS bilateral-delegation fixture at
# aeoess/agent-passport-system/fixtures/bilateral-delegation.
_CTE_ENVELOPE_EXAMPLE = {
    "@context": [
        "https://www.w3.org/ns/credentials/v2",
        "https://agentgraph.co/ns/trust-evidence/v1",
    ],
    "type": "TrustAttestation",
    "version": "0.3.1",
    "claim_category": "authority",
    "provider": {
        "id": "did:web:agentgraph.co",
        "name": "AgentGraph Trust Scanner",
        "category": "static_analysis",
        "version": "0.3.1",
    },
    "subject": {
        "did": "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
        "repo": "example-org/example-repo",
        "ref": "main",
    },
    "attestation": {
        "type": "SecurityAttestation",
        "confidence": 0.82,
        "payload": {
            "trust_score": 66,
            "grade": "B",
            "findings": {"critical": 0, "high": 2, "medium": 5, "total": 7},
        },
    },
    "delegation": {
        "delegation_chain_root": (
            "4f3d8defea1e82c1705c35d97ee4db046c6313ba83855a7d0de04a44f04c834a"
        ),
        "delegation_depth": 2,
        "canonicalization": "RFC-8785",
    },
    "issued_at": "2026-04-23T00:00:00Z",
    "expires_at": "2026-04-23T01:00:00Z",
}

# v0.3.1 negative-path vector: scope violation.
# Envelope declares claim_category="identity" but carries authority-layer
# fields (delegation). A conformant verifier MUST return
# INVALID_CLAIM_SCOPE before any semantic evaluation.
_CTE_SCOPE_VIOLATION_EXAMPLE = {
    "@context": [
        "https://www.w3.org/ns/credentials/v2",
        "https://agentgraph.co/ns/trust-evidence/v1",
    ],
    "type": "TrustAttestation",
    "version": "0.3.1",
    "claim_category": "identity",
    "provider": {
        "id": "did:web:agentgraph.co",
        "name": "AgentGraph Trust Scanner",
        "category": "static_analysis",
        "version": "0.3.1",
    },
    "subject": {
        "did": "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
    },
    "attestation": {
        "type": "IdentityAttestation",
        "confidence": 0.9,
        "payload": {"key_status": "active"},
    },
    "delegation": {
        "delegation_chain_root": (
            "4f3d8defea1e82c1705c35d97ee4db046c6313ba83855a7d0de04a44f04c834a"
        ),
        "delegation_depth": 2,
        "canonicalization": "RFC-8785",
    },
    "issued_at": "2026-04-23T00:00:00Z",
    "expires_at": "2026-04-23T01:00:00Z",
}

# v0.3.1 negative-path vector: composition failure.
# Two authority-layer delegation chains with disjoint scopes. Monotonic
# narrowing produces an empty intersection, so a conformant verifier MUST
# return INVALID_COMPOSITION before semantic evaluation.
_CTE_COMPOSITION_FAILURE_EXAMPLE = {
    "@context": [
        "https://www.w3.org/ns/credentials/v2",
        "https://agentgraph.co/ns/trust-evidence/v1",
    ],
    "type": "TrustAttestation",
    "version": "0.3.1",
    "claim_category": "authority",
    "provider": {
        "id": "did:web:agentgraph.co",
        "name": "AgentGraph Trust Scanner",
        "category": "static_analysis",
        "version": "0.3.1",
    },
    "subject": {
        "did": "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
    },
    "attestation": {
        "type": "AuthorityComposition",
        "confidence": 0.7,
        "payload": {"composition_type": "multi_chain"},
    },
    "delegation": {
        "chains": [
            {
                "delegation_chain_root": (
                    "4f3d8defea1e82c1705c35d97ee4db046c6313ba83855a7d0de04a44f04c834a"
                ),
                "scope": "urn:agentgraph:platform:feed:write",
            },
            {
                "delegation_chain_root": (
                    "b11a72b09b8184e3cc4620e0d5fe0926f6fecfb8cd35c2ef364c5761647c43b4"
                ),
                "scope": "urn:agentgraph:platform:marketplace:buy",
            },
        ],
        "canonicalization": "RFC-8785",
    },
    "issued_at": "2026-04-23T00:00:00Z",
    "expires_at": "2026-04-23T01:00:00Z",
}

_CTE_VERDICT_EXAMPLE = {
    "type": "EnforcementVerdict",
    "version": "0.3.1",
    "gateway": {
        "id": "did:web:agentgraph.co#gateway",
        "name": "AgentGraph Trust Gateway",
        "version": "0.3.1",
    },
    "claim": {
        "action": {
            "type": "mutation:platform_access",
            "target": "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
            "scope": "urn:agentgraph:platform:feed:write",
        },
        "evidence_basis": {
            "bundle_hash": (
                "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
            ),
            "delegation_chain_root": (
                "4f3d8defea1e82c1705c35d97ee4db046c6313ba83855a7d0de04a44f04c834a"
            ),
        },
        "admissibility_result": "conditional_allow",
        "validity_window": {
            "not_before": "2026-04-23T00:00:00Z",
            "not_after": "2026-04-23T01:00:00Z",
            "binding_mode": "authority_within_window_evidence_after",
        },
        "forwardability": {
            "mode": "local",
            "forwardable_to": [],
            "delegation_path": None,
        },
    },
    "issued_at": "2026-04-23T00:00:00Z",
    "expires_at": "2026-04-23T01:00:00Z",
}


@router.get("/.well-known/cte-test-vectors.json")
async def cte_test_vectors() -> JSONResponse:
    """Publish deterministic test vectors for CTEF v0.3 canonicalization.

    Partners building a CTEF v0.3 verifier (or a provider that composes
    with AgentGraph bilaterally) can reproduce the canonical bytes + the
    delegation-chain-root hash locally and confirm byte-for-byte
    agreement with AgentGraph's canonicalizer. The canonical form is
    identical to ``src.signing.canonicalize_jcs_strict`` and is validated
    against the APS bilateral-delegation fixture (10 JCS vectors, all
    passing) — so an APS-conformant verifier and an AgentGraph-conformant
    verifier MUST produce byte-exact agreement on the same input.

    The two example envelopes here (a ``TrustAttestation`` carrying a
    ``delegation_chain_root``, and an ``EnforcementVerdict`` carrying
    the v0.3 5-dimension claim model) exercise the full surface a
    partner needs to implement.
    """
    envelope_bytes = canonicalize_jcs_strict(_CTE_ENVELOPE_EXAMPLE)
    verdict_bytes = canonicalize_jcs_strict(_CTE_VERDICT_EXAMPLE)
    scope_violation_bytes = canonicalize_jcs_strict(_CTE_SCOPE_VIOLATION_EXAMPLE)
    composition_failure_bytes = canonicalize_jcs_strict(
        _CTE_COMPOSITION_FAILURE_EXAMPLE
    )

    envelope_sha = hashlib.sha256(envelope_bytes).hexdigest()
    verdict_sha = hashlib.sha256(verdict_bytes).hexdigest()
    scope_violation_sha = hashlib.sha256(scope_violation_bytes).hexdigest()
    composition_failure_sha = hashlib.sha256(composition_failure_bytes).hexdigest()

    return JSONResponse(
        content={
            "version": "0.3.1",
            "spec": "CTEF (Composable Trust Evidence Format)",
            "contract": {
                "canonicalization": "RFC 8785 (JSON Canonicalization Scheme)",
                "canonicalization_rules": [
                    "Keys sorted by Unicode code point.",
                    "Non-ASCII above U+001F emitted as literal UTF-8 bytes (not \\uXXXX escapes).",
                    "null values preserved at every depth.",
                    "Integer-valued floats normalized to integers (ECMA-262 §7.1.12.1).",
                ],
                "hash_algorithm": "SHA-256",
                "delegation_chain_root": (
                    "hex(sha256(canonicalize_jcs_strict(delegation_chain)))"
                ),
                "reference_implementation": (
                    "src.signing.canonicalize_jcs_strict "
                    "(agentgraph-co/agentgraph)"
                ),
                "reference_fixtures": [
                    {
                        "source": (
                            "aeoess/agent-passport-system/fixtures/bilateral-delegation/"
                            "canonicalize-fixture-v1.json"
                        ),
                        "vectors": 10,
                        "status": "AgentGraph passes 10/10 byte-exact",
                        "test": "tests/test_jcs_canonicalize_aps_interop.py",
                    },
                    {
                        "source": "https://aeoess.com/fixtures/rotation-attestation/",
                        "vectors": 5,
                        "status": "AgentGraph passes 5/5 byte-exact (live-fetch dual-lock)",
                        "test": "tests/test_aps_rotation_attestation_interop.py",
                    },
                ],
                "rfc": (
                    "See docs/internal/rfc-evidence-format-v1.md in "
                    "agentgraph-co/agentgraph for the full CTEF v0.3.1 spec."
                ),
            },
            "claim_model": {
                "claim_category": {
                    "closed_set": [
                        "identity",
                        "transport",
                        "authority",
                        "continuity",
                    ],
                    "required_on_envelope": True,
                    "note": (
                        "Outer discriminator for the claim-layer semantics. "
                        "Added in v0.3.1. A claim carrying fields outside "
                        "its declared category MUST be rejected with "
                        "INVALID_CLAIM_SCOPE before semantic evaluation."
                    ),
                },
                "composition_rules": {
                    "identity": (
                        "Key binding — same DID across claims, same "
                        "resolution path. Two verifiers given the same "
                        "identity claim must resolve the same key."
                    ),
                    "transport": (
                        "Identity-key binding — the identity signs the "
                        "transport key. Transport-layer claims compose "
                        "onto the identity they reference."
                    ),
                    "authority": (
                        "Monotonic narrowing — effective scope after a "
                        "delegation chain is the greatest lower bound "
                        "(intersection) of every scope in the chain. "
                        "Content-addressed via delegation_chain_root. "
                        "Two claims with disjoint scopes produce "
                        "INVALID_COMPOSITION."
                    ),
                    "continuity": (
                        "Rotation-attestation chain — history-stability "
                        "under rotation, content-addressed over the "
                        "rotation event sequence. An SMSH-style tier "
                        "trajectory is a superset-with-projection: "
                        "reduces to a scalar under an AGT-compatible "
                        "projection but carries richer evidence that "
                        "is not lost under the projection."
                    ),
                },
                "superset_with_projection_principle": (
                    "When one layer's representation can project to a "
                    "simpler shape a partner verifier expects, declare "
                    "the superset form and the projection explicitly. "
                    "Lossy projections between layer representations "
                    "are where silent divergence lives; an explicit "
                    "superset-with-projection avoids it. This is the "
                    "composition principle for every layer, not only "
                    "a one-off example — every future layer addition "
                    "should template safe downgrade this way."
                ),
                "projection_family_examples": [
                    {
                        "layer": "authority",
                        "superset": "delegation_chain_root (content-addressed chain)",
                        "projection": "AGT trust_score (scalar)",
                        "loses": "chain depth, per-hop scope narrowing, intermediate principals",
                    },
                    {
                        "layer": "continuity",
                        "superset": "rotation-attestation chain (ordered event sequence)",
                        "projection": "has_rotated: bool",
                        "loses": "rotation timing, migration_type, attestor identity",
                    },
                    {
                        "layer": "continuity",
                        "superset": "continuity receipts (trajectory over kid history)",
                        "projection": "last_seen_kid (scalar key identifier)",
                        "loses": "prior kids, rotation reasons, issuance timestamps",
                    },
                    {
                        "layer": "identity",
                        "superset": "multi-anchor resolution path (JWKS + DNS + WebPKI)",
                        "projection": "resolved_did (scalar identifier)",
                        "loses": "anchor diversity, federation trust tier, AGT metadata",
                    },
                ],
            },
            "error_codes": {
                "INVALID_CLAIM_SCOPE": {
                    "triggers_on": (
                        "Claim carries fields outside its declared "
                        "claim_category (e.g. identity-categorized "
                        "claim carrying authority-layer delegation)."
                    ),
                    "ordering": (
                        "Structural failure precedes semantic evaluation. "
                        "Fail-closed is mandatory before any layer-specific "
                        "logic runs."
                    ),
                    "test_vector": "scope_violation_vector (below)",
                },
                "INVALID_COMPOSITION": {
                    "triggers_on": (
                        "Well-typed claims at each layer cannot be combined "
                        "under the layer's composition rule (e.g. disjoint "
                        "authority scopes, broken rotation chain, unresolvable "
                        "identity-to-transport binding). Distinct from "
                        "INVALID_CLAIM_SCOPE — no per-claim scope violation "
                        "has occurred; the composition is what fails."
                    ),
                    "ordering": (
                        "Structural failure precedes semantic evaluation. "
                        "Same ordering constraint as INVALID_CLAIM_SCOPE."
                    ),
                    "test_vector": "composition_failure_vector (below)",
                },
            },
            "reserved_values": {
                "claim_category.envelope": {
                    "status": "reserved",
                    "committed_in": "v0.3.2 or v0.3.1 errata",
                    "composition_rule_variants": [
                        {
                            "name": "zero_knowledge_membership",
                            "use_when": (
                                "The envelope identity itself must stay "
                                "private from the verifier (envelope name "
                                "is sensitive, not just the member list)."
                            ),
                            "shape": (
                                "ZK proof of membership in the "
                                "attestation-registry snapshot, "
                                "content-addressed over the snapshot root."
                            ),
                        },
                        {
                            "name": "signed_snapshot_attestation",
                            "use_when": (
                                "The envelope is public; only the member "
                                "list is sensitive. Cheaper, no ZK runtime "
                                "dependency, still unlinkable across members."
                            ),
                            "shape": (
                                "Issuer signature over "
                                "{subject, registry_root, "
                                "asserted_membership: true} where "
                                "registry_root is the content-addressed "
                                "snapshot identifier at attestation time."
                            ),
                        },
                    ],
                    "note": (
                        "Fifth-layer regulatory-envelope attestation "
                        "(Hive Civilization contribution). Implementations "
                        "pick by privacy requirement: ZK for private "
                        "envelope identity, signed-snapshot when only the "
                        "member list needs unlinkability. Both variants "
                        "will be named in the v0.3.2 normative rule table. "
                        "APS (aeoess/agent-passport-system) has committed "
                        "to adopting the same claim_category value in "
                        "adapter mappings when it lands. "
                        "Specification forthcoming."
                    ),
                },
                "evidence_basis.evidence_type.payment_execution": {
                    "status": "reserved",
                    "committed_in": "v0.3.2 or v0.3.1 errata",
                    "note": (
                        "Payment-execution receipt as an independent "
                        "signal type (HiveCompute x402 contribution). "
                        "Answers 'consideration was exchanged' — "
                        "distinct from 'task result matches spec' (SAR). "
                        "Expected fields: eip3009_authorization_hash, "
                        "base_tx_hash, wallet_did, amount_usdc, issued_at. "
                        "Specification forthcoming."
                    ),
                },
            },
            "envelope_vector": {
                "note": (
                    "Example CTEF v0.3.1 TrustAttestation envelope "
                    "(claim_category=authority) with delegation_chain_root "
                    "composition per §4.6. A partner verifier MUST "
                    "reproduce canonical_bytes_utf8 and canonical_sha256 "
                    "exactly; divergence indicates a canonicalizer drift "
                    "that would break bilateral composition."
                ),
                "input_object": _CTE_ENVELOPE_EXAMPLE,
                "canonical_bytes_utf8": envelope_bytes.decode("utf-8"),
                "canonical_sha256": envelope_sha,
                "expected_result": "pass",
            },
            "verdict_vector": {
                "note": (
                    "Example CTEF v0.3.1 EnforcementVerdict with the "
                    "5-dimension claim-model surface per §6.3 (action, "
                    "evidence_basis, admissibility_result, validity_window, "
                    "forwardability). A partner that consumes AgentGraph "
                    "verdicts should verify canonical_sha256 matches what "
                    "they compute locally."
                ),
                "input_object": _CTE_VERDICT_EXAMPLE,
                "canonical_bytes_utf8": verdict_bytes.decode("utf-8"),
                "canonical_sha256": verdict_sha,
                "expected_result": "pass",
            },
            "scope_violation_vector": {
                "note": (
                    "Negative-path vector (v0.3.1). Envelope declares "
                    "claim_category='identity' but carries authority-layer "
                    "delegation fields. A conformant verifier MUST reject "
                    "with INVALID_CLAIM_SCOPE before semantic evaluation "
                    "— structural failure precedes any layer-specific "
                    "logic. Canonical bytes are reproducible; the "
                    "expected_result is fail-closed, not pass."
                ),
                "input_object": _CTE_SCOPE_VIOLATION_EXAMPLE,
                "canonical_bytes_utf8": scope_violation_bytes.decode("utf-8"),
                "canonical_sha256": scope_violation_sha,
                "expected_result": "fail-closed",
                "expected_error_code": "INVALID_CLAIM_SCOPE",
            },
            "composition_failure_vector": {
                "note": (
                    "Negative-path vector (v0.3.1). Two authority-layer "
                    "delegation chains with disjoint scopes "
                    "(feed:write vs marketplace:buy). Monotonic narrowing "
                    "produces an empty intersection, so a conformant "
                    "verifier MUST reject with INVALID_COMPOSITION before "
                    "semantic evaluation. Canonical bytes are reproducible; "
                    "the expected_result is fail-closed, not pass."
                ),
                "input_object": _CTE_COMPOSITION_FAILURE_EXAMPLE,
                "canonical_bytes_utf8": composition_failure_bytes.decode("utf-8"),
                "canonical_sha256": composition_failure_sha,
                "expected_result": "fail-closed",
                "expected_error_code": "INVALID_COMPOSITION",
            },
        },
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/.well-known/agent-trust.json")
async def agent_trust() -> JSONResponse:
    """Domain verification for Open Agent Trust Registry (OATR).

    CI at FransDevelopment/open-agent-trust-registry fetches this to verify
    domain ownership during issuer registration.
    """
    return JSONResponse(
        content={
            "issuer_id": _OATR_ISSUER_ID,
            "public_key_fingerprint": _OATR_PUBLIC_KEY,
        },
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )
