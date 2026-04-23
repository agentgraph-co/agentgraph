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
    "version": "0.3.0",
    "provider": {
        "id": "did:web:agentgraph.co",
        "name": "AgentGraph Trust Scanner",
        "category": "static_analysis",
        "version": "0.3.0",
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

_CTE_VERDICT_EXAMPLE = {
    "type": "EnforcementVerdict",
    "version": "0.3.0",
    "gateway": {
        "id": "did:web:agentgraph.co#gateway",
        "name": "AgentGraph Trust Gateway",
        "version": "0.3.0",
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

    envelope_sha = hashlib.sha256(envelope_bytes).hexdigest()
    verdict_sha = hashlib.sha256(verdict_bytes).hexdigest()

    return JSONResponse(
        content={
            "version": "0.3.0",
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
                "reference_fixture": (
                    "aeoess/agent-passport-system/fixtures/bilateral-delegation/"
                    "canonicalize-fixture-v1.json "
                    "— 10 JCS vectors; AgentGraph passes 10/10 byte-exact."
                ),
                "rfc": (
                    "See docs/internal/rfc-evidence-format-v1.md in "
                    "agentgraph-co/agentgraph for the full CTEF v0.3 spec."
                ),
            },
            "envelope_vector": {
                "note": (
                    "Example CTEF v0.3 TrustAttestation envelope with "
                    "delegation_chain_root composition per §4.6. A partner "
                    "verifier MUST reproduce canonical_bytes_utf8 and "
                    "canonical_sha256 exactly; divergence indicates a "
                    "canonicalizer drift that would break bilateral composition."
                ),
                "input_object": _CTE_ENVELOPE_EXAMPLE,
                "canonical_bytes_utf8": envelope_bytes.decode("utf-8"),
                "canonical_sha256": envelope_sha,
            },
            "verdict_vector": {
                "note": (
                    "Example CTEF v0.3 EnforcementVerdict with the 5-dimension "
                    "claim-model surface per §6.3 (action, evidence_basis, "
                    "admissibility_result, validity_window, forwardability). "
                    "A partner that consumes AgentGraph verdicts should verify "
                    "canonical_sha256 matches what they compute locally."
                ),
                "input_object": _CTE_VERDICT_EXAMPLE,
                "canonical_bytes_utf8": verdict_bytes.decode("utf-8"),
                "canonical_sha256": verdict_sha,
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
