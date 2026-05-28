"""Generate the 4 negative-path conformance fixtures for A2A #1496.

Targets: aeoess/aps-conformance-suite#3 — fixtures/composition/a2a-1496-negative-paths/

Shape conforms to aeoess's validator at
fixtures/composition/a2a-1496-negative-paths/lib.ts:

  NegativePathDelegation = {
    delegator: string  // Ed25519 PUBLIC KEY hex (64 chars)
    delegatee: string  // Ed25519 PUBLIC KEY hex
    scope: { action_categories: string[]; [k: string]: unknown }
    validityWindow: { not_before?: string; not_after: string }
    signature: string  // Ed25519 HEX signature (128 chars)
  }

  NegativePathInput = {
    chain: NegativePathDelegation[]
    max_depth?: number
    now?: string   // ISO 8601 UTC for deterministic VALIDITY_EXPIRED
  }

Validator check order:
  1. Depth (chain.length > max_depth)
  2. Per link root → leaf:
     a. validityWindow.not_after < now           → VALIDITY_EXPIRED
     b. Ed25519 verify signature                  → INVALID_SIGNATURE
     c. (non-root) action_categories expansion    → INVALID_CLAIM_SCOPE

Each fixture exercises EXACTLY ONE targeted violation; earlier checks
all pass cleanly. Pass `input.now` so fixtures are deterministic vs
real-time clock.

Reproducibility: deterministic Ed25519 seeds (see SEEDS below).
Re-running this script produces byte-identical fixtures.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# --- JCS canonicalization (RFC 8785, null-preserving) ---


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
    """RFC 8785 JCS with null values preserved.

    Byte-identical to aeoess's `canonicalizeJCS()` in
    fixtures/composition/a2a-1496-negative-paths/lib.ts for the subset
    of values exercised by these fixtures (objects, arrays, strings,
    integers, ISO 8601 timestamps; no floats, no Unicode-non-ASCII keys).
    """
    cleaned = _normalize_for_jcs_strict(payload)
    return json.dumps(
        cleaned, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


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
PUBS = {label: public_key_hex(key) for label, key in KEYS.items()}

# --- Reference times ---

NOT_BEFORE = "2026-05-01T00:00:00Z"
NOT_AFTER_VALID = "2026-12-31T23:59:59Z"
NOT_AFTER_EXPIRED = "2024-12-31T23:59:59Z"
FIXED_NOW = "2026-05-13T18:00:00Z"  # deterministic clock for all fixtures


# --- Chain link builder ---


def build_link(
    delegator_label: str,
    delegatee_label: str,
    action_categories: list[str],
    not_before: str,
    not_after: str,
) -> dict:
    """Build a delegation link signed by the delegator's key, per validator
    semantics in lib.ts:

      signature = ed25519_sign(
          delegator_private_key,
          canonicalizeJCS(link minus signature)
      ).hex()
    """
    link_unsigned = {
        "delegator": PUBS[delegator_label],
        "delegatee": PUBS[delegatee_label],
        "scope": {"action_categories": action_categories},
        "validityWindow": {
            "not_before": not_before,
            "not_after": not_after,
        },
    }
    canonical = canonicalize_jcs_strict(link_unsigned)
    sig = KEYS[delegator_label].sign(canonical)
    return {**link_unsigned, "signature": sig.hex()}


# --- Fixture 1: scope expansion → INVALID_CLAIM_SCOPE ---


def fixture_scope_expansion() -> dict:
    """chain[1] expands action_categories beyond chain[0]'s grant.

    chain.length=2 ≤ max_depth=3 (depth passes).
    All links within validityWindow vs now (validity passes).
    All signatures valid (signature passes).
    chain[1] action_categories {data:read, data:write} ⊄ chain[0]'s {data:read}.
    → INVALID_CLAIM_SCOPE on chain[1].
    """
    link0 = build_link(
        "root", "agent_a", ["data:read"], NOT_BEFORE, NOT_AFTER_VALID,
    )
    link1 = build_link(
        "agent_a", "agent_b", ["data:read", "data:write"],
        NOT_BEFORE, NOT_AFTER_VALID,
    )
    return {
        "name": "scope-expansion",
        "description": (
            "Chain of length 2 where chain[1] expands action_categories "
            "beyond chain[0]'s grant ({data:read} → {data:read, data:write}). "
            "Depth + validity + signature all pass; scope-narrowing check "
            "fires on chain[1] vs chain[0]."
        ),
        "input": {
            "chain": [link0, link1],
            "max_depth": 3,
            "now": FIXED_NOW,
        },
        "expected_error_code": "INVALID_CLAIM_SCOPE",
    }


# --- Fixture 2: depth violation → DELEGATION_DEPTH_EXCEEDED ---


def fixture_depth_violation() -> dict:
    """chain.length=4 > max_depth=3. Depth fires first.

    All 4 links nevertheless validly signed + within validity to
    demonstrate depth short-circuits cleanly before later checks.
    """
    scope = ["data:read"]
    chain = [
        build_link("root", "agent_a", scope, NOT_BEFORE, NOT_AFTER_VALID),
        build_link("agent_a", "agent_b", scope, NOT_BEFORE, NOT_AFTER_VALID),
        build_link("agent_b", "agent_c", scope, NOT_BEFORE, NOT_AFTER_VALID),
        build_link("agent_c", "agent_d", scope, NOT_BEFORE, NOT_AFTER_VALID),
    ]
    return {
        "name": "depth-violation",
        "description": (
            "Chain of length 4 with max_depth=3. chain.length > max_depth "
            "fires DELEGATION_DEPTH_EXCEEDED as the first check. All four "
            "links are nevertheless validly signed and within validity "
            "window so the depth check is demonstrably short-circuiting "
            "before validity/signature/scope are evaluated."
        ),
        "input": {
            "chain": chain,
            "max_depth": 3,
            "now": FIXED_NOW,
        },
        "expected_error_code": "DELEGATION_DEPTH_EXCEEDED",
    }


# --- Fixture 3: signature substitution → INVALID_SIGNATURE ---


def fixture_signature_substitution() -> dict:
    """chain[1]'s signature is replaced with a valid-shape Ed25519 sig over
    unrelated canonical bytes (still produced by the correct delegator key,
    just not over chain[1]'s own canonical form).

    chain.length=2 ≤ max_depth=3 (depth passes).
    Validity passes for both links.
    chain[0] signature valid.
    chain[1] signature fails verification.
    → INVALID_SIGNATURE on chain[1].
    """
    link0 = build_link(
        "root", "agent_a", ["data:read"], NOT_BEFORE, NOT_AFTER_VALID,
    )
    link1 = build_link(
        "agent_a", "agent_b", ["data:read"], NOT_BEFORE, NOT_AFTER_VALID,
    )
    # Substitute link1's signature with a sig over unrelated canonical bytes.
    decoy_canonical = canonicalize_jcs_strict({"unrelated": "payload"})
    decoy_sig = KEYS["agent_a"].sign(decoy_canonical)
    link1["signature"] = decoy_sig.hex()
    return {
        "name": "signature-substitution",
        "description": (
            "Chain of length 2 where chain[1]'s signature is replaced with "
            "an Ed25519 signature over canonicalizeJCS({\"unrelated\":"
            "\"payload\"}). The signature is produced by the correct "
            "delegator private key (agent_a) but does not cover chain[1]'s "
            "own canonical form. Depth + validity pass for both links + "
            "chain[0] signature valid; chain[1] signature verification fails."
        ),
        "input": {
            "chain": [link0, link1],
            "max_depth": 3,
            "now": FIXED_NOW,
        },
        "expected_error_code": "INVALID_SIGNATURE",
    }


# --- Fixture 4: validity expired → VALIDITY_EXPIRED ---


def fixture_validity_expired() -> dict:
    """Single-link chain where validityWindow.not_after is 2024-12-31 (past
    relative to FIXED_NOW=2026-05-13).

    chain.length=1 ≤ max_depth=3 (depth passes).
    chain[0].validityWindow.not_after < now → fires VALIDITY_EXPIRED.
    Signature is nevertheless validly produced (validity short-circuits
    before signature check).
    """
    link0 = build_link(
        "root", "agent_a", ["data:read"],
        "2024-01-01T00:00:00Z", NOT_AFTER_EXPIRED,
    )
    return {
        "name": "validity-expired",
        "description": (
            "Chain of length 1 where chain[0].validityWindow.not_after is "
            "2024-12-31T23:59:59Z (well in the past relative to the "
            "deterministic clock now=2026-05-13T18:00:00Z). chain.length=1 "
            "≤ max_depth=3 so depth passes; validity check fires before "
            "signature evaluation. Signature is nevertheless validly "
            "produced over canonicalizeJCS(link minus signature) so the "
            "validity check is demonstrably short-circuiting."
        ),
        "input": {
            "chain": [link0],
            "max_depth": 3,
            "now": FIXED_NOW,
        },
        "expected_error_code": "VALIDITY_EXPIRED",
    }


# --- Provenance ---


def provenance() -> dict:
    return {
        "generator": (
            "agentgraph-co/agentgraph scripts/gen_a2a_1496_negative_paths.py"
        ),
        "canonicalization": (
            "RFC 8785 JCS with null values preserved; byte-identical to "
            "aeoess/aps-conformance-suite "
            "fixtures/composition/a2a-1496-negative-paths/lib.ts "
            "canonicalizeJCS() on the value subset exercised by these "
            "fixtures (objects, arrays, strings, integers, ISO 8601 timestamps)"
        ),
        "signature_scheme": (
            "Ed25519 over canonicalizeJCS(link minus signature) directly, "
            "no sha256 wrap; signature serialized as hex (128 chars)"
        ),
        "delegator_delegatee_format": "Ed25519 public key hex (64 chars)",
        "field_name_convention": (
            "CTEF v0.3.2 §A: camelCase validityWindow with snake_case "
            "not_before/not_after; scope.action_categories array; "
            "chain-level max_depth; optional input.now for deterministic "
            "validity clock"
        ),
        "validator_check_order": [
            "depth", "validity (per link root→leaf)",
            "signature (per link)", "scope_narrowing (non-root)",
        ],
        "ed25519_seeds_hex": SEEDS,
        "ed25519_public_keys_hex": PUBS,
        "reference_times": {
            "not_before_valid": NOT_BEFORE,
            "not_after_valid": NOT_AFTER_VALID,
            "not_after_expired": NOT_AFTER_EXPIRED,
            "fixed_now": FIXED_NOW,
        },
        "fixture_intent": {
            "01-scope-expansion": "INVALID_CLAIM_SCOPE on chain[1] after passing depth + validity (both links) + signature (both links) + scope (chain[0] is root, skipped)",
            "02-depth-violation": "DELEGATION_DEPTH_EXCEEDED (chain.length=4 > max_depth=3) — first check in order",
            "03-signature-substitution": "INVALID_SIGNATURE on chain[1] after passing depth + validity (both links) + signature (chain[0])",
            "04-validity-expired": "VALIDITY_EXPIRED on chain[0] after passing depth",
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
