"""Generate 3 mainnet-shaped snapshot fixtures with real Ed25519 signatures.

Run from the package root:
    python -m agentgraph_bridge_erc8004.fixtures.regen_fixtures

Produces 3 subdirectories under fixtures/, each containing:
    - entry.json: ERC8004Entry shape
    - envelope.json: signed CTEF envelope
    - jwks.json: matching provider JWKS
    - expected_normalized.json: expected NormalizedAttestation output

The Ed25519 keypair is deterministic per fixture (seeded from fixture name
via SHA-256). Re-running this script produces byte-identical output, so
fixture diffs are stable in git.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

FIXTURES_DIR = Path(__file__).parent

# Deterministic timestamp: 2026-05-22 12:00 UTC. Far enough in the future
# that fixtures stay admissible for years.
_FIXTURE_ISSUED_AT = "2026-05-22T12:00:00+00:00"
_FIXTURE_EXPIRES_AT = "2030-05-22T12:00:00+00:00"


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _deterministic_priv(seed_str: str) -> Ed25519PrivateKey:
    """Derive a deterministic Ed25519 private key from a string seed."""
    seed = hashlib.sha256(seed_str.encode()).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def _sign_envelope(env: dict, priv: Ed25519PrivateKey, kid: str) -> dict:
    """Sign a CTEF envelope in-place with deterministic Ed25519."""
    preimage = rfc8785.dumps(env)
    sig = priv.sign(preimage)
    return {
        **env,
        "signature": {
            "alg": "EdDSA",
            "kid": kid,
            "sig": _b64url(sig),
        },
    }


def _build_jwks(priv: Ed25519PrivateKey, kid: str) -> dict:
    """Build a JWKS containing the public half of `priv`."""
    pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "kid": kid,
                "x": _b64url(pub),
                "use": "sig",
                "alg": "EdDSA",
            },
        ],
    }


def _build_fixture(
    name: str,
    *,
    registry: str,
    entry_id: int,
    submitter: str,
    subject_did: str,
    provider_did: str,
    claim_type: str,
    claim_subtype: str | None = None,
    payload: dict,
    kid: str = "fixture-key-1",
) -> None:
    """Build one fixture subdirectory."""
    out_dir = FIXTURES_DIR / name
    out_dir.mkdir(exist_ok=True)

    priv = _deterministic_priv(f"agentgraph-erc8004-fixture:{name}")
    envelope = {
        "claim_type": claim_type,
        "subject_did": subject_did,
        "provider_did": provider_did,
        "issued_at": _FIXTURE_ISSUED_AT,
        "expires_at": _FIXTURE_EXPIRES_AT,
        "payload": payload,
    }
    if claim_subtype is not None:
        envelope["claim_subtype"] = claim_subtype
    envelope_signed = _sign_envelope(envelope, priv, kid)

    data_bytes = json.dumps(envelope_signed, separators=(",", ":")).encode()

    entry = {
        "registry": registry,
        "entry_id": entry_id,
        "submitter": submitter,
        "subject_did": subject_did,
        "data_b64": _b64url(data_bytes),  # raw bytes round-tripped via b64
        "block_number": 25_000_000 + entry_id,
        "block_timestamp": _FIXTURE_ISSUED_AT,
        "tx_hash": "0x" + hashlib.sha256(name.encode()).hexdigest(),
    }

    jwks = _build_jwks(priv, kid)

    expected = {
        "source_urn": f"urn:erc8004:{registry}:{entry_id}",
        "claim_type": claim_type,
        "claim_subtype": claim_subtype,
        "subject_did": subject_did,
        "provider_did": provider_did,
        "payload": payload,
        "signature_verified": True,
        "registry_signature_verified": True,
        "issued_at": _FIXTURE_ISSUED_AT,
        "expires_at": _FIXTURE_EXPIRES_AT,
    }

    (out_dir / "entry.json").write_text(json.dumps(entry, indent=2) + "\n")
    (out_dir / "envelope.json").write_text(json.dumps(envelope_signed, indent=2) + "\n")
    (out_dir / "jwks.json").write_text(json.dumps(jwks, indent=2) + "\n")
    (out_dir / "expected_normalized.json").write_text(
        json.dumps(expected, indent=2) + "\n",
    )
    print(f"  ✓ {name}")


def main() -> None:
    print("Generating ERC-8004 bridge fixtures:")

    _build_fixture(
        "identity_basic",
        registry="identity",
        entry_id=1,
        submitter="0x" + "ab" * 20,
        subject_did="did:web:agent.example.com",
        provider_did="did:web:registrar.example.com",
        claim_type="identity",
        payload={
            "sub": "did:web:agent.example.com",
            "verified_method": "did:web:agent.example.com#key-1",
            "credential_id": "vc:identity:agent-example:001",
        },
    )

    _build_fixture(
        "authority_tier_upgrade",
        registry="reputation",
        entry_id=42,
        submitter="0x" + "cd" * 20,
        subject_did="did:web:agent.example.com",
        provider_did="did:web:trust.arkforge.tech",
        claim_type="authority",
        claim_subtype="tier_upgrade",
        payload={
            "subject_did": "did:web:agent.example.com",
            "from_tier": "NEUTRAL",
            "to_tier": "TRUSTED",
            "policy_ref": "sha256:aeb0208a" + "0" * 56,
            "scope_boundary": "session:ctef-tier-upgrade-fixture-v1",
            "requester_did": "did:web:requester.example",
            "constraint_evaluation": {
                "facet": "ResourceViolation",
                "limit": 100,
                "actual": 42,
                "delta": -58,
            },
        },
    )

    _build_fixture(
        "continuity_behavioral",
        registry="validation",
        entry_id=99,
        submitter="0x" + "ef" * 20,
        subject_did="did:web:agent.example.com",
        provider_did="did:web:dominion-observatory.sgdata.workers.dev",
        claim_type="continuity",
        claim_subtype="behavioral_eval",
        payload={
            "subject_did": "did:web:agent.example.com",
            "evidence_class": "behavioral",
            "interaction_success_rate": 0.94,
            "latency_p99_ms": 850,
            "anomaly_score": 0.02,
            "compliance_posture": ["eu-ai-act-art-12", "singapore-imda"],
            "observation_window_days": 30,
        },
    )

    print("\nAll fixtures regenerated.")


if __name__ == "__main__":
    main()
