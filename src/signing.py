"""Ed25519 signing key management for attestation payloads.

AgentGraph signs security attestations as a platform-level issuer.
The private key is loaded from ATTESTATION_SIGNING_KEY_ED25519 (base64
encoded 32-byte seed).  In debug mode a transient key is generated if
the env var is absent.

Payload canonicalization follows JCS (RFC 8785): sorted keys, no
whitespace, integer-valued floats without decimal (1.0 → 1), null
values stripped.  This ensures byte-identical serialization across
Python and TypeScript runtimes.
"""
from __future__ import annotations

import base64
import json
import logging
import math

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


def canonicalize(payload: dict) -> bytes:
    """Serialize *payload* to canonical JSON bytes (JCS-compatible).

    Sorted keys, no whitespace, integer-valued floats without decimal,
    null values stripped.  Matches APS interop fixtures for cross-language
    verification (Python json.dumps(1.0)='1.0' vs JS JSON.stringify(1.0)='1').
    """
    cleaned = _normalize_for_jcs(payload)
    return json.dumps(
        cleaned, sort_keys=True, separators=(",", ":"),
    ).encode()


def _normalize_for_jcs(obj: object) -> object:
    """Recursively normalize a Python object for JCS serialization.

    - Strip keys with None values
    - Convert integer-valued floats to int (1.0 → 1)
    - Reject Inf/NaN
    """
    if isinstance(obj, dict):
        return {
            k: _normalize_for_jcs(v) for k, v in obj.items() if v is not None
        }
    if isinstance(obj, list):
        return [_normalize_for_jcs(item) for item in obj]
    if isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            raise ValueError(f"Cannot canonicalize {obj}")
        if obj == int(obj):
            return int(obj)
    return obj


def canonicalize_jcs_strict(payload: object) -> bytes:
    """Serialize *payload* to RFC 8785 (JCS) canonical JSON bytes.

    Unlike ``canonicalize()`` (legacy AgentGraph path that strips nulls
    and uses ASCII-only escapes), this function is byte-identical to
    RFC 8785 JCS on the subset exercised by the APS bilateral-delegation
    fixture at ``aeoess/agent-passport-system/fixtures/bilateral-delegation``:

    - Keys sorted by Unicode code point (``sort_keys=True``).
    - ``None`` values **preserved** (not stripped) at every depth.
    - Non-ASCII characters emitted as literal UTF-8 bytes
      (``ensure_ascii=False``), not ``\\uXXXX`` escapes.
    - Integer-valued floats normalized to int (``1.0`` → ``1``) to match
      ECMA-262 number serialization.
    - Inf/NaN rejected.

    Used by CTEF (Composable Trust Evidence Format, A2A#1734) envelopes
    where ``delegation_chain_root`` composition requires byte-for-byte
    agreement with APS. **Do not** use for legacy signed attestations —
    the original ``canonicalize()`` is preserved verbatim so previously
    signed payloads keep verifying.
    """
    cleaned = _normalize_for_jcs_strict(payload)
    return json.dumps(
        cleaned, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def _normalize_for_jcs_strict(obj: object) -> object:
    """Like ``_normalize_for_jcs`` but preserves ``None`` values.

    RFC 8785 §3.2.1 makes no provision for stripping null; ``null`` is a
    valid JSON primitive and must survive canonicalization.
    """
    if isinstance(obj, dict):
        return {k: _normalize_for_jcs_strict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_for_jcs_strict(item) for item in obj]
    if isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            raise ValueError(f"Cannot canonicalize {obj}")
        if obj == int(obj):
            return int(obj)
    return obj


def create_jws(payload_bytes: bytes) -> str:
    """Return a compact JWS (RFC 7515) string: header.payload.signature.

    The signing input is ``header_b64 + "." + payload_b64`` (ASCII bytes).
    This avoids canonical-JSON ambiguity across languages — the payload
    bytes are preserved exactly as provided.
    """
    header = b'{"alg":"EdDSA","kid":"' + KID.encode() + b'"}'
    h_b64 = _b64url(header)
    p_b64 = _b64url(payload_bytes)
    signing_input = (h_b64 + "." + p_b64).encode()
    sig = get_signing_key().sign(signing_input)
    return h_b64 + "." + p_b64 + "." + _b64url(sig)
