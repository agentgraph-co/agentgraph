# x402 endpoint-safety screen — PRE_PAYMENT_GUARD plugin (v0)

A reference implementation + conformance vectors for an **endpoint-safety** screen
under the converging x402 pre-payment guard interface
([x402-foundation/x402#2533](https://github.com/x402-foundation/x402/issues/2533)).

It's the third screen alongside evidai's **authorization** plugin and the **payload/PII**
screen: same chokepoint, orthogonal concern. This one refuses to pay an x402 endpoint that
AgentGraph has graded **critical/high** — *score before money moves.*

## Interface (matches the thread)

```
declares: ["resource_url", "safety_attestation"]          # keys_off_raw
screen(input, ctx) -> {"verdict": "admit"|"deny", "reason"?: str, "entities"?: [str]}
```

- **Deny-only, mutation-free.** It reads the supplied AgentGraph safety attestation and
  decides; it changes nothing a downstream screen sees. That purity is what makes the verdict
  byte-reproducible offline — the same property the authorization and payload screens have.
- **Pure / no network.** The endpoint's signed safety attestation is passed in as
  `input["safety_attestation"]` (the host fetches + signature-verifies it before the guard
  runs, via `agentgraph_sdk.verify`), exactly as a payload screen receives the payload.
- **Missing attestation → `admit` with `reason: "no_safety_attestation"`** (never a silent
  pass). Whether an un-attested endpoint is acceptable is the host's policy decision (a
  `require_safety` flag), the same philosophy as SafeAgent's `require_attestation`.

## The verdict is the proof, not a parallel artifact

Per @evidai's point on #2533: the guard verdict *is* the pre-execution decision a settlement
record anchors. This safety verdict is designed to be carried in AgentGraph's
[`pre-execution-verdict-v0`](../../standards/v0.4-pre-execution-verdict-v0.md) envelope —
`admission.verdict` + a `binding_digest`/`action_ref` — so a `PRE_PAYMENT_GUARD` verdict and
an `action_ref` are the decision and its proof, the same shape on both sides.

## Conformance

`safety_screen_v0.json` pins, for 5 vectors, the RFC 8785 canonical bytes + SHA-256 of the
verdict the reference screen produces. Reproduce:

```bash
pip install rfc8785==0.1.4
python3 verify_fixture.py     # 5/5 byte-for-byte
```

| Vector | Verdict |
|---|---|
| admit_clean (grade A, 0 critical/high) | admit |
| deny_critical (2 critical) | deny |
| deny_high (4 high) | deny |
| admit_no_attestation (un-attested) | admit + reason |
| deny_critical_and_high | deny + entities |

Same byte-verifiable pattern AlgoVoi uses (we cross-validate their JCS corpus 253/253) — so
this screen's verdict is reproducible offline by any implementation, no trust in ours.
