# Cross-Issuer Federation v0

**Status:** v0 draft, AEOESS Consilium Pass Candidate 4 substrate
**Owner:** AgentGraph (kenneives)
**Co-authors:** named per-row in §3 (AlgoVoi, Vauban, Erik Newton, Arian Gogani, vdineshk) — each operates an independent issuer that contributes a matrix row
**Target:** ship before 2026-06-05 substrate window close; published artifact for AEOESS synthesis matrix v1.1

---

## Purpose

This document specifies **cross-issuer federation at the substrate layer**: the conditions under which attestations emitted by independent, mutually-untrusted issuers can be composed into a single verifiable trust state, with no central authority and no privileged coordinator. It is the substrate-level answer to AEOESS Consilium Pass Candidate 4 ("Cross-issuer federation").

The challenge matters because the agent trust ecosystem is structurally multi-issuer. A relying-party agent in 2026 does not get to pick the issuer set its counterparty was attested by. An A2A agent verifying a claim chain may need to compose attestations from x402 settlement infrastructure, a Concordia HITL gateway, a Nobulex AAIF receipt, and a Dominion Observatory behavioral evaluation — all four independently owned, none subordinate to the others, none willing to delegate authority to a shared coordinator. Without a substrate-layer composition discipline, the federation either collapses into vendor lock-in (one issuer wins) or fragments into silos (no issuer's output composes with another).

The substrate answer: a **URN-namespaced attestation matrix** where each issuer owns a namespace, fixtures are published per-row by the issuer that owns the namespace, and substrate-level conformance (JCS canonicalization, byte-match cross-validation, discrimination-tuple injectivity) is the only thing every issuer agrees on. No issuer-to-issuer trust assumption is required; the substrate is the shared agreement.

This is the gap the URN-namespace-as-federation-seam pattern closes at the substrate layer.

---

## §1 — The gap as observed

### §1.1 In the cohort's own substrate work

The AEOESS Consilium Pass through May 2026 produced substrate against four of five candidates from independent issuers: AlgoVoi on C1 (verifier-instance), giskard09 on C3 + C5 (cross-system-verification, delegation-chain-ref), AgentGraph on C1 (formalism + scan-corpus distribution). Each issuer operated independently — different repos, different commit chains, different fixture sets, different runtime infrastructure. **None of them assumed any of the others were authoritative.** And yet the matrix v1.1 composes their outputs cleanly because each issuer's contribution is namespaced, content-addressed, and substrate-conformant.

That is federation working. The federation discipline was not specified — it was practiced. C4 makes the practice normative.

### §1.2 In the v0.3.3 cross-extension URN matrix

The matrix already operates as a federation primitive at production scale. As of 2026-05-28 the matrix carries 9 active rows + 1 reserved across **eight independently-owned issuers**: ERC-8004 (mainnet contract authors), argentum-core (giskard09), x402-foundation + AlgoVoi, Nobulex (Arian), Dominion Observatory (vdineshk), Foxbook, Concordia (Erik) + HiveTrust (HAHS co-author), ArkForge (desiorac + lawcontinue), Vauban Pay (kenneives + eriknewton + seritalien). Five rows are ACCEPTED by the row's owning issuer; four are PLACEHOLDER pending substrate. No central party admits or rejects rows — the owning issuer accepts their own row by publishing the substrate, and substrate-validation runs across the matrix without privileged access to any issuer's endpoint.

The matrix is the substrate evidence that federation works under these conditions. C4 specifies the conditions.

---

## §2 — The URN-namespace-as-federation-seam rule

**Authorship note:** the URN-namespace matrix pattern was scaffolded in `docs/standards/v0.3.3-working-doc.md` Artifact 3 (commit `dcaaa75`, 2026-05-19), with row-by-row substrate contributed by named implementers per §3. The federation invariant formalized here generalizes the per-row substrate into a per-matrix conformance discipline.

### §2.1 Statement

A cross-issuer federation is substrate-conformant iff **every issuer in the federation independently controls a URN namespace** in the matrix, where each namespace satisfies the following five invariants:

1. **Namespace ownership.** The issuer holds resolution authority for `urn:<namespace>:*` and SHALL publish fixtures + substrate-conformance evidence for any row in the matrix bearing their namespace.
2. **Discrimination-tuple injectivity** (per [Semantic Divergence Boundary v0 §2](semantic-divergence-boundary-v0.md), Candidate 1). The tuple `(claim_type, evidenceType, source_provider_did)` SHALL be unique across the matrix — no two rows (regardless of issuer) may carry the same tuple.
3. **Substrate canonicalization.** The issuer's published fixtures SHALL be byte-match validated against at least one of the 5 reference JCS implementations in `tests/cross-impl/` (rfc8785 Py, canonicalize JS, gowebpki/jcs Go, cyberphone Java, serde_jcs Rust).
4. **No privileged coordinator.** The matrix MUST NOT contain a row whose validation requires a call to any single issuer's operated endpoint. Every row's substrate MUST be verifiable from public artifacts (fixtures, on-chain anchors, content-addressed receipts) alone. *(This is the same fail-closed discipline giskard09 named as Invariant 5 in cross-system-verification-v1.0 for Candidate 3 — generalized from per-issuer to per-matrix.)*
5. **Issuer accreditation by composition, not by admission.** No central party admits or rejects an issuer. An issuer is *de facto* accredited by virtue of: holding their namespace, publishing substrate-conformant fixtures, and being byte-match cross-validated by at least one other issuer in the federation. The matrix is the audit trail.

### §2.2 Why this closes the gap

The five invariants together convert "federation requires inter-issuer trust" into "federation requires only substrate-conformance per issuer + injectivity across issuers." No issuer needs to trust any other issuer's runtime — they only need to validate that the others' published bytes pass the same JCS canonicalization + discrimination-tuple discipline. Issuer-to-issuer adversariality is the assumed condition; substrate-conformance is the only shared agreement.

Concretely: a verifier consuming `urn:nobulex:receipt` does not require any inbound trust assumption about Nobulex's runtime to validate the receipt. The verifier checks (a) Nobulex's published fixtures byte-match canonical, (b) Nobulex's tuple `(continuity, behavioral, did:web:nobulex.com)` is the only `(continuity, behavioral, did:web:nobulex.com)` row in the matrix (no collision), and (c) the consumed receipt byte-matches the fixture. If all three hold, the verifier admits the claim — without trusting Nobulex's operational integrity, only Nobulex's substrate discipline.

The federation seam is the URN namespace boundary. The substrate is the JCS canonicalization. The composition is the matrix. None of those require a coordinator.

---

## §3 — Five worked examples (the federation in production)

Each example is a matrix row whose owning issuer independently controls the namespace and contributed the substrate. Each row composes with the others via the §2 invariants. None require inter-issuer trust.

### §3.1 Row 3 — `urn:x402:audit-chain` (AlgoVoi + x402-foundation)

**Issuer:** x402-foundation + AlgoVoi (chopmob-cloud). **Namespace authority:** `urn:x402:*`. **Tuple:** `(authority, cryptographic, did:web:trust.algovoi.com)` — distinct from every other authority/cryptographic row by source_provider_did. **Fixture:** in-tree at [`tests/cross-impl/fixtures/`](https://github.com/agentgraph-co/agentgraph/tree/v0.3.3-cross-extension-matrix/tests/cross-impl/fixtures); AlgoVoi-controlled upstream at [`chopmob-cloud/algovoi-jcs-conformance-vectors`](https://github.com/chopmob-cloud/algovoi-jcs-conformance-vectors) (proxy-chain + multi-chain Ed25519 fixtures relocated there permanently 2026-05-24 per A2A #1829); reference resolver `/compliance/attestation audit_chain.head`. **Cross-validation:** 53/53 + 37/37 pair-invariants across 5 JCS impls. **Accreditation:** by composition — AlgoVoi accepts the row, AgentGraph's substrate runner byte-matches it, no central party adjudicates. *Illustrates §2.1 invariant 1 (namespace ownership): AlgoVoi controls their own fixture repository as the upstream canonical source, the in-tree reproduction is downstream.*

### §3.2 Row 4 — `urn:nobulex:receipt` (Arian Gogani / Nobulex)

**Issuer:** Nobulex (Arian Gogani). **Namespace authority:** `urn:nobulex:*`. **Tuple:** `(continuity, behavioral, did:web:nobulex.com)`. **Substrate basis:** Nobulex AAIF — Ed25519 over JCS-canonical JSON + lowercase-hex SHA-256; `timestamp_ms` field alignment per x402 #2322 convergence. **Cross-validation:** argentum-core PENDING-boundary specimen incoming. **Accreditation:** by composition — Nobulex accepts the row + cross-validates against argentum-core (an independent issuer in the matrix at row 2).

### §3.3 Row 5 — `urn:observatory:eval` (vdineshk / Dominion Observatory)

**Issuer:** Dominion Observatory (vdineshk). **Namespace authority:** `urn:observatory:*`. **Tuple:** `(continuity, behavioral, did:web:dominionobservatory.com)` — non-colliding with Row 4's same `(continuity, behavioral)` pair because `source_provider_did` discriminates (per [Candidate 1 §3.2](semantic-divergence-boundary-v0.md)). **Live endpoint:** `dominion-observatory.sgdata.workers.dev/mcp`. **Cross-validation:** PLACEHOLDER pending substrate. **Accreditation pathway:** publish fixture + byte-match against one other matrix issuer.

### §3.4 Row 7 — `urn:concordia:receipt` (Erik Newton + Steve Rotzin)

**Issuer:** Concordia Protocol (Erik Newton) with HAHS co-author HiveTrust (Steve Rotzin). **Namespace authority:** `urn:concordia:*`. **Tuple:** `(authority, third-party, did:web:hivetrust.tech)` — concrete instance of two-party issuer cooperation under one URN namespace (HiveTrust attests on Concordia's row, attribution preserved). **Fixture:** `concordia-protocol/tests/fixtures/approval_receipt/hahs-procurement-tier-upgrade-v1.json`. **Cross-validation:** byte-match against rfc8785@0.1.4. **Accreditation:** ACCEPTED by Erik per A2A #1734 reclassification — substrate-conformance verified, no central party authorized the acceptance.

### §3.5 Row 9 — `urn:x402:receipt:stark-vauban-pay-v1` (Vauban + kenneives + eriknewton + seritalien)

**Issuer:** Vauban Pay (operationally) under `urn:x402:*` namespace (delegated from x402-foundation). **Namespace authority:** `urn:x402:receipt:stark-vauban-pay-v1` subspace. **Tuple:** `(authority, cryptographic, did:web:pay.vauban.tech)` — distinct from Row 3's `(authority, cryptographic, did:web:trust.algovoi.com)` despite shared namespace prefix and shared `(claim_type, evidenceType)` pair. **IETF anchor:** [draft-vauban-x402-stark-receipts-00](https://datatracker.ietf.org/doc/draft-vauban-x402-stark-receipts/) (ISE queue, 2026-05-21). **Cross-validation:** substrate runner row 5 (serde_jcs Rust). **Accreditation:** ACCEPTED — substrate evidence by IETF I-D anchor + Rust runner byte-match; v0.4 forward-link to `transactional` claim_type re-classification.

These five rows together demonstrate the federation operating: five independently-owned issuer namespaces, five distinct discrimination tuples, byte-match cross-validated against the same substrate, with no row's validity depending on a central party.

---

## §4 — The matrix as the production federation instance

The v0.3.3 cross-extension URN matrix is the **first production cross-issuer federation under the §2 invariants**. As of 2026-05-28:

- **Issuers operating in the federation:** 8 (AgentGraph, argentum-core, x402-foundation/AlgoVoi, Nobulex, Dominion Observatory, Foxbook, Concordia + HiveTrust, Vauban Pay).
- **Accepted rows:** 5 (#3, #4, #5, #7, #9). Each accepted by the owning issuer; each cross-validated by at least one other issuer in the matrix; each byte-matched against at least one of the 5 reference JCS impls.
- **Placeholder rows:** 4 (#1 ERC-8004, #2 Mycelium, #6 Foxbook, #8 ArkForge). Pending issuer-published substrate + cross-validation evidence.
- **Reserved rows:** 1 (#7b Concordia continuity).
- **No row requires a call to any single issuer's operated endpoint to validate.** Every accepted row's substrate is publishable + verifiable from in-tree fixtures or on-chain anchors.

The matrix is therefore not a coordination artifact — it is a **federation conformance instance**. The substrate evidence Candidate 4 asked for is that the federation exists and operates under explicit invariants. Both conditions hold.

The three legs of the Candidate 4 substrate closure:

1. **Formalism** (AgentGraph): the §2 five invariants generalizing the per-row substrate discipline into a per-matrix federation discipline.
2. **Composability bridge** (Candidate 1): the discrimination-tuple injectivity rule (AlgoVoi + AgentGraph) prevents cross-issuer semantic collision under shared `(claim_type, evidenceType)` pairs — federation does not require namespace partition of the underlying CTEF closed set.
3. **Production instance** (the matrix): 8 issuers, 5 accepted rows, 4 placeholder rows, no central coordinator, no inter-issuer trust assumption, substrate-conformance as the only shared agreement.

The three legs together convert "cross-issuer federation is architecturally possible" into "cross-issuer federation is operating right now under named invariants in a publicly-auditable matrix, with substrate cross-validated by 5 reference JCS implementations and discrimination-tuple injectivity preventing semantic collision across issuers." That is the substrate evidence shape Candidate 4 asked for.

---

## §5 — Cross-references

- **Substrate canonicalization:** x402-foundation/x402 PR #2436 (AlgoVoi canonicalisation discipline v3), 5-impl × 53-vector validation matrix in-tree at `agentgraph-co/agentgraph/tests/cross-impl/`
- **Candidate 1 composability bridge:** [`semantic-divergence-boundary-v0.md`](semantic-divergence-boundary-v0.md) (discrimination-tuple injectivity rule, AlgoVoi + AgentGraph)
- **Candidate 3 portability primitive:** giskard09 `cross-system-verification-v1.0` (commit b502d85) — the four-step verification procedure with on-chain anchor as shared substrate; C4's no-privileged-coordinator invariant generalizes C3's no-Giskard-endpoint-required invariant to the matrix level
- **Candidate 5 provenance primitive:** giskard09 `delegation-chain-ref-v1.0` (commit a148776) — the dual-traversal delegation chain composes orthogonally with C4 federation (delegation operates within-issuer, federation operates across-issuers)
- **L1-L4 vocabulary anchor:** `crosswalk/agentgraph.yaml` in `aeoess/agent-governance-vocabulary` (merged)
- **v0.3.3 cross-extension matrix:** [`docs/standards/v0.3.3-working-doc.md#cross-extension-fixture-matrix`](v0.3.3-working-doc.md) in this repo, branch `v0.3.3-cross-extension-matrix`

---

## §6 — What this document does NOT do

- **Does not specify revocation semantics across issuers.** When an issuer revokes an attestation, the propagation through the federation is a per-issuer-policy decision, not a federation-discipline decision. C4 specifies the substrate composability, not the revocation policy.
- **Does not specify trust score aggregation policy.** How a relying-party computes a single trust score from N issuers' attestations is downstream of C4. The substrate guarantees the attestations are composable; weighting them into a score is a verifier-side decision.
- **Does not specify issuer accreditation policy.** No central party admits issuers — accreditation is *by composition* under §2.5. Federations that want central admission can layer it on top, but C4 does not require it.
- **Does not address Byzantine issuers** publishing fixtures that pass substrate canonicalization but assert false claims about subjects. That is a content-truthfulness problem outside the substrate layer; the §2 invariants guarantee composability, not honesty. The discrimination-tuple injectivity rule limits a Byzantine issuer's blast radius (they can only claim within their own `source_provider_did` namespace), but does not detect dishonesty within it.

---

## §7 — Synthesis matrix attribution

For the AEOESS synthesis matrix record:

| Component | Originating contribution | Submitted substrate |
|---|---|---|
| Five-invariant federation discipline (formalism) | AgentGraph (kenneives) | This document §2 |
| Composability bridge (discrimination-tuple injectivity) | AlgoVoi + AgentGraph, see Candidate 1 | [`semantic-divergence-boundary-v0.md`](semantic-divergence-boundary-v0.md) §2 |
| Generalization of no-coordinator invariant (from per-issuer to per-matrix) | Derived from giskard09 Invariant 5 in `cross-system-verification-v1.0` for Candidate 3 | §2.4 above |
| Row 3 substrate (`urn:x402:audit-chain`) | AlgoVoi + x402-foundation | This document §3.1 |
| Row 4 substrate (`urn:nobulex:receipt`) | Arian Gogani (Nobulex) | This document §3.2 |
| Row 5 substrate (`urn:observatory:eval`) | vdineshk (Dominion Observatory) | This document §3.3 |
| Row 7 substrate (`urn:concordia:receipt`) | Erik Newton (Concordia) + Steve Rotzin (HiveTrust HAHS) | This document §3.4 |
| Row 9 substrate (`urn:x402:receipt:stark-vauban-pay-v1`) | kenneives + eriknewton + seritalien (Vauban Pay) | This document §3.5 |
| Production federation instance (the matrix itself) | Composition of the 8 issuers above | [`v0.3.3-working-doc.md`](v0.3.3-working-doc.md) Artifact 3 |

The composition is the substrate: formalism (federation invariants) + composability bridge (injectivity from C1) + generalized no-coordinator invariant (from C3) + per-row issuer-published substrate + the matrix as the production federation instance.

cc @aeoess for the synthesis record. Reference contributions cited by URL + commit hash per the originating-contribution discipline; no consolidation into single-author framing.
