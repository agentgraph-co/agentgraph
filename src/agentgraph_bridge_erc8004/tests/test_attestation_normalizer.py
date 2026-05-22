"""Tests for ERC-8004 attestation normalizer.

Signature verification uses real Ed25519 keys generated per-test (not
mocked). did:web JWKS fetches are mocked via httpx.MockTransport so
no network I/O.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agentgraph_bridge_erc8004.attestation_normalizer import (
    NormalizationError,
    _did_web_to_jwks_url,
    normalize,
)
from agentgraph_bridge_erc8004.models import ERC8004Entry, ERC8004Registry


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _make_signed_envelope(
    private_key: Ed25519PrivateKey,
    kid: str = "test-key-1",
    *,
    claim_type: str = "identity",
    subject_did: str = "did:web:agent.example.com",
    provider_did: str = "did:web:issuer.example.com",
    issued_at: str = "2026-05-22T10:00:00Z",
    expires_at: str | None = "2027-05-22T10:00:00Z",
    payload: dict | None = None,
    omit_signature: bool = False,
    bad_alg: str | None = None,
) -> dict:
    """Build a CTEF envelope with a real Ed25519 signature for testing."""
    env: dict = {
        "claim_type": claim_type,
        "subject_did": subject_did,
        "provider_did": provider_did,
        "issued_at": issued_at,
        "payload": payload or {"sub": subject_did},
    }
    if expires_at is not None:
        env["expires_at"] = expires_at

    if omit_signature:
        return env

    preimage = rfc8785.dumps(env)
    sig_bytes = private_key.sign(preimage)
    env["signature"] = {
        "alg": bad_alg or "EdDSA",
        "kid": kid,
        "sig": _b64url(sig_bytes),
    }
    return env


def _make_jwks(public_key, kid: str = "test-key-1") -> dict:
    """Build a JWKS containing an Ed25519 OKP key."""
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
    )
    raw_pub = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "kid": kid,
                "x": _b64url(raw_pub),
                "use": "sig",
                "alg": "EdDSA",
            },
        ],
    }


def _mock_jwks_client(jwks_dict: dict) -> httpx.Client:
    """Build an httpx.Client backed by a MockTransport returning jwks_dict."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=jwks_dict)
    return httpx.Client(transport=httpx.MockTransport(handler))


def _make_entry(data: bytes, registry: ERC8004Registry = ERC8004Registry.IDENTITY) -> ERC8004Entry:
    """Build an ERC8004Entry wrapping arbitrary data bytes."""
    return ERC8004Entry(
        registry=registry,
        entry_id=42,
        submitter="0x" + "ab" * 20,
        subject_did="did:web:agent.example.com",
        data=data,
        block_number=25_000_000,
        block_timestamp=datetime(2026, 5, 22, 10, 0, 0, tzinfo=timezone.utc),
        tx_hash="0x" + "cd" * 32,
    )


# ────────────────────────────────────────────────────────────────────
# Happy path
# ────────────────────────────────────────────────────────────────────


class TestNormalizeHappyPath:
    def test_valid_identity_attestation(self):
        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key()
        env = _make_signed_envelope(priv)
        jwks = _make_jwks(pub)
        client = _mock_jwks_client(jwks)
        entry = _make_entry(json.dumps(env).encode())

        result = normalize(entry, http_client=client)

        assert result.signature_verified is True
        assert result.registry_signature_verified is True
        assert result.claim_type == "identity"
        assert result.subject_did == "did:web:agent.example.com"
        assert result.provider_did == "did:web:issuer.example.com"
        assert result.is_admissible
        assert result.source_urn == "urn:erc8004:identity:42"

    def test_with_payload(self):
        priv = Ed25519PrivateKey.generate()
        env = _make_signed_envelope(
            priv, payload={"sub": "did:web:agent.example.com", "verified_at": "2026-05-22"},
        )
        jwks = _make_jwks(priv.public_key())
        client = _mock_jwks_client(jwks)
        entry = _make_entry(json.dumps(env).encode())

        result = normalize(entry, http_client=client)
        assert result.payload["verified_at"] == "2026-05-22"

    def test_all_claim_types_accepted(self):
        for claim_type in ("identity", "transport", "authority", "continuity"):
            priv = Ed25519PrivateKey.generate()
            env = _make_signed_envelope(priv, claim_type=claim_type)
            client = _mock_jwks_client(_make_jwks(priv.public_key()))
            entry = _make_entry(json.dumps(env).encode())
            result = normalize(entry, http_client=client)
            assert result.claim_type == claim_type


# ────────────────────────────────────────────────────────────────────
# Signature verification failures (security-critical)
# ────────────────────────────────────────────────────────────────────


