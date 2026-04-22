"""Regression tests for the public did:web document at /.well-known/did.json.

The document is referenced as the verification anchor for AgentGraph
attestations (JWS, CTEF outer envelope) and as the ``aud`` target of CTEF
envelopes (``#gateway-reverify``). Partners rely on it; a silent
schema regression would break cross-provider verification.
"""
from __future__ import annotations

import asyncio
import json


def test_did_document_has_verification_and_gateway_service():
    from src.feeds.bluesky.feed_router import did_document

    resp = asyncio.run(did_document())
    doc = json.loads(resp.body)

    assert doc["id"].startswith("did:web:")

    # verificationMethod must publish an Ed25519 JWK for attestation verification.
    vms = doc["verificationMethod"]
    assert len(vms) >= 1
    vm = vms[0]
    assert vm["type"] == "JsonWebKey2020"
    assert vm["controller"] == doc["id"]
    assert vm["id"].startswith(doc["id"] + "#")
    jwk = vm["publicKeyJwk"]
    assert jwk["kty"] == "OKP"
    assert jwk["crv"] == "Ed25519"
    assert jwk["alg"] == "EdDSA"
    assert jwk["use"] == "sig"
    assert jwk.get("x")
    assert jwk.get("kid")

    # assertionMethod / authentication must reference the publishing VM.
    assert vm["id"] in doc["assertionMethod"]
    assert vm["id"] in doc["authentication"]

    # #gateway-reverify service must be present — this is the CTEF aud target.
    svc_ids = {s["id"] for s in doc["service"]}
    assert f"{doc['id']}#gateway-reverify" in svc_ids
    gw = next(s for s in doc["service"] if s["id"].endswith("#gateway-reverify"))
    assert gw["serviceEndpoint"].endswith("/api/v1/gateway/re-verify")
    assert gw["type"] == "TrustGatewayReverify"

    # Bluesky feed generator service preserved.
    assert f"{doc['id']}#bsky_fg" in svc_ids

    # JWKS convenience service.
    assert f"{doc['id']}#jwks" in svc_ids
