"""Ed25519 signing key management for attestation payloads.

AgentGraph signs security attestations as a platform-level issuer.
The private key is loaded from ATTESTATION_SIGNING_KEY_ED25519 (base64
encoded 32-byte seed).  In debug mode a transient key is generated if
the env var is absent.
"""
from __future__ import annotations

import base64
import logging

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from src.config import settings

logger = logging.getLogger(__name__)

KID = "agentgraph-security-v1"

_private_key: Ed25519PrivateKey | None = None


def _b64url(data: bytes) -> str:
    """Base64url-encode without padding (RFC 7515 §2)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def get_signing_key() -> Ed25519PrivateKey:
    """Return the platform Ed25519 private key (singleton)."""
    global _private_key
    if _private_key is not None:
        return _private_key

    raw = getattr(settings, "attestation_signing_key_ed25519", None)
    if raw:
        seed = base64.b64decode(raw)
        _private_key = Ed25519PrivateKey.from_private_bytes(seed)
        logger.info("Loaded attestation signing key from env")
    elif settings.debug:
        _private_key = Ed25519PrivateKey.generate()
        logger.warning("Generated transient attestation signing key (debug mode)")
    else:
        raise RuntimeError(
            "ATTESTATION_SIGNING_KEY_ED25519 must be set in production"
        )
    return _private_key


def get_public_key() -> Ed25519PublicKey:
    """Return the platform Ed25519 public key."""
    return get_signing_key().public_key()


def get_jwk() -> dict:
    """Return the public key as a JWK dict (RFC 7517 / RFC 8037)."""
    pub = get_public_key()
    raw_pub = pub.public_bytes_raw()
    return {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": _b64url(raw_pub),
        "kid": KID,
        "use": "sig",
        "alg": "EdDSA",
    }


def sign_payload(payload_bytes: bytes) -> bytes:
    """Sign *payload_bytes* with Ed25519, return 64-byte raw signature."""
    return get_signing_key().sign(payload_bytes)
