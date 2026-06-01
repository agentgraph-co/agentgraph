"""SDK client-side envelope verification (#118).

The load-bearing guarantee: the SDK's standalone verifier accepts envelopes the
SERVER signs (cross-compatibility), rejects tampering, and flags staleness — so
a consumer can trust the score without trusting our server.
"""
from __future__ import annotations

import base64
import os
import sys
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.trust.envelope_v2 import Contribution, build_envelope, sign_envelope

# SDK is a separate package under sdk/ — put it on path before importing it.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))

from agentgraph_sdk.verify import verify_envelope  # noqa: E402, I001


def _jwks_for(priv: Ed25519PrivateKey, kid: str) -> dict:
    raw = priv.public_key().public_bytes_raw()
    x = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return {"keys": [{"kty": "OKP", "crv": "Ed25519", "x": x, "kid": kid, "alg": "EdDSA"}]}


def _signed(priv, kid="trust-v2-2026", computed_at=None):
    unsigned = build_envelope(
        subject_did="did:web:agent.example",
        subject_kind="agent",
        contributions=[Contribution(
            source="scan_corpus", raw_signal=0.8,
            weighted_contribution=0.8, freshness_ttl_seconds=3600,
        )],
        computed_at=computed_at,
    )
    return sign_envelope(unsigned, priv, f"did:web:agentgraph.co#{kid}")


def test_sdk_verifies_server_signed_envelope():
    priv = Ed25519PrivateKey.generate()
    env = _signed(priv)
    res = verify_envelope(env, _jwks_for(priv, "trust-v2-2026"))
    assert res.valid is True
    assert res.signature_valid and res.fresh
    assert res.kid == "trust-v2-2026"
    assert bool(res) is True  # __bool__


def test_sdk_rejects_tampered_score():
    priv = Ed25519PrivateKey.generate()
    env = _signed(priv)
    env["trust_score"] = 0.99  # tamper after signing
    res = verify_envelope(env, _jwks_for(priv, "trust-v2-2026"))
    assert res.valid is False
    assert res.signature_valid is False


def test_sdk_rejects_stale_envelope():
    priv = Ed25519PrivateKey.generate()
    old = datetime.now(timezone.utc) - timedelta(hours=2)  # ttl is 3600s
    env = _signed(priv, computed_at=old)
    res = verify_envelope(env, _jwks_for(priv, "trust-v2-2026"))
    assert res.signature_valid is True   # signature still valid
    assert res.fresh is False
    assert res.valid is False            # but stale → not valid


def test_sdk_rejects_unknown_kid():
    priv = Ed25519PrivateKey.generate()
    env = _signed(priv, kid="trust-v2-2026")
    res = verify_envelope(env, _jwks_for(priv, "some-other-kid"))
    assert res.valid is False
    assert "no matching key" in res.reason


def test_sdk_rejects_wrong_key():
    priv = Ed25519PrivateKey.generate()
    other = Ed25519PrivateKey.generate()
    env = _signed(priv, kid="trust-v2-2026")
    res = verify_envelope(env, _jwks_for(other, "trust-v2-2026"))  # right kid, wrong key
    assert res.valid is False
    assert res.signature_valid is False
