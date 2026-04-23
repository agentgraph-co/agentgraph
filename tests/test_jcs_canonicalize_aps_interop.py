"""Cross-implementation regression test for RFC 8785 JCS canonicalization.

Binds ``src.signing.canonicalize_jcs_strict`` to the APS bilateral-delegation
fixture at ``aeoess/agent-passport-system/fixtures/bilateral-delegation/``.

**Why this test exists.** CTEF (Composable Trust Evidence Format, A2A#1734)
composes AgentGraph verdicts with APS delegation chains via a shared
``delegation_chain_root`` that is content-addressed over canonical JSON.
The composition only works if AgentGraph and APS produce *byte-identical*
canonical output for the same input. A silent canonicalizer drift — on
null handling, unicode escaping, key ordering — breaks every bilateral
receipt in the wild without any visible API change.

If this test fails, do not patch ``canonicalize_jcs_strict`` to match:
a silent canonical change invalidates every previously-signed CTEF
envelope. Treat the failure as a breaking interop event, bump the
fixture version, and coordinate with APS maintainers.

Fixture source: https://github.com/aeoess/agent-passport-system/tree/main/fixtures/bilateral-delegation
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.signing import canonicalize_jcs_strict

FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "aps-bilateral-delegation"
    / "canonicalize-fixture-v1.json"
)

# Per APS README.md: deterministic keypair derivation.
_APS_SEED_INPUT = b"aps-canonicalize-fixture-v1"
_APS_EXPECTED_SEED_HEX = (
    "4f3d8defea1e82c1705c35d97ee4db046c6313ba83855a7d0de04a44f04c834a"
)
_APS_EXPECTED_PUBKEY_HEX = (
    "16bd0f3e8181e93d58c23268ee0d5f4d5b70b3ce66fc246c0f5d7ec3dda9ab80"
)


@pytest.fixture(scope="module")
def fixture_data() -> dict:
    with open(FIXTURE_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def vectors(fixture_data: dict) -> list[dict]:
    return fixture_data["vectors"]


def test_deterministic_keypair_reproduces():
    """APS seed → pubkey derivation must reproduce locally."""
    seed = hashlib.sha256(_APS_SEED_INPUT).digest()
    assert seed.hex() == _APS_EXPECTED_SEED_HEX, (
        f"APS seed derivation drifted: got {seed.hex()}"
    )
    priv = Ed25519PrivateKey.from_private_bytes(seed)
    pub_hex = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    assert pub_hex == _APS_EXPECTED_PUBKEY_HEX, (
        f"APS pubkey derivation drifted: got {pub_hex}"
    )


def test_fixture_has_all_10_vectors(vectors: list[dict]):
    assert len(vectors) == 10, (
        f"APS fixture vector count changed: got {len(vectors)}, "
        "expected 10. Bump fixture version and coordinate with APS."
    )


@pytest.mark.parametrize(
    "vector_name",
    [
        "nested-null-preservation",
        "key-ordering-unicode",
        "empty-containers",
        "deeply-nested",
        "string-escape-tab",
        "string-escape-unicode",
        "numeric-edge-cases",
        "array-of-objects",
        "bilateral-receipt-shape",
        "migration-attestation-shape",
    ],
)
def test_canonical_bytes_reproduce_byte_exact(
    vectors: list[dict], vector_name: str,
):
    """Every APS vector must produce identical canonical bytes + SHA-256."""
    vector = next(v for v in vectors if v["name"] == vector_name)

    canonical = canonicalize_jcs_strict(vector["input"])

    assert canonical.hex() == vector["canonical_bytes_hex"], (
        f"{vector_name}: canonical bytes diverged from APS fixture."
    )
    assert hashlib.sha256(canonical).hexdigest() == vector["canonical_sha256"], (
        f"{vector_name}: SHA-256 diverged from APS fixture."
    )


@pytest.mark.parametrize(
    "vector_name",
    [
        "nested-null-preservation",
        "key-ordering-unicode",
        "empty-containers",
        "deeply-nested",
        "string-escape-tab",
        "string-escape-unicode",
        "numeric-edge-cases",
        "array-of-objects",
        "bilateral-receipt-shape",
        "migration-attestation-shape",
    ],
)
def test_ed25519_signature_reproduces(
    vectors: list[dict], vector_name: str,
):
    """Signing the canonical bytes with the APS deterministic key must
    produce the exact signature APS published — proves end-to-end
    bilateral receipt interop, not just canonicalization."""
    vector = next(v for v in vectors if v["name"] == vector_name)

    seed = hashlib.sha256(_APS_SEED_INPUT).digest()
    priv = Ed25519PrivateKey.from_private_bytes(seed)

    canonical = canonicalize_jcs_strict(vector["input"])
    our_sig = priv.sign(canonical)

    assert our_sig.hex() == vector["ed25519_signature_over_canonical_hex"], (
        f"{vector_name}: Ed25519 signature diverged from APS fixture."
    )

    # And APS's signature must verify against our canonical bytes.
    priv.public_key().verify(
        bytes.fromhex(vector["ed25519_signature_over_canonical_hex"]),
        canonical,
    )
