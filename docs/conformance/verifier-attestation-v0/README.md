# pre-execution-verdict-v0 — verifier-side reference fixture (AgentGraph)

AgentGraph's canonical, byte-reproducible reference fixture for the
**`pre-execution-verdict-v0`** verifier-attestation envelope synthesized on A2A
[#1920](https://github.com/a2aproject/A2A/discussions/1920)
(spec: [`docs/standards/v0.4-pre-execution-verdict-v0.md`](../../standards/v0.4-pre-execution-verdict-v0.md)).

The verifier produces a signed admission object **before** the gateway mints/reserves.
This fixture is the spec author's reference: four scenarios, each a compact EdDSA JWS over
the JCS-canonical envelope, verifiable offline against the embedded JWKS — and byte-matched
against the independent implementations in the cohort.

## Run it (zero dependencies, Node ≥ 18)

```
node verify_fixture.mjs       # verifies the 4 vectors against the JWKS + recomputes every binding_digest
node cross_impl_check.mjs      # recomputes other impls' binding_digests with this construction
```

Expected:
```
✓ 34/34 assertions pass — agentgraph-pre-execution-verdict-v0
✓ 11/11 cross-impl binding_digests byte-match this reference
```

## The four scenarios
| scenario | verdict | reason_code |
|---|---|---|
| `admit` | admit | ok |
| `scope-deny` | deny | scope_denied |
| `limit-deny` | deny | limit_exceeded |
| `dual-approval-flag` | flag | dual_approval_required |

## Construction (the byte-match bar)
- **`binding_digest` = `sha256(JCS({amount_usd, charge_ref, nonce, subject_did}))`** —
  RFC 8785 JCS, lowercase-hex SHA-256. Byte-identical to the converged gateway construction.
- **JWS** = compact EdDSA over `JCS(header).JCS(payload)`, `payload = JCS(core)`; verified
  against the embedded `jwks` (kid `agentgraph-verifier-v0`). No network, no trust in the producer.
- **`action_ref`** = `lowercase-hex(SHA-256(JCS({agent_id, action_type, scope, timestamp})))` per
  [draft-giskard-aeoess-action-ref §3](https://github.com/giskard09/draft-giskard-aeoess-action-ref)
  (timestamp = RFC 3339 millisecond string). Recomputable from `binding.action_ref_preimage`;
  **`action_ref_method`** names the derivation. Verified to reproduce the draft's Appendix A Vector 1.
- **`key_source`** ∈ `{inline, cache, resolver}`; `cache` is a derivation (population event auditable),
  per [#1829](https://github.com/a2aproject/A2A/issues/1829).

## Cross-implementation byte-match (`cross_impl_check.mjs`)
Recomputing the published digests of two independent implementations with this exact
construction — **11/11 byte-identical**:
- **Verifier-side** — [`haroldmalikfrimpong-ops/agentid`](https://github.com/haroldmalikfrimpong-ops/agentid) `ctef-verifier-attestation/v0.1` — 5/5 (live example + 4 scenarios).
- **Gateway-side** — [`evidai/agent-payment-mcp`](https://github.com/evidai/agent-payment-mcp) `gated-preflight-v1` — 6/6 (incl. decimal amounts).
- **Exactly-once guard** — [`azender1/SafeAgent`](https://github.com/azender1/SafeAgent) `exactly-once-v1` keys on the same `action_ref`.

Three mutually-untrusting implementations, one construction, byte-reproducible end to end:
**verifier admission (this) → gated reserve/confirm (evidai) → exactly-once execution (azender1).**
