# A2A #1496 Negative-Path Conformance Fixtures

**Target:** `aeoess/aps-conformance-suite#3` at `fixtures/composition/a2a-1496-negative-paths/`
**Source:** `agentgraph-co/agentgraph` → `scripts/gen_a2a_1496_negative_paths.py`
**Per:** aeoess format notes on A2A #1786 (2026-05-13 14:07Z)

## Files

| File | Triggers | Description |
|---|---|---|
| `01-scope-expansion.fixture.json` | `INVALID_CLAIM_SCOPE` | Chain of 2 links where link[1] expands the scope set granted by link[0]. Depth + validity + signature pass; scope check fires. |
| `02-depth-violation.fixture.json` | `DELEGATION_DEPTH_EXCEEDED` | Chain of 4 links with `max_depth=3`. First check in order fires; all 4 links are nevertheless validly signed + within validity. |
| `03-signature-substitution.fixture.json` | `INVALID_SIGNATURE` | Chain of 2 links where link[1]'s signature is replaced with a valid-shape Ed25519 sig over unrelated canonical bytes. Depth + validity pass; signature check fires. |
| `04-validity-expired.fixture.json` | `VALIDITY_EXPIRED` | Chain of 1 link with `validityWindow.not_after` in 2024. Depth passes; validity check fires before signature evaluation. |
| `generation-provenance.json` | — | Deterministic seeds + public keys + reference times for reproducible regeneration. |

## Reproducibility

Re-running the source script produces byte-identical fixtures:

```bash
cd agentgraph-co/agentgraph
python3 scripts/gen_a2a_1496_negative_paths.py
```

Output lands in `generated-fixtures/a2a-1496-negative-paths/`. Drop into
`aeoess/aps-conformance-suite/fixtures/composition/a2a-1496-negative-paths/`
to wire into the scaffold's `verify.ts` runner.

## Format conformance (per aeoess A2A #1786, 2026-05-13)

1. **Signature scheme:** Ed25519 over `canonicalizeJCS(link minus signature)` directly. **No sha256 wrap.** CTEF / RFC 9421 convention.
2. **Canonicalization:** RFC 8785 JCS with **null values preserved** (matches `src.signing.canonicalize_jcs_strict` byte-output; cross-verified against `trailofbits/rfc8785.py` and `@nobulex/crypto`).
3. **Field names:** `validityWindow` (camelCase) wrapping `not_before` / `not_after` (snake_case inside) per CTEF v0.3.2 §A spelling.
4. **Depth check:** chain-level `chain.length > max_depth`; **no per-link `currentDepth` / `maxDepth` fields**.
5. **Check order:** `depth → validity → signature → scope`. Each fixture exercises **exactly one** violation at the targeted check level; all earlier checks pass cleanly.

## Round-trip verification

Each fixture's signatures verify correctly per `cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PublicKey.verify()`:

| Fixture | chain[0] sig | chain[1] sig | chain[2] sig | chain[3] sig |
|---|---|---|---|---|
| `01-scope-expansion` | ✓ | ✓ | — | — |
| `02-depth-violation` | ✓ | ✓ | ✓ | ✓ |
| `03-signature-substitution` | ✓ | **✗** (substituted, by design) | — | — |
| `04-validity-expired` | ✓ | — | — | — |

The only failing signature verification is link[1] of fixture 3, which is the intended violation.

## Open question for aeoess

The exact CTEF v0.3.2 §A wire field shape (specifically: does each chain link
embed `signature` as a base64url string at the top level of the link object,
versus nested under e.g. `proof.signature`?) was inferred from your format notes
+ the closest analogue in `aeoess/agent-passport-system/fixtures/bilateral-delegation/`.

If your validator's `validateNegativePathInput()` reads signature from a
different field path, fixture regeneration is one line in `build_link()` and
re-running the script produces updated artifacts. Flagging here so the round-trip
either confirms the shape on first PR review or surfaces a one-shot field-path
correction.
