"""Generate the 4 negative-path conformance fixtures for A2A #1496.

Targets: aeoess/aps-conformance-suite#3 — fixtures/composition/a2a-1496-negative-paths/

Per aeoess's format notes on A2A #1786 (2026-05-13):
  1. Signature: Ed25519 over canonicalizeJCS(link minus signature) directly, NO sha256 wrap.
  2. Canonicalization: RFC 8785 JCS with null values preserved.
  3. Field names: camelCase `validityWindow.not_after` (CTEF v0.3.2 §A spelling).
  4. Depth check: chain-level `chain.length > max_depth`.
  Validator check order: depth → validity → signature → scope.
  One targeted violation per fixture; first check in order fires.

Reproducibility: keys derived from deterministic Ed25519 seeds (see SEEDS below).
Re-running this script produces byte-identical fixtures.

Output: ./generated-fixtures/{01-scope-expansion,02-depth-violation,
03-signature-substitution,04-validity-expired}.fixture.json + generation-provenance.json
"""
from __future__ import annotations

import base64
import json
import math
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


# --- JCS canonicalization (matches src.signing.canonicalize_jcs_strict) ---


def _normalize_for_jcs_strict(obj: object) -> object:
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


def canonicalize_jcs_strict(payload: object) -> bytes:
    """RFC 8785 JCS with null values preserved."""
    cleaned = _normalize_for_jcs_strict(payload)
    return json.dumps(
        cleaned, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def keypair_from_seed_hex(seed_hex: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))


