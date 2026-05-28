"""Normalize a raw ERC-8004 registry entry into a verified attestation.

Takes the `data` bytes from an `ERC8004Entry` (which carries a CTEF envelope),
parses the envelope, resolves the issuer's `did:web` to fetch Ed25519 public
keys, verifies the signature against the JCS-canonical preimage, and returns
a `NormalizedAttestation` ready for ingestion into the composite trust score.

The CTEF v0.3.1+ envelope shape this normalizer accepts:

    {
      "claim_type": "identity" | "transport" | "authority" | "continuity",
      "claim_subtype": <optional string>,
      "subject_did": "did:web:agent.example.com",
      "provider_did": "did:web:issuer.example.com",
      "issued_at": "<RFC 3339 timestamp>",
      "expires_at": "<RFC 3339 timestamp, optional>",
      "payload": { ... claim-specific fields ... },
      "signature": {
        "alg": "EdDSA",
        "kid": "<key id matching provider's published JWKS>",
        "sig": "<base64url-encoded Ed25519 signature>"
      }
    }

Verification preimage is JCS(envelope_without_signature) per CTEF v0.3.1.
Signing key resolution is by `kid` lookup in the provider's published JWKS
at `https://<did-web-domain>/.well-known/jwks.json`.

The normalizer treats signature verification as a HARD requirement — any
failure (malformed envelope, unreachable JWKS, kid not found, signature
mismatch) raises `NormalizationError`. Downstream score ingestion never
sees an unverified attestation.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

import httpx
import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from agentgraph_bridge_erc8004.models import ERC8004Entry, NormalizedAttestation

# Closed claim_type set per CTEF v0.3.1 §1.1
_VALID_CLAIM_TYPES = {"identity", "transport", "authority", "continuity"}

# Timeout for JWKS fetches. Short — the bridge is not in a hot path,
# and a slow JWKS endpoint should fail closed quickly rather than block
# the trust recompute job.
_JWKS_TIMEOUT_SECONDS = 10.0


class NormalizationError(ValueError):
    """Raised when an ERC-8004 entry can't be normalized to a verified attestation.

    Covers the full failure surface:
    - Malformed envelope (not JSON, missing required fields, invalid claim_type)
    - did:web resolution failure (invalid DID format, JWKS fetch error)
    - Signature verification failure (kid not found, alg mismatch, invalid sig)
    """


def _decode_b64url(s: str) -> bytes:
    """base64url decode with padding tolerance."""
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _parse_iso_timestamp(ts: str) -> datetime:
    """Parse an RFC 3339 timestamp into a tz-aware datetime."""
    # Handle both "Z" suffix and explicit "+00:00"
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _did_web_to_jwks_url(did: str) -> str:
    """Resolve a did:web identifier to its JWKS endpoint URL.

    did:web:example.com           → https://example.com/.well-known/jwks.json
    did:web:example.com:agent:x   → https://example.com/agent/x/jwks.json

    Per W3C DID did:web spec. Path segments after the domain become URL
    path components separated by `/`.
    """
    if not did.startswith("did:web:"):
        raise NormalizationError(
            f"Provider DID must use did:web method, got: {did!r}",
        )
    rest = did[len("did:web:"):]
    if not rest:
        raise NormalizationError(f"Empty did:web identifier: {did!r}")

    parts = rest.split(":")
    domain = parts[0]
    if not domain:
        raise NormalizationError(f"Empty domain in did:web: {did!r}")

    if len(parts) == 1:
        # Bare domain → .well-known/jwks.json
        return f"https://{domain}/.well-known/jwks.json"

    # Path-form → /<path>/jwks.json
    path = "/".join(parts[1:])
    return f"https://{domain}/{path}/jwks.json"


def _fetch_jwks(jwks_url: str, http_client: httpx.Client | None = None) -> list[dict]:
    """Fetch + parse JWKS from a URL.

    Returns the `keys` array. Caller is responsible for filtering by kid.
    """
    own_client = http_client is None
    client = http_client or httpx.Client(timeout=_JWKS_TIMEOUT_SECONDS)
    try:
        resp = client.get(jwks_url, headers={"User-Agent": "agentgraph-erc8004/0.1"})
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        raise NormalizationError(f"JWKS fetch failed for {jwks_url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise NormalizationError(f"JWKS at {jwks_url} is not valid JSON: {exc}") from exc
    finally:
        if own_client:
            client.close()

    keys = data.get("keys")
    if not isinstance(keys, list):
        raise NormalizationError(
            f"JWKS at {jwks_url} missing 'keys' array",
        )
    return keys


def _find_ed25519_key(keys: list[dict], kid: str) -> Ed25519PublicKey:
    """Look up an Ed25519 public key by kid in a JWKS keys array.

    Returns a usable Ed25519PublicKey. Raises NormalizationError if:
    - kid not found
    - matched key is not Ed25519 (kty=OKP, crv=Ed25519)
    - public key bytes are malformed
    """
    matching = [k for k in keys if k.get("kid") == kid]
    if not matching:
        raise NormalizationError(f"kid {kid!r} not found in JWKS")

    jwk = matching[0]
    if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
        raise NormalizationError(
            f"Key kid={kid!r} is not Ed25519 "
            f"(got kty={jwk.get('kty')!r}, crv={jwk.get('crv')!r})",
        )

    x = jwk.get("x")
    if not isinstance(x, str):
        raise NormalizationError(f"Key kid={kid!r} missing 'x' (public key)")

    try:
        pubkey_bytes = _decode_b64url(x)
        return Ed25519PublicKey.from_public_bytes(pubkey_bytes)
    except (ValueError, Exception) as exc:
        raise NormalizationError(
            f"Key kid={kid!r} has malformed Ed25519 public bytes: {exc}",
        ) from exc


def _verify_envelope_signature(envelope: dict, pubkey: Ed25519PublicKey) -> None:
    """Verify Ed25519 signature on a CTEF envelope.

    Preimage is JCS(envelope_without_signature). Raises NormalizationError
    on any failure (invalid signature, malformed sig bytes).
    """
    sig_block = envelope.get("signature")
    if not isinstance(sig_block, dict):
        raise NormalizationError("Envelope missing 'signature' block")

    if sig_block.get("alg") != "EdDSA":
        raise NormalizationError(
            f"Unsupported signature alg: {sig_block.get('alg')!r} (expected EdDSA)",
        )

    sig_b64 = sig_block.get("sig")
    if not isinstance(sig_b64, str):
        raise NormalizationError("Envelope signature.sig missing or not a string")

    try:
        sig_bytes = _decode_b64url(sig_b64)
    except Exception as exc:
        raise NormalizationError(f"Malformed signature base64url: {exc}") from exc

    # Preimage: envelope minus signature, JCS-canonicalized
    preimage_obj = {k: v for k, v in envelope.items() if k != "signature"}
    preimage_bytes = rfc8785.dumps(preimage_obj)

    try:
        pubkey.verify(sig_bytes, preimage_bytes)
    except InvalidSignature as exc:
        raise NormalizationError("Ed25519 signature verification FAILED") from exc


def normalize(
    entry: ERC8004Entry,
    *,
    registry_signature_verified: bool = True,
    http_client: httpx.Client | None = None,
    freshness_ttl_seconds: int | None = None,
) -> NormalizedAttestation:
    """Normalize a raw ERC-8004 entry into a verified attestation.

    Args:
        entry: Raw entry from `ERC8004RegistryReader.read_entry()`.
        registry_signature_verified: Caller asserts the entry submitter's
            Ethereum-layer signature was verified on-chain. This is true
            by definition for entries returned from the registry (the
            chain enforces the submitter signature at write time). Pass
            False only when consuming entries via untrusted indexer paths.
        http_client: Optional shared httpx.Client for JWKS fetches.
            Pass one in for connection reuse across batch normalization.
        freshness_ttl_seconds: If set and the envelope has no `expires_at`,
            derive an implicit expiry of `issued_at + freshness_ttl_seconds`.

    Returns:
        NormalizedAttestation with both signature layers verified and
        the parsed CTEF payload populated. Caller should check
        `.is_admissible` before feeding into the composite trust score.

    Raises:
        NormalizationError on any verification failure.
    """
    source_urn = f"urn:erc8004:{entry.registry.value}:{entry.entry_id}"

    # Step 1: decode `data` bytes as UTF-8 JSON
    try:
        raw_text = entry.data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NormalizationError(
            f"{source_urn}: entry data is not valid UTF-8: {exc}",
        ) from exc

    try:
        envelope = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise NormalizationError(
            f"{source_urn}: entry data is not valid JSON: {exc}",
        ) from exc

    if not isinstance(envelope, dict):
        raise NormalizationError(
            f"{source_urn}: envelope must be a JSON object, got {type(envelope).__name__}",
        )

    # Step 2: validate required envelope fields
    claim_type = envelope.get("claim_type")
    if claim_type not in _VALID_CLAIM_TYPES:
        raise NormalizationError(
            f"{source_urn}: invalid claim_type {claim_type!r} "
            f"(expected one of {sorted(_VALID_CLAIM_TYPES)})",
        )

    subject_did = envelope.get("subject_did")
    if not isinstance(subject_did, str) or not subject_did:
        raise NormalizationError(f"{source_urn}: subject_did missing or empty")

    provider_did = envelope.get("provider_did")
    if not isinstance(provider_did, str) or not provider_did:
        raise NormalizationError(f"{source_urn}: provider_did missing or empty")

    issued_at_raw = envelope.get("issued_at")
    if not isinstance(issued_at_raw, str):
        raise NormalizationError(f"{source_urn}: issued_at missing or not a string")

    try:
        issued_at = _parse_iso_timestamp(issued_at_raw)
    except (ValueError, TypeError) as exc:
        raise NormalizationError(
            f"{source_urn}: issued_at not RFC 3339: {issued_at_raw!r} ({exc})",
        ) from exc

    expires_at: datetime | None = None
    expires_at_raw = envelope.get("expires_at")
    if expires_at_raw is not None:
        if not isinstance(expires_at_raw, str):
            raise NormalizationError(
                f"{source_urn}: expires_at must be a string if present",
            )
        try:
            expires_at = _parse_iso_timestamp(expires_at_raw)
        except (ValueError, TypeError) as exc:
            raise NormalizationError(
                f"{source_urn}: expires_at not RFC 3339: {expires_at_raw!r} ({exc})",
            ) from exc
    elif freshness_ttl_seconds is not None:
        # No explicit expiry → derive from issued_at + TTL
        from datetime import timedelta
        expires_at = issued_at + timedelta(seconds=freshness_ttl_seconds)

    # Step 3: resolve provider's JWKS + find signing key
    sig_block = envelope.get("signature")
    if not isinstance(sig_block, dict):
        raise NormalizationError(f"{source_urn}: signature block missing")
    kid = sig_block.get("kid")
    if not isinstance(kid, str):
        raise NormalizationError(f"{source_urn}: signature.kid missing")

    jwks_url = _did_web_to_jwks_url(provider_did)
    keys = _fetch_jwks(jwks_url, http_client=http_client)
    pubkey = _find_ed25519_key(keys, kid)

    # Step 4: verify Ed25519 signature over JCS preimage
    _verify_envelope_signature(envelope, pubkey)

    # Step 5: compute freshness TTL remaining
    freshness_remaining: int | None = None
    if expires_at is not None:
        delta = (expires_at - datetime.now(timezone.utc)).total_seconds()
        freshness_remaining = max(0, int(delta))

    return NormalizedAttestation(
        source_urn=source_urn,
        claim_type=claim_type,
        claim_subtype=envelope.get("claim_subtype"),
        subject_did=subject_did,
        provider_did=provider_did,
        payload=envelope.get("payload") or {},
        signature_verified=True,
        registry_signature_verified=registry_signature_verified,
        issued_at=issued_at,
        expires_at=expires_at,
        freshness_ttl_remaining_seconds=freshness_remaining,
    )


__all__ = [
    "NormalizationError",
    "normalize",
]
