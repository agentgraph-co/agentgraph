"""Regression test for /.well-known/webhook-test-vectors.json.

Partners (MoltBridge, Verascore, ...) reproduce the HMAC locally from
this document and compare byte-for-byte. If the canonical form or
signature drifts without the contract version bumping, partners break
silently. Pin the expected signature.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json


def test_webhook_test_vectors_reproducible():
    from src.api.jwks_router import webhook_test_vectors

    resp = asyncio.run(webhook_test_vectors())
    doc = json.loads(resp.body)

    assert doc["version"] == "1.0"
    assert doc["event"] == "scan-change"

    # Canonicalization spec must not drift.
    assert doc["contract"]["signature_algorithm"] == "HMAC-SHA256"
    assert doc["contract"]["signature_header"] == "X-Partner-Signature"
    assert doc["contract"]["timestamp_header"] == "X-Partner-Timestamp"

    # Reproduce the canonical bytes + HMAC from the published body +
    # shared_secret. Must match the published signature exactly — a
    # partner running the same code locally depends on this.
    tv = doc["test_vector"]
    body_obj = tv["body_object"]
    secret = tv["shared_secret"].encode("utf-8")

    canonical = json.dumps(body_obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    assert canonical.decode("utf-8") == tv["canonical_bytes_utf8"]

    mac = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    assert mac == tv["expected_signature_hex"]
    assert tv["expected_headers"]["X-Partner-Signature"] == f"sha256={mac}"
    assert tv["expected_headers"]["X-AgentGraph-Event"] == "scan-change"