def public_key_hex(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return raw.hex()


# --- Deterministic seeds (reproducible fixture generation) ---

SEEDS = {
    "root": "01" * 32,
    "agent_a": "02" * 32,
    "agent_b": "03" * 32,
    "agent_c": "04" * 32,
    "agent_d": "05" * 32,
}

KEYS = {label: keypair_from_seed_hex(seed) for label, seed in SEEDS.items()}

# --- DIDs ---

ROOT_DID = "did:web:agentgraph.co"
AGENT_A_DID = "did:web:agent-a.example.com"
AGENT_B_DID = "did:web:agent-b.example.com"
AGENT_C_DID = "did:web:agent-c.example.com"
AGENT_D_DID = "did:web:agent-d.example.com"

# --- Reference times (chosen so fixtures are stable across v0.3.2 publish window) ---

NOT_BEFORE = "2026-05-01T00:00:00Z"
NOT_AFTER_VALID = "2026-12-31T23:59:59Z"  # well after v0.3.2 publish
NOT_AFTER_EXPIRED = "2024-12-31T23:59:59Z"  # well in the past


# --- Chain link builder (sign over canonical(link minus signature)) ---


def build_link(
    issuer: str,
    subject: str,
    scope: list[str],
    not_before: str,
    not_after: str,
    signing_key: Ed25519PrivateKey,
) -> dict:
    """Build a delegation chain link with a valid Ed25519 signature.

    Per aeoess format note 1: Ed25519 over canonicalizeJCS(link minus signature)
    directly, no sha256 wrap.
    """
    link_unsigned = {
        "issuer": issuer,
        "subject": subject,
        "scope": scope,
        "validityWindow": {
            "not_before": not_before,
            "not_after": not_after,
        },
    }
    canonical = canonicalize_jcs_strict(link_unsigned)
    sig = signing_key.sign(canonical)
    return {**link_unsigned, "signature": b64url(sig)}


# --- Fixture 1: scope expansion → INVALID_CLAIM_SCOPE ---


def fixture_scope_expansion() -> dict:
    """Chain[0] grants {data:read}; chain[1] expands to {data:read, data:write}.

    All links validly signed, all within validity window, chain.length=2 ≤ max_depth=3.
    Depth + validity + signature checks all pass; scope check fires.
    """
    link0 = build_link(
        ROOT_DID, AGENT_A_DID, ["data:read"],
        NOT_BEFORE, NOT_AFTER_VALID, KEYS["root"],
    )
    link1 = build_link(
        AGENT_A_DID, AGENT_B_DID, ["data:read", "data:write"],
        NOT_BEFORE, NOT_AFTER_VALID, KEYS["agent_a"],
    )
    return {
        "name": "scope-expansion",
        "description": (
            "Chain of length 2 where link[1] expands the scope set granted by "
            "link[0] (data:read → {data:read, data:write}). All links validly "
            "signed and within validity window; chain.length=2 ≤ max_depth=3 so "
            "depth + validity + signature checks pass before scope check fires."
        ),
        "input": {
            "chain": [link0, link1],
            "max_depth": 3,
        },
        "expected_error_code": "INVALID_CLAIM_SCOPE",
    }


# --- Fixture 2: depth violation → DELEGATION_DEPTH_EXCEEDED ---


def fixture_depth_violation() -> dict:
    """Chain of length 4 with max_depth=3.

    First check (depth) fires before validity, signature, or scope are evaluated.
    All links nevertheless validly signed + within validity to demonstrate that
    depth short-circuits cleanly.
    """
    scope = ["data:read"]
    chain = []
    # root -> agent_a -> agent_b -> agent_c -> agent_d (4 hops, chain.length=4)
    signing_pairs = [
        (ROOT_DID, AGENT_A_DID, KEYS["root"]),
        (AGENT_A_DID, AGENT_B_DID, KEYS["agent_a"]),
        (AGENT_B_DID, AGENT_C_DID, KEYS["agent_b"]),
        (AGENT_C_DID, AGENT_D_DID, KEYS["agent_c"]),
    ]
    for issuer, subject, key in signing_pairs:
        chain.append(build_link(
            issuer, subject, scope, NOT_BEFORE, NOT_AFTER_VALID, key,
        ))
    return {
        "name": "depth-violation",
        "description": (
            "Chain of length 4 with max_depth=3. chain.length > max_depth fires "
            "DELEGATION_DEPTH_EXCEEDED before validity, signature, or scope are "
            "evaluated. All four links are nevertheless validly signed and within "
            "validity window so the depth check is demonstrably short-circuiting."
        ),
        "input": {
            "chain": chain,
            "max_depth": 3,
        },
        "expected_error_code": "DELEGATION_DEPTH_EXCEEDED",
    }


# --- Fixture 3: signature substitution → INVALID_SIGNATURE ---


def fixture_signature_substitution() -> dict:
    """Chain[1]'s signature is replaced with a valid Ed25519 signature over
    unrelated canonical bytes (still produced by the correct signing key, but
    not over link[1]'s own canonical form).

    chain.length=2 ≤ max_depth=3 and validityWindow is current, so depth +
    validity pass; signature check fires before scope.
    """
    link0 = build_link(
        ROOT_DID, AGENT_A_DID, ["data:read"],
        NOT_BEFORE, NOT_AFTER_VALID, KEYS["root"],
    )
    # Build a normal link[1] first to establish its un-substituted shape.
    link1 = build_link(
        AGENT_A_DID, AGENT_B_DID, ["data:read"],
        NOT_BEFORE, NOT_AFTER_VALID, KEYS["agent_a"],
    )
    # Substitute link[1]'s signature with a sig over unrelated canonical bytes.
    decoy_canonical = canonicalize_jcs_strict({"unrelated": "payload"})
    decoy_sig = KEYS["agent_a"].sign(decoy_canonical)
    link1["signature"] = b64url(decoy_sig)
    return {
        "name": "signature-substitution",
        "description": (
            "Chain of length 2 where link[1]'s signature is replaced with an "
            "Ed25519 signature over unrelated canonical bytes "
            "(JCS of `{\"unrelated\":\"payload\"}`). The signature is still "
            "produced by the correct signing key (agent_a) but does not "
            "cover link[1]'s own canonical form. chain.length=2 ≤ max_depth=3 "
            "and validityWindow is current, so depth + validity pass; signature "
            "check fires before scope."
        ),
        "input": {
            "chain": [link0, link1],
            "max_depth": 3,
        },
        "expected_error_code": "INVALID_SIGNATURE",
    }


# --- Fixture 4: validity expired → VALIDITY_EXPIRED ---


def fixture_validity_expired() -> dict:
    """Single-link chain where validityWindow.not_after is 2024-12-31 (past).

    chain.length=1 ≤ max_depth=3 so depth passes; validity check fires before
    signature or scope evaluation.
    """
    link0 = build_link(
        ROOT_DID, AGENT_A_DID, ["data:read"],
        "2024-01-01T00:00:00Z", NOT_AFTER_EXPIRED, KEYS["root"],
    )
    return {
        "name": "validity-expired",
        "description": (
            "Chain of length 1 where the single link's validityWindow.not_after "
            "is 2024-12-31T23:59:59Z (well in the past). chain.length=1 ≤ "
            "max_depth=3 so depth passes; validity check fires before signature "
            "or scope evaluation. The signature is nevertheless validly produced "
            "over canonicalizeJCS(link minus signature) so the validity check "
            "is demonstrably short-circuiting before the signature check."
        ),
        "input": {
            "chain": [link0],
            "max_depth": 3,
        },
        "expected_error_code": "VALIDITY_EXPIRED",
    }


# --- Provenance file (so any verifier can confirm reproducibility) ---


def provenance() -> dict:
    return {
        "generator": (
            "agentgraph-co/agentgraph scripts/gen_a2a_1496_negative_paths.py"
        ),
        "canonicalization": (
            "RFC 8785 (JCS), nulls preserved (matches "
            "src.signing.canonicalize_jcs_strict; same byte output as "
            "trailofbits/rfc8785.py and @nobulex/crypto canonicalize)"
        ),
        "signature_scheme": (
            "Ed25519 over canonicalizeJCS(link minus signature), no sha256 wrap "
            "(per aeoess format note 1 on A2A #1786, 2026-05-13)"
        ),
        "signature_encoding": "base64url, no padding",
        "field_name_convention": (
            "CTEF v0.3.2 §A: camelCase validityWindow with snake_case "
            "not_before/not_after; chain-level max_depth"
        ),
        "validator_check_order": ["depth", "validity", "signature", "scope"],
        "ed25519_seeds_hex": SEEDS,
        "ed25519_public_keys_hex": {
            label: public_key_hex(key) for label, key in KEYS.items()
        },
        "reference_times": {
            "not_before_valid": NOT_BEFORE,
            "not_after_valid": NOT_AFTER_VALID,
            "not_after_expired": NOT_AFTER_EXPIRED,
        },
        "fixture_intent": {
            "01-scope-expansion": (
                "Triggers INVALID_CLAIM_SCOPE after passing depth + validity + "
                "signature"
            ),
            "02-depth-violation": (
                "Triggers DELEGATION_DEPTH_EXCEEDED — first check in order"
            ),
            "03-signature-substitution": (
                "Triggers INVALID_SIGNATURE after passing depth + validity"
            ),
            "04-validity-expired": (
                "Triggers VALIDITY_EXPIRED after passing depth"
            ),
        },
    }


def main() -> None:
    outdir = Path(__file__).parent.parent / "generated-fixtures" / "a2a-1496-negative-paths"
    outdir.mkdir(parents=True, exist_ok=True)

    fixtures = [
        ("01-scope-expansion.fixture.json", fixture_scope_expansion()),
        ("02-depth-violation.fixture.json", fixture_depth_violation()),
        ("03-signature-substitution.fixture.json", fixture_signature_substitution()),
        ("04-validity-expired.fixture.json", fixture_validity_expired()),
    ]

    for filename, payload in fixtures:
        out = outdir / filename
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {out}")

    prov_file = outdir / "generation-provenance.json"
    prov_file.write_text(json.dumps(provenance(), indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {prov_file}")


if __name__ == "__main__":
    main()
