# Semantic Divergence Boundary v0

**Status:** v0 draft, AEOESS Consilium Pass Candidate 1 substrate
**Owner:** AgentGraph (kenneives)
**Co-author (discrimination-tuple section §2):** AlgoVoi (chopmob-cloud) per A2A #1734 May 14 framing + May 23 co-authorship request
**Target:** ship before May 26 substrate window close; published artifact for AEOESS synthesis matrix (May 27-28 publication)

---

## Purpose

This document specifies the **semantic divergence boundary**: the condition where two attestations produce byte-identical canonical bytes under JCS-RFC 8785 canonicalization yet encode semantically distinct claims. It is the substrate-level answer to AEOESS Consilium Pass Candidate 1 ("Semantic divergence under byte-match identity").

The boundary matters because byte-match validation is necessary but not sufficient for cross-implementation interop. Two implementations can independently produce identical canonical bytes from semantically distinct inputs — and a verifier that checks only canonical-bytes equality will accept both as equivalent. The divergence surfaces downstream as silent verifier disagreement on the meaning of the attestation.

This is the gap the discrimination-tuple injectivity rule closes at the substrate layer.

---

## §1 — The gap as observed

### §1.1 In substrate-conformant claims

Two URN-namespaced attestations may carry distinct semantic claims while producing identical canonical-byte representations under JCS-RFC 8785 + lowercase-hex SHA-256. The substrate layer has no semantic notion of what each URN means; it only canonicalizes bytes. A verifier that operates at the substrate layer accepts both as conformant, leaving the semantic resolution to downstream consumers — which may interpret them inconsistently.

### §1.2 In production agent populations

