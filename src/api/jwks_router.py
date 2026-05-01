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
    "claim_type": "authority",
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
# Envelope declares claim_type="identity" but carries authority-layer
# fields (delegation). A conformant verifier MUST return
# INVALID_CLAIM_SCOPE before any semantic evaluation.
_CTE_SCOPE_VIOLATION_EXAMPLE = {
    "@context": [
        "https://www.w3.org/ns/credentials/v2",
        "https://agentgraph.co/ns/trust-evidence/v1",
    ],
    "type": "TrustAttestation",
    "version": "0.3.1",
    "claim_type": "identity",
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
    "claim_type": "authority",
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
                "claim_type": {
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
                        "claim_type (e.g. identity-categorized "
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
                "claim_type.envelope": {
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
                        "to adopting the same claim_type value in "
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
                    "(claim_type=authority) with delegation_chain_root "
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
                    "claim_type='identity' but carries authority-layer "
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


@router.get("/.well-known/interop-harness.json")
async def interop_harness() -> JSONResponse:
    """Consolidated CTEF v0.3.1 byte-match interop harness state.

    Single artifact summarizing every implementation that has byte-match
    validated against the published test vectors. Requested by aeoess for
    A2A WG #1786 sponsorship readiness — partners and maintainers can
    fetch one URL to see the full cross-implementation harness state.

    Updated whenever a new implementation byte-match-validates.
    """
    return JSONResponse(
        content={
            "spec": "CTEF (Composable Trust Evidence Format)",
            "spec_version": "0.3.1",
            "spec_anchor": "https://agentgraph.co/.well-known/cte-test-vectors.json",
            "wg_proposal": "https://github.com/a2aproject/A2A/issues/1786",
            "as_of": "2026-05-01",
            "evidence_taxonomy": {
                "substrate": (
                    "JCS canonicalizer byte-match across independent "
                    "implementations on signed fixtures. Multi-source-proven "
                    "as of 2026-05-01 via 8 independent canonicalizers + 2 "
                    "publicly-runnable verification scripts (Nobulex "
                    "verify-aps-byte-match.mjs + verify-ctef-byte-match.mjs)."
                ),
                "verifier_conformance": (
                    "claim_type discrimination, composition contracts, "
                    "negative-path semantics. Per-implementation work that "
                    "lands per role-taxonomy slot. Citation-graph framing "
                    "from msaleme (A2A #1786, 2026-04-30) — substrate and "
                    "verifier conformance are separable evidence categories."
                ),
                "reproducibility": (
                    "Anyone-can-clone reproducibility added 2026-04-30 via "
                    "Nobulex scripts that pull APS + CTEF fixtures from "
                    "their canonical sources, run through @nobulex/crypto, "
                    "compare SHA-256 against expected hashes, and emit "
                    "verification receipts. Lifts the substrate-evidence "
                    "claim from 'stated and validated' to 'reader-runnable.' "
                    "On 2026-05-01, APS independently re-ran both scripts "
                    "and posted PASS receipts (10/10 + 4/4 incl negative-"
                    "path) mirrored at aeoess/aps-conformance-suite/cross-"
                    "impl-receipts/ — substrate evidence now lives in two "
                    "independent repos with no maintainer re-run dependency."
                ),
            },
            "role_taxonomy": {
                "evidence_provider": (
                    "Issues claim_type-tagged attestations against the CTEF "
                    "envelope; produces JCS-canonicalized signed evidence; "
                    "appears as the upstream signer in a verifier's trust "
                    "chain."
                ),
                "enforcement_gateway": (
                    "Evaluation-only: receives evidence bundles, evaluates "
                    "against policy, returns JWS-signed verdicts (certified "
                    "true/false + attestation). No evidence emission, no "
                    "canonicalization dependency. Verifies existing proofs "
                    "and issues policy decisions only — does not re-sign or "
                    "re-canonicalize. Sits downstream of evidence providers. "
                    "Per arkforge framing, A2A #1734 comment 2026-04-30."
                ),
                "substrate_verifier": (
                    "Independent canonicalizer + fixture-validation runner "
                    "with no implementation overlap with the providers it "
                    "verifies. Reproduces SHA-256s without issuing or "
                    "evaluating evidence. Closes the 'everyone running the "
                    "same canonicalizer library' objection for sponsorship "
                    "review weighting."
                ),
            },
            "implementations": [
                {
                    "name": "AgentGraph",
                    "maintainer": "@kenneives",
                    "language": "Python",
                    "role": "evidence_provider",
                    "bilateral_delegation_byte_match": "10/10",
                    "rotation_attestation_byte_match": "5/5 (live-fetch)",
                    "claim_type_live": True,
                    "claim_type_endpoint": (
                        "https://agentgraph.co/.well-known/cte-test-vectors.json"
                    ),
                    "test_files": [
                        "tests/test_jcs_canonicalize_aps_interop.py",
                        "tests/test_aps_rotation_attestation_interop.py",
                        "tests/test_cte_test_vectors.py",
                    ],
                },
                {
                    "name": "Agent Passport System (APS)",
                    "maintainer": "@aeoess",
                    "language": "Python",
                    "role": "evidence_provider",
                    "bilateral_delegation_byte_match": (
                        "publishes the fixture set"
                    ),
                    "rotation_attestation_byte_match": (
                        "publishes the fixture set"
                    ),
                    "claim_type_live": True,
                    "fixture_repo": (
                        "https://github.com/aeoess/agent-passport-system"
                    ),
                },
                {
                    "name": "AgentID",
                    "maintainer": "@haroldmalikfrimpong-ops",
                    "language": "Python",
                    "role": "evidence_provider",
                    "bilateral_delegation_byte_match": "10/10 (32/32 tests)",
                    "rotation_attestation_byte_match": None,
                    "claim_type_live": True,
                    "claim_type_endpoint": (
                        "https://getagentid.dev/api/v1/agents/verify"
                    ),
                },
                {
                    "name": "@nobulex/crypto",
                    "maintainer": "@arian-gogani",
                    "language": "TypeScript",
                    "role": "evidence_provider",
                    "bilateral_delegation_byte_match": "10/10",
                    "ctef_inline_byte_match": (
                        "4/4 SHA-256-exact including both negative-path "
                        "vectors (INVALID_CLAIM_SCOPE, INVALID_COMPOSITION) "
                        "— A2A #1786 comment 2026-04-30"
                    ),
                    "rotation_attestation_byte_match": "verifier testing in flight",
                    "claim_type_live": False,
                    "package": "@nobulex/crypto (npm)",
                    "merged_into": (
                        "Microsoft Agent Governance Toolkit "
                        "(microsoft/agent-governance-toolkit#1333, "
                        "OpenSSF passing badge, 2026-04 week)"
                    ),
                    "reproducibility_scripts": {
                        "aps_bilateral_delegation": (
                            "https://github.com/arian-gogani/nobulex/blob/main/"
                            "scripts/verify-aps-byte-match.mjs"
                        ),
                        "ctef_v031_inline": (
                            "https://github.com/arian-gogani/nobulex/blob/main/"
                            "scripts/verify-ctef-byte-match.mjs"
                        ),
                        "receipt_artifacts": (
                            "aps-byte-match-receipt.json + "
                            "ctef-byte-match-receipt.json in repo root"
                        ),
                        "instructions": (
                            "Anyone can clone arian-gogani/nobulex and run "
                            "`node scripts/verify-aps-byte-match.mjs` and "
                            "`node scripts/verify-ctef-byte-match.mjs` to "
                            "reproduce 10/10 APS + 4/4 CTEF byte-match "
                            "without any AgentGraph or APS code path"
                        ),
                    },
                    "aaif_filing": (
                        "aaif/project-proposals#20 (Nobulex, filed "
                        "2026-04-30) — Growth-stage proposal positioning "
                        "Nobulex bilateral-receipt primitive as accountability "
                        "infrastructure layered on the CTEF substrate; cites "
                        "AgentGraph as harness maintainer + 8 byte-match "
                        "implementations as cross-organization adoption proof"
                    ),
                },
                {
                    "name": "HiveTrust",
                    "maintainer": "@srotzin",
                    "language": "Python",
                    "role": "evidence_provider",
                    "inline_vector_byte_match": (
                        "4/4 byte-exact + SHA-256-exact (envelope, verdict, "
                        "scope_violation, composition_failure) — A2A #1786 "
                        "comment 2026-04-28"
                    ),
                    "bilateral_delegation_byte_match": (
                        "alignment confirmed; APS bilateral-delegation + "
                        "rotation-attestation runs queued"
                    ),
                    "rotation_attestation_byte_match": "queued",
                    "claim_type_live": True,
                    "verifier_url": (
                        "https://hive-gamification.onrender.com/v1/compliance/verify/{attestation_id}"
                    ),
                    "ed25519_pubkey": (
                        "12de746d51fca019c5c64685f2688a0e4a57ab532f6f6c67d44494de43f4c408"
                    ),
                    "schema_url": "https://hivemorph.onrender.com/openapi.json",
                },
                {
                    "name": "ArkForge Trust Layer",
                    "maintainer": "@desiorac",
                    "language": "Python",
                    "role": "enforcement_gateway",
                    "inline_vector_byte_match": (
                        "4/4 byte-exact (canonical + SHA-256) — qntm#7 PR #14, "
                        "2026-04-30"
                    ),
                    "constraint_evaluation_vectors": (
                        "3 scenarios delivered (within-limit delta=250, "
                        "near-miss delta=5, exceeded delta=-150) — facet/limit/"
                        "actual/delta shape from corpollc/qntm#6"
                    ),
                    "claim_type_live": True,
                    "did": "did:web:trust.arkforge.tech",
                    "verifier_url": "https://trust.arkforge.tech/v1/proxy",
                    "self_verification_script": (
                        "specs/test-vectors/verify_execution_attestation_arkforge.py"
                    ),
                },
                {
                    "name": "msaleme clean-room canonicalizer",
                    "maintainer": "@msaleme",
                    "language": "Python",
                    "role": "substrate_verifier",
                    "canonicalizer": "trailofbits/rfc8785.py v0.1.4",
                    "byte_match_aggregate": (
                        "19/19 byte-exact + SHA-256-exact across three fixture "
                        "sources: AgentGraph CTEF v0.3.1 inline (4/4), APS "
                        "bilateral-delegation (10/10), APS rotation-attestation "
                        "(5/5) — A2A #1786 comment 2026-04-30"
                    ),
                    "implementation_independence": (
                        "Zero implementation overlap with AgentGraph / APS / "
                        "AgentID / Nobulex / HiveTrust — closes the 'everyone "
                        "running the same canonicalizer library' objection"
                    ),
                    "verifier_reference_artifact": (
                        "~150 lines of Python over rfc8785.py; offered as "
                        "standalone WG-citation artifact"
                    ),
                    "claim_type_live": False,
                },
                {
                    "name": "Foxbook",
                    "maintainer": "@cloakmaster",
                    "language": "TypeScript",
                    "role": "evidence_provider",
                    "claim_type_layer": "identity",
                    "canonicalizer": "canonicalize@2.1.0 (erdtman RFC 8785 reference impl)",
                    "inline_vector_byte_match": (
                        "4/4 SHA-256-exact against agentgraph-co/agentgraph@69ad94d "
                        "— A2A #1672 comment 2026-04-30"
                    ),
                    "claim_type_live": True,
                    "did_method": "did:foxbook:{ULID}",
                    "transparency_log": "https://transparency.foxbook.dev",
                    "byte_match_report": (
                        "https://github.com/cloakmaster/foxbook/blob/9e392c5/"
                        "ops/evidence/2026-04-30-ctef-v0.3.1-byte-match.md"
                    ),
                    "wg_proposal": "A2A #1803",
                },
            ],
            "in_flight": [
                {
                    "name": "Vorim AI",
                    "maintainer": "@kwame",
                    "language": "TypeScript",
                    "ietf_draft": "draft-vorim-vaip-00",
                    "status": "byte-match validation in flight as 6th implementation",
                },
                {
                    "name": "Concordia",
                    "maintainer": "@erik-newton",
                    "language": "Python",
                    "status": (
                        "PR #10 to haroldmalikfrimpong-ops/agentid-aps-interop "
                        "approved with 131/131 checks; Concordia v1.0.0 fixtures + "
                        "verify.py repair"
                    ),
                },
                {
                    "name": "lawcontinue distributed-inference reference",
                    "maintainer": "@lawcontinue",
                    "status": (
                        "245-step sequence_bound case in coordination with APS for "
                        "v0.3.2 §6.3.1 worked example"
                    ),
                },
                {
                    "name": "msaleme x402 conformance harness (claim_type module)",
                    "maintainer": "@msaleme",
                    "status": (
                        "substrate-layer byte-match completed and promoted to "
                        "the implementations list (7th impl, substrate_verifier "
                        "role, 19/19 across three fixture sources via "
                        "trailofbits/rfc8785.py). Verifier-conformance work for "
                        "claim_type-tagged compliance scoped against the "
                        "experimental-ext repo once it opens for test-vector "
                        "contributions; delivery window not yet scoped. A2A "
                        "#1786 comment 2026-04-30"
                    ),
                },
                {
                    "name": "AEP (Agentic Exchange Protocol)",
                    "maintainer": "@Pineapples100",
                    "language": "spec draft",
                    "status": (
                        "T0–T3 trust tier model + /.well-known/aep-manifest.json "
                        "for org-level trust boundaries on SMTP/iCal/messaging "
                        "surfaces; tier-transition proofs would compose as "
                        "authority-layer claims in CTEF envelope; "
                        "https://github.com/pmyers-abundance/aep — A2A #1734 "
                        "comment 2026-04-30"
                    ),
                },
            ],
            "negative_path_vectors": {
                "scope_violation": {
                    "expected_error_code": "INVALID_CLAIM_SCOPE",
                    "purpose": (
                        "structural-before-semantic ordering — claim carrying "
                        "fields outside its declared claim_type MUST be rejected "
                        "before semantic evaluation"
                    ),
                },
                "composition_failure": {
                    "expected_error_code": "INVALID_COMPOSITION",
                    "purpose": (
                        "scope-narrowing-only invariant — child scope MUST NOT "
                        "expand parent scope; composition failure is fail-closed"
                    ),
                },
            },
            "summary": {
                "implementations_byte_match_validated": 8,
                "implementations_inline_vector_byte_match_validated": 5,
                "evidence_providers": 6,
                "enforcement_gateways": 1,
                "substrate_verifiers": 1,
                "languages": 2,
                "independent_canonicalizers": 8,
                "wg_proposal_phase": "Proposal Phase, awaiting maintainer sponsorship",
                "fail_closed_negative_paths": 2,
                "reader_runnable_verifiers": 2,
                "cross_repository_receipt_mirrors": 2,
            },
            "cross_validation_receipts": {
                "agentgraph_to_aps_via_nobulex": {
                    "verifier_repo": "https://github.com/arian-gogani/nobulex",
                    "verifier_script": "scripts/verify-aps-byte-match.mjs",
                    "fixture_source": (
                        "https://github.com/aeoess/agent-passport-system/blob/"
                        "main/fixtures/bilateral-delegation/"
                        "canonicalize-fixture-v1.json"
                    ),
                    "result": "10/10 PASS",
                    "third_party_rerun": (
                        "APS-side rerun 2026-05-01T16:59:33Z; receipt "
                        "mirrored at aeoess/aps-conformance-suite/cross-"
                        "impl-receipts/"
                    ),
                    "seed_sha256": (
                        "4f3d8defea1e82c1705c35d97ee4db046c6313ba83855a7d0de04a44f04c834a"
                    ),
                },
                "ctef_v031_via_nobulex": {
                    "verifier_repo": "https://github.com/arian-gogani/nobulex",
                    "verifier_script": "scripts/verify-ctef-byte-match.mjs",
                    "fixture_source": "https://agentgraph.co/.well-known/cte-test-vectors.json",
                    "fixture_version": "0.3.1",
                    "fixture_commit": "agentgraph-co/agentgraph@69ad94d",
                    "result": (
                        "4/4 PASS including both negative-path vectors "
                        "(INVALID_CLAIM_SCOPE, INVALID_COMPOSITION)"
                    ),
                    "third_party_rerun": (
                        "APS-side rerun 2026-05-01T17:03:08Z; receipt "
                        "mirrored at aeoess/aps-conformance-suite/cross-"
                        "impl-receipts/"
                    ),
                },
                "reciprocal_property": (
                    "@nobulex/crypto canonicalizeJson against APS-emitted "
                    "fixture produces byte-identical SHA-256 to APS SDK "
                    "canonicalizeJCS at every vector — substrate-layer "
                    "interop is proven symmetric, not just one-directional."
                ),
            },
        },
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )
