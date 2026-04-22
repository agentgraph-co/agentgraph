"""JWKS and well-known endpoints for AgentGraph's cryptographic identity."""
from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.signing import get_jwk

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
