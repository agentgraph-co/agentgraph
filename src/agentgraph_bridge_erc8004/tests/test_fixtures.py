"""Round-trip the 3 snapshot fixtures through normalize() and verify the
output matches the captured `expected_normalized.json` exactly.

This is the canonical reproduction test: anyone who clones the repo and
runs pytest gets byte-deterministic confirmation that:
  1. The fixture envelopes parse cleanly
  2. The Ed25519 signatures verify against the bundled JWKS
  3. The NormalizedAttestation output matches the captured expected shape

If this test fails on a clean clone, either:
  - rfc8785 / cryptography changed canonical-bytes behavior (substrate drift)
  - The normalizer logic regressed
  - Someone modified a fixture without re-running regen_fixtures.py

All three are signal-worthy and worth investigating before shipping.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from agentgraph_bridge_erc8004.attestation_normalizer import normalize
from agentgraph_bridge_erc8004.models import ERC8004Entry

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

_FIXTURE_NAMES = [
    "identity_basic",
    "authority_tier_upgrade",
    "continuity_behavioral",
]


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _load_entry(name: str) -> ERC8004Entry:
    raw = json.loads((_FIXTURES_DIR / name / "entry.json").read_text())
    # Convert the b64-encoded data field back to bytes
    data_bytes = _b64url_decode(raw.pop("data_b64"))
    raw["data"] = data_bytes
    # ERC8004Entry expects datetime, not string
    raw["block_timestamp"] = datetime.fromisoformat(raw["block_timestamp"])
    return ERC8004Entry(**raw)


def _load_jwks(name: str) -> dict:
    return json.loads((_FIXTURES_DIR / name / "jwks.json").read_text())


def _load_expected(name: str) -> dict:
    return json.loads((_FIXTURES_DIR / name / "expected_normalized.json").read_text())


def _mock_jwks_client(jwks: dict) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=jwks)
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("fixture_name", _FIXTURE_NAMES)
def test_fixture_round_trip(fixture_name: str):
    entry = _load_entry(fixture_name)
    jwks = _load_jwks(fixture_name)
    expected = _load_expected(fixture_name)
    client = _mock_jwks_client(jwks)

    result = normalize(entry, http_client=client)

    assert result.source_urn == expected["source_urn"]
    assert result.claim_type == expected["claim_type"]
    assert result.claim_subtype == expected["claim_subtype"]
    assert result.subject_did == expected["subject_did"]
    assert result.provider_did == expected["provider_did"]
    assert result.payload == expected["payload"]
    assert result.signature_verified is True
    assert result.registry_signature_verified is True
    assert result.is_admissible


def test_all_three_fixtures_present():
    """Guard against fixtures getting accidentally deleted."""
    for name in _FIXTURE_NAMES:
        d = _FIXTURES_DIR / name
        assert d.exists(), f"Fixture dir missing: {d}"
        for f in ("entry.json", "envelope.json", "jwks.json", "expected_normalized.json"):
            assert (d / f).exists(), f"Fixture file missing: {d / f}"
