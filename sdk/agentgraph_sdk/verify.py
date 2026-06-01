"""Client-side verification of AgentGraph Trust Score v2 envelopes.

The point of the signed envelope: a consumer can verify a trust score WITHOUT
trusting AgentGraph's server. This module reproduces the exact verification the
server does (JCS-canonical, proof-stripped, Ed25519 over a SHA-256 digest),
standalone — it only needs ``rfc8785`` + ``cryptography``, not any AgentGraph
server code.

Spec: docs/standards/trust-score-envelope-v2.0.md (§6 verification).
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PROOF_TYPE = "Ed25519Signature2020"


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of verifying a signed trust-score envelope.

    ``valid`` is the bottom line (signature good AND within freshness window).
    The component fields explain a failure.
    """

    valid: bool
    signature_valid: bool
    fresh: bool
    kid: str | None = None
    reason: str = "ok"

    def __bool__(self) -> bool:
        return self.valid


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _strip_proof(envelope: dict) -> dict:
    return {k: v for k, v in envelope.items() if k != "proof"}


def envelope_digest(envelope: dict) -> bytes:
    """SHA-256 of the JCS-canonical, proof-stripped envelope (what proof.jws signs)."""
    return hashlib.sha256(rfc8785.dumps(_strip_proof(envelope))).digest()


def _kid_from_jws(jws: str) -> str | None:
    try:
        header = jws.split(".", 1)[0]
        import json

        return json.loads(_b64url_decode(header)).get("kid")
    except Exception:
        return None


def _public_key_for_kid(jwks: dict | list, kid: str | None) -> Ed25519PublicKey | None:
    """Resolve an Ed25519 public key from a JWKS (RFC 7517) by kid.

    ``jwks`` may be the full ``{"keys": [...]}`` doc or a bare list of JWKs.
    If ``kid`` is None, the first OKP/Ed25519 key is used.
    """
    keys = jwks.get("keys", []) if isinstance(jwks, dict) else jwks
    candidates = [
        k for k in keys
        if k.get("kty") == "OKP" and k.get("crv") == "Ed25519" and "x" in k
    ]
    if kid is not None:
        for k in candidates:
            if k.get("kid") == kid:
                return Ed25519PublicKey.from_public_bytes(_b64url_decode(k["x"]))
        return None
    if candidates:
        return Ed25519PublicKey.from_public_bytes(_b64url_decode(candidates[0]["x"]))
    return None


def is_fresh(envelope: dict, *, now: datetime | None = None) -> bool:
    """True iff the envelope is within its ``freshness_ttl_seconds`` window."""
    now = now or datetime.now(timezone.utc)
    try:
        computed = datetime.fromisoformat(envelope["computed_at"].replace("Z", "+00:00"))
        ttl = int(envelope.get("freshness_ttl_seconds", 0))
    except (KeyError, ValueError):
        return False
    return (now - computed).total_seconds() <= ttl


def verify_envelope(
    envelope: dict, jwks: dict | list, *, now: datetime | None = None
) -> VerificationResult:
    """Verify a signed v2 trust-score envelope against a JWKS.

    Fetch the JWKS once from ``<issuer>/.well-known/jwks.json`` (or use the
    client's ``verify()`` which does it for you). Returns a
    :class:`VerificationResult`; truthy iff signature valid AND fresh.
    """
    proof = envelope.get("proof")
    if not proof or proof.get("type") != PROOF_TYPE:
        return VerificationResult(False, False, False, reason="missing or unsupported proof")
    jws = proof.get("jws", "")
    parts = jws.split(".")
    if len(parts) != 3:
        return VerificationResult(False, False, False, reason="malformed jws")

    kid = _kid_from_jws(jws)
    pub = _public_key_for_kid(jwks, kid)
    if pub is None:
        return VerificationResult(False, False, False, kid=kid, reason="no matching key in JWKS")

    try:
        pub.verify(_b64url_decode(parts[2]), envelope_digest(envelope))
        sig_ok = True
    except (InvalidSignature, ValueError):
        sig_ok = False

    fresh = is_fresh(envelope, now=now)
    if not sig_ok:
        return VerificationResult(False, False, fresh, kid=kid, reason="signature invalid")
    if not fresh:
        return VerificationResult(False, True, False, kid=kid, reason="envelope expired (stale)")
    return VerificationResult(True, True, True, kid=kid, reason="ok")


__all__ = ["VerificationResult", "verify_envelope", "is_fresh", "envelope_digest"]