class TestSignatureFailures:
    def test_wrong_signing_key(self):
        signing_priv = Ed25519PrivateKey.generate()
        different_priv = Ed25519PrivateKey.generate()
        env = _make_signed_envelope(signing_priv)
        # JWKS published a DIFFERENT public key — sig won't verify
        jwks = _make_jwks(different_priv.public_key())
        client = _mock_jwks_client(jwks)
        entry = _make_entry(json.dumps(env).encode())

        with pytest.raises(NormalizationError, match="signature verification FAILED"):
            normalize(entry, http_client=client)

    def test_tampered_payload(self):
        priv = Ed25519PrivateKey.generate()
        env = _make_signed_envelope(priv)
        # Tamper with payload AFTER signing
        env["payload"]["sub"] = "did:web:attacker.example.com"
        client = _mock_jwks_client(_make_jwks(priv.public_key()))
        entry = _make_entry(json.dumps(env).encode())

        with pytest.raises(NormalizationError, match="signature verification FAILED"):
            normalize(entry, http_client=client)

    def test_missing_signature_block(self):
        priv = Ed25519PrivateKey.generate()
        env = _make_signed_envelope(priv, omit_signature=True)
        client = _mock_jwks_client(_make_jwks(priv.public_key()))
        entry = _make_entry(json.dumps(env).encode())

        with pytest.raises(NormalizationError, match="signature block missing"):
            normalize(entry, http_client=client)

    def test_unsupported_alg(self):
        priv = Ed25519PrivateKey.generate()
        env = _make_signed_envelope(priv, bad_alg="ES256")
        client = _mock_jwks_client(_make_jwks(priv.public_key()))
        entry = _make_entry(json.dumps(env).encode())

        with pytest.raises(NormalizationError, match="Unsupported signature alg"):
            normalize(entry, http_client=client)

    def test_kid_not_in_jwks(self):
        priv = Ed25519PrivateKey.generate()
        env = _make_signed_envelope(priv, kid="nonexistent-kid")
        # JWKS published under a different kid
        jwks = _make_jwks(priv.public_key(), kid="other-kid")
        client = _mock_jwks_client(jwks)
        entry = _make_entry(json.dumps(env).encode())

        with pytest.raises(NormalizationError, match="kid 'nonexistent-kid' not found"):
            normalize(entry, http_client=client)


# ────────────────────────────────────────────────────────────────────
# Envelope shape validation
# ────────────────────────────────────────────────────────────────────


class TestEnvelopeValidation:
    def test_invalid_utf8(self):
        entry = _make_entry(b"\xff\xfe\x00\x00")
        with pytest.raises(NormalizationError, match="not valid UTF-8"):
            normalize(entry)

    def test_invalid_json(self):
        entry = _make_entry(b"{not json")
        with pytest.raises(NormalizationError, match="not valid JSON"):
            normalize(entry)

    def test_envelope_not_object(self):
        entry = _make_entry(b'["array"]')
        with pytest.raises(NormalizationError, match="envelope must be a JSON object"):
            normalize(entry)

    def test_invalid_claim_type(self):
        priv = Ed25519PrivateKey.generate()
        env = _make_signed_envelope(priv, claim_type="bogus")
        client = _mock_jwks_client(_make_jwks(priv.public_key()))
        entry = _make_entry(json.dumps(env).encode())
        with pytest.raises(NormalizationError, match="invalid claim_type"):
            normalize(entry, http_client=client)

    def test_missing_subject_did(self):
        priv = Ed25519PrivateKey.generate()
        env = _make_signed_envelope(priv, subject_did="")
        client = _mock_jwks_client(_make_jwks(priv.public_key()))
        entry = _make_entry(json.dumps(env).encode())
        with pytest.raises(NormalizationError, match="subject_did missing or empty"):
            normalize(entry, http_client=client)

    def test_missing_provider_did(self):
        priv = Ed25519PrivateKey.generate()
        env = _make_signed_envelope(priv, provider_did="")
        client = _mock_jwks_client(_make_jwks(priv.public_key()))
        entry = _make_entry(json.dumps(env).encode())
        with pytest.raises(NormalizationError, match="provider_did missing or empty"):
            normalize(entry, http_client=client)


# ────────────────────────────────────────────────────────────────────
# Freshness + TTL
# ────────────────────────────────────────────────────────────────────


class TestFreshness:
    def test_explicit_expires_at(self):
        priv = Ed25519PrivateKey.generate()
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        env = _make_signed_envelope(priv, expires_at=future)
        client = _mock_jwks_client(_make_jwks(priv.public_key()))
        entry = _make_entry(json.dumps(env).encode())
        result = normalize(entry, http_client=client)
        assert result.expires_at is not None
        assert result.freshness_ttl_remaining_seconds > 0
        assert result.is_admissible

    def test_expired_attestation_not_admissible(self):
        priv = Ed25519PrivateKey.generate()
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        env = _make_signed_envelope(priv, expires_at=past)
        client = _mock_jwks_client(_make_jwks(priv.public_key()))
        entry = _make_entry(json.dumps(env).encode())
        result = normalize(entry, http_client=client)
        # Signature verified, but expired → not admissible
        assert result.signature_verified is True
        assert result.freshness_ttl_remaining_seconds == 0
        assert not result.is_admissible

    def test_implicit_ttl_from_freshness_param(self):
        priv = Ed25519PrivateKey.generate()
        # Omit explicit expires_at; rely on caller-supplied TTL
        env = _make_signed_envelope(priv, expires_at=None)
        client = _mock_jwks_client(_make_jwks(priv.public_key()))
        entry = _make_entry(json.dumps(env).encode())
        result = normalize(entry, http_client=client, freshness_ttl_seconds=3600)
        assert result.expires_at is not None  # derived from issued_at + 3600s


# ────────────────────────────────────────────────────────────────────
# did:web URL resolution
# ────────────────────────────────────────────────────────────────────


class TestDIDWebResolution:
    def test_bare_domain(self):
        assert _did_web_to_jwks_url("did:web:example.com") == \
            "https://example.com/.well-known/jwks.json"

    def test_path_form(self):
        assert _did_web_to_jwks_url("did:web:example.com:agents:42") == \
            "https://example.com/agents/42/jwks.json"

    def test_non_web_method_rejected(self):
        with pytest.raises(NormalizationError, match="must use did:web"):
            _did_web_to_jwks_url("did:key:abc123")

    def test_empty_did_rejected(self):
        with pytest.raises(NormalizationError, match="Empty did:web"):
            _did_web_to_jwks_url("did:web:")