Distinct from the abstract canonicalization case: production agent populations contain attestations that are byte-conformant under substrate canonicalization rules but semantically distinct in their runtime behavior. *State of Agent Security 2026* (AgentGraph, published 2026-05-12; full report at https://agentgraph.co/state-of-agent-security-2026) measured this directly across ~35,000 agents scanned across MCP Registry, OpenClaw skills marketplace, npm/PyPI agent packages, and AI-generated Solidity from Microsoft-backed Dreamspace. **12% of OpenClaw skill repositories with valid `SKILL.md`, byte-clean canonical serialization, and live `did:web` resolution were classified malware on static analysis.** Same canonical shape, same byte-conformance, radically distinct runtime semantics.

The empirical distribution shows the gap is not a theoretical curiosity. It is a production-frequency failure mode at agent-population scale.

---

## §2 — The discrimination-tuple injectivity rule

**Authorship note:** the discrimination-tuple injectivity formulation in this section originates with AlgoVoi (chopmob-cloud), posted in A2A #1734 on 2026-05-14, and is incorporated here with named co-authorship per his May 23 request on A2A #1734. AlgoVoi additionally holds the verifier-side production angle from `/compliance/screen` — referenced in §4 as the third leg of the closure.

### §2.1 Statement

For every URN-namespaced attestation row in the v0.3.3 cross-extension matrix (or any downstream extension thereof), the tuple `(claim_type, evidenceType, source_provider_did)` SHALL be unique. No two URNs in the matrix may claim the same triple.

Where:

- `claim_type` ∈ `{identity, transport, authority, continuity}` — the closed CTEF v0.3.1+ set
- `evidenceType` ∈ Dominion taxonomy values `{behavioral, regulatory, self-attested, third-party, cryptographic, observational}`
- `source_provider_did` is the URI-form DID of the attestation issuer (e.g. `did:web:registrar.example.com`)

### §2.2 Why this closes the gap

Two substrate-conformant URNs producing identical canonical bytes for the same `(claim_type, evidenceType, source_provider_did)` tuple are by construction asserting the same semantic claim, so substrate-level byte-match equivalence is also semantic equivalence. The verifier's "accept on byte-match" decision is semantically safe.

Two URNs producing identical canonical bytes for *different* `(claim_type, evidenceType, source_provider_did)` tuples are asserting *different* semantic claims, and the substrate verifier MUST detect the discrimination-tuple mismatch as a canonical signal of semantic divergence — even when the canonical-bytes layer reports match. The tuple-mismatch becomes the audit signal that converts the silent verifier-disagreement gap into a structured rejection at substrate layer.

Injectivity is enforced via cross-impl JCS_hash comparison at substrate-validation time. The check is cheap: compute the JCS_hash of the discrimination tuple alongside the JCS_hash of the full envelope; reject any pair where envelope hashes match but tuple hashes differ.

---

## §3 — Three worked examples

Each example surfaces the discrimination-tuple gap from concrete v0.3.3 row-classification work, demonstrates how the injectivity rule resolves it, and names the implementer who surfaced the case.

### §3.1 Erik Newton's row #7 reclassification

**Surfaced by:** eriknewton (Concordia Protocol), A2A #1734 on 2026-05-21.

The original v0.3.3 scaffold placed row #7 as `urn:concordia:attestation` tagged `(authority, third-party)` per the HAHS schema attribution. Erik analyzed Concordia v0.5.1 §9.6.2 (Reputation Attestation) vs §9.6.4b (ApprovalReceipt) and concluded the original URN named the wrong artifact: §9.6.2 Reputation Attestation is bilateral peer-on-peer (countersigned by both parties before validity), not third-party authority. The (authority, third-party) tuple did not match the artifact under it.

The injectivity rule catches the mismatch concretely: a verifier consuming a `(authority, third-party, did:web:hivetrust.tech)` tuple expects a third-party attestation, but a Concordia §9.6.2 envelope would byte-match a §9.6.4b envelope under canonical serialization while semantically asserting a different claim class.

Erik's resolution: rename the URN to `urn:concordia:receipt` (correct artifact: §9.6.4b ApprovalReceipt — HITL authority decision on a negotiation event, signed by a third party to the bilateral negotiation), preserve the HAHS schema attribution (HiveTrust attests hire-time authority on behalf of a procurement principal), and reserve `urn:concordia:attestation` as a follow-on row 7b at `(continuity, behavioral)` for the §9.6.2 Reputation Attestation case (which composes cleanly via `source_provider_did` distinguishing Concordia from Nobulex from Dominion).

The discrimination-tuple injectivity rule made the mismatch detectable at substrate-validation time, before the misclassified row could ship downstream.

### §3.2 Row #4/#5 (continuity, behavioral) ambiguity resolution via `source_provider_did`

**Surfaced during:** v0.3.3 cross-extension matrix authoring, late May 2026.

Row #4 (`urn:nobulex:receipt`, Nobulex AAIF, arian-gogani) and Row #5 (`urn:observatory:eval`, Dominion Observatory, vdineshk) both occupy the `(continuity, behavioral)` cell. Without a third tuple component, the matrix would carry two semantically distinct attestation classes — Nobulex's bilateral behavioral receipts vs Dominion's empirical interaction-success-rate observations — under a single `(claim_type, evidenceType)` pair, and the substrate verifier would have no signal to distinguish them at canonical-bytes equality.

The injectivity rule resolves the ambiguity by enforcing tuple uniqueness only over the full three-component tuple. `source_provider_did` discriminates: `did:web:nobulex.com` vs `did:web:dominionobservatory.com` are distinct, so the tuples `(continuity, behavioral, did:web:nobulex.com)` and `(continuity, behavioral, did:web:dominionobservatory.com)` are non-colliding even though they share the first two components.

A consumer receiving a `(continuity, behavioral)` attestation now has a guaranteed canonical anchor — the issuer's DID — for routing the semantic interpretation to the correct registrar's documentation. The substrate gives the verifier a deterministic signal even when the claim_type + evidenceType pair is reused.

### §3.3 Row #8 `urn:arkforge:verdict` open architectural question

**Surfaced by:** ArkForge (desiorac, lawcontinue) via the `tier_upgrade_proof` reference fixture on A2A #1734, May 19.

ArkForge contributed a `tier_upgrade_proof` fixture tagged `(authority, tier_upgrade)` with `claim_subtype` semantics — the gateway emits a verdict (TRUSTED → NEUTRAL → WATCH → QUARANTINE) signed by `did:web:trust.arkforge.tech` with embedded JWS over a JCS-canonical preimage. The architectural open question raised in the v0.3.3 matrix design: does this land as the 8th matrix row (gateway-verdict layer composing with the 7 substrate-emitter rows) or as a companion gateway-fixture set (separate directory, cleaner separation but loses single-table composition view)?

The discrimination-tuple injectivity rule shapes the answer. If gateway verdicts land as a matrix row, the tuple `(authority, cryptographic, did:web:trust.arkforge.tech)` is canonically distinguished from substrate-emitter authority rows by `source_provider_did` (the gateway's DID, not the underlying emitter's). The 7 substrate-emitter rows + 1 gateway-verdict row compose without tuple collision — the injectivity rule keeps them semantically distinct even when they share `(authority, cryptographic)` as the first two components.

If gateway verdicts live in a companion set, they're outside the matrix and the discrimination tuple does not enforce injectivity across the matrix/companion boundary; verifier behavior depends on whether the consumer reads from one source or both. The cleaner option is to keep them in the matrix and rely on `source_provider_did` to discriminate — which the injectivity rule supports natively.

This is the open architectural question the rule directly informs. desiorac + lawcontinue input still invited.

---

## §4 — Verifier-side production angle (AlgoVoi)

The discrimination-tuple injectivity rule has a concrete production verifier instance: AlgoVoi's `/compliance/screen` endpoint, which accepts byte-conformant input and produces an ALLOW / REFER / DENY classification. A tuple mismatch between the asserted `(claim_type, evidenceType, source_provider_did)` of the input and what `/compliance/screen` recognizes as a valid known-issuer triple is exactly the failure mode the screening verifier MUST catch before admission. The verifier rejects rather than coerces — same fail-closed discipline as Substrate Rule 4 of the AlgoVoi canonicalisation discipline (x402-foundation/x402 #2326 v3).

The three legs of the Candidate 1 substrate closure:

1. **Formalism** (AlgoVoi): discrimination-tuple injectivity rule, originating A2A #1734 May 14, formalized in §2 above
2. **Distribution** (AgentGraph): 12% conformance-clean-but-malicious in OpenClaw at scan time, *State of Agent Security 2026*, §1.2 above
3. **Verifier-instance** (AlgoVoi): `/compliance/screen` as the production verifier that converts tuple-mismatch into structured rejection

The three legs together convert "semantic divergence is theoretically possible" into "semantic divergence is empirically measurable at known frequency, with a substrate-layer signal that catches it at known verifier instance." That is the substrate evidence shape Candidate 1 asked for.

---

## §5 — Cross-references

- **Substrate canonicalization:** x402-foundation/x402 PR #2436 (AlgoVoi canonicalisation discipline v3), 5-impl × 53-vector validation matrix in-tree at `agentgraph-co/agentgraph/tests/cross-impl/`
- **L1-L4 vocabulary anchor:** `crosswalk/agentgraph.yaml` in `aeoess/agent-governance-vocabulary` (merged); shared L1-L4 trust level taxonomy where Candidate 1 (semantic divergence) and Candidate 3 (cross-jurisdictional portability) intersect
- **Scan corpus full report:** `agentgraph.co/state-of-agent-security-2026` (May 12, 2026)
- **v0.3.3 cross-extension matrix:** `docs/standards/v0.3.3-working-doc.md#cross-extension-fixture-matrix` in this repo, branch `v0.3.3-cross-extension-matrix`
- **AlgoVoi original discrimination-tuple framing:** A2A #1734 comment, 2026-05-14 (and follow-up clarifications through 2026-05-23)

---

## §6 — What this document does NOT do

- Does not propose a new closed-set extension to `claim_type` or `evidenceType`. The `(authority, identity, continuity, transport)` set and Dominion `evidenceType` taxonomy stay as-is. The injectivity rule operates over the existing tuple shape.
- Does not specify the verifier's downstream action on tuple-mismatch detection (reject vs warn vs surface to operator). That's a verifier-policy decision, not a substrate-discipline decision.
- Does not enumerate every possible semantic-divergence case — that's a moving target as the row-set extends. The discrimination-tuple injectivity rule is the substrate-layer invariant; specific row classifications evolve under it.
- Does not address verifier-confusion cases where the same canonical bytes encoded different semantic claims and a verifier missed the gap in production. That is a richer-substrate problem AEOESS identified as the "thinnest substrate" sub-case of Candidate 1; this document provides the structural primitive (injectivity rule) on which such cases can be classified, but does not catalog them.

---

## §7 — Synthesis matrix attribution

For the AEOESS synthesis matrix record:

| Component | Originating contribution | Submitted substrate |
|---|---|---|
| Discrimination-tuple injectivity rule (formalism) | AlgoVoi (chopmob-cloud), A2A #1734 May 14 + May 23 co-authorship | This document §2 |
| Scan-corpus distribution (empirical) | AgentGraph (kenneives), *State of Agent Security 2026* May 12 | This document §1.2 |
| `/compliance/screen` verifier-instance (production) | AlgoVoi (chopmob-cloud) | Referenced §4; live endpoint |
| Worked examples (operational) | eriknewton (row #7), arian-gogani + vdineshk (row #4/#5), desiorac + lawcontinue (row #8) | This document §3 |

The composition is the substrate: formalism + distribution + verifier-instance + operational examples, with named per-component originating contributors and per-row substrate from named implementers.

cc @aeoess for the synthesis record. Reference implementations cited by URL per the originating-contribution discipline; no consolidation into single-author framing.
