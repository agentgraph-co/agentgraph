# AgentGraph ↔ AlgoVoi — JCS RFC 8785 conformance

**Result: 253 / 253 byte-for-byte + SHA-256 checks pass across 24 anchor-set files. 0 failures.**
*(Recorded at corpus commit `f31f4af`, the pin in `fetch_vectors.sh`, which is what this runner uses.)*

> **Scope note (2026-06-24):** AlgoVoi subsequently removed the `ctef_aps_v1` set (18 of these
> checks) from their corpus to keep it scoped to AlgoVoi's *own* substrate — CTEF is AgentGraph's
> format, and our own CTEF conformance vectors live on our side
> ([`ctef-aps`](../) / the CTEF spec). The pinned `f31f4af` run above stands as recorded; against
> the *current* AlgoVoi manifest this runner reproduces the remaining ~235 checks across 22 JCS
> substrate sets identically (the substrate is unchanged). This is bilateral peer interop on the
> shared RFC 8785 substrate — credit is mutual and unchanged.

AgentGraph's production JSON canonicalizer (`rfc8785` 0.1.4 — the same library and
version used in `src/signing.py` to canonicalize every CTEF attestation, `binding_digest`,
and `action_ref`) reproduces [AlgoVoi's](https://github.com/chopmob-cloud/algovoi-jcs-conformance-vectors)
published cross-language conformance corpus exactly — both the canonical UTF-8 bytes and
their SHA-256 digests.

AlgoVoi's corpus is itself cross-validated 880/880 across eight independent JCS
implementations in eight languages. AgentGraph reproducing it bit-for-bit means an
AgentGraph attestation and an AlgoVoi receipt that canonicalize the same object produce
**identical bytes** — the precondition for bilateral composition (one verifier can hash,
sign over, or chain another's evidence without drift).

## Why it matters

AgentGraph and AlgoVoi are **two independent implementations of an IETF standard**
(RFC 8785), both anchoring on `urn:x402:canonicalisation:jcs-rfc8785-v1`. This is
*bilateral peer interop / cross-validation* — not adoption of one stack by the other.
AgentGraph imports no AlgoVoi code or corpus at runtime (0 refs in `src/`); both sides
implement the same public standard and agree at the byte level. (Conversely, AlgoVoi is
itself an independent implementer of AgentGraph's CTEF format — see the `ctef_aps_v1`
anchor set, which models AgentGraph's own `agentgraph.co/ns/trust-evidence` envelope.)

This check is the evidence that the shared substrate actually holds at the byte level,
not just on paper — across the CTEF/APS
attestation format, the `action_ref` family, AP2 open-mandate hashes, the x402 receipt
families (compliance / settlement / cancellation / refund), privacy-class declarations,
per-chain envelopes, the Payment Evidence Frame, ZKP receipts, retention chains, and the
adversarial-isolation set.

## What's in scope

The corpus also contains RFC 9421 HTTP-message-signature *proxy-chain* wire fixtures.
AgentGraph does **not** implement the RFC 9421 signing-base layer, so those are out of
scope. AgentGraph shares only the JCS RFC 8785 canonicalization substrate — which is
exactly what every vector in the 24 files below exercises.

## Reproduce

```bash
./fetch_vectors.sh          # clones AlgoVoi's corpus pinned to f31f4af, flattens into ./vectors
python3 run_conformance.py  # runs AgentGraph's rfc8785 0.1.4 against every vector
```

Requires `pip install rfc8785==0.1.4` (already an AgentGraph dependency).
`./vectors/` is fetched on demand (Apache-2.0, AlgoVoi) and is git-ignored — not vendored.

## Per-file result

| Anchor set | Checks |
|---|---|
| action_ref_exactly_once_v1 | 11/11 |
| action_ref_namespace_v0 | 8/8 |
| action_ref_transactional_v0 | 15/15 |
| adversarial_isolation_v1 | 24/24 |
| ap2_omh_v0 | 7/7 |
| cancellation_receipt_v1 | 10/10 |
| compliance_receipt_v1 | 10/10 |
| composite_trust_query_v1 | 10/10 |
| ctef_aps_v1 (aps + ctef) | 18/18 |
| epi_interop_v0 | 5/5 |
| epi_pqc_v0 | 4/4 |
| multichain_ed25519_substrate_v0 | 2/2 |
| pef_v1 | 16/16 |
| per_chain_envelope_v0 | 19/19 |
| privacy_class_v0_1 (v0 + v0.1) | 23/23 |
| refund_receipt_v1 | 10/10 |
| retention_chain_v0 | 3/3 |
| retention_chain_v1 | 14/14 |
| rfc9421_receipt_evidence_v0 | 6/6 |
| settlement_action_binding_v1 | 12/12 |
| settlement_attestation_v1 | 10/10 |
| zkp_receipt_v1 | 16/16 |
| **Total** | **253/253** |

## Scoring note (honest scope)

Each check is one (input → expected canonical bytes) or (input → expected SHA-256) pair
extracted from a vector. Adversarial *reject* vectors are scored on their authoritative
`expected_*` fields. The deliberately-stale audit-chain linkage fields
(`content_hash` / `prev_hash`) inside tamper rows are **excluded** from scoring — they are
chain-integrity metadata a verifier checks, not canonicalization-reproduction targets, and
their being broken is the point of those vectors. See `run_conformance.py` for the exact
extraction logic.

Pinned corpus: `chopmob-cloud/algovoi-jcs-conformance-vectors@f31f4af` (manifest 0.16.0).
See `receipt.json` for the machine-readable attestation in AlgoVoi's implementor format.
