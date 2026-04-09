# A2A Follow-up Replies — 2026-04-06

## Instructions

1. **Post on insumer-examples #1 FIRST** — reply to haroldmalikfrimpong-ops's comment
2. **Then reply on A2A #1672** — references the insumer-examples work

- insumer-examples #1: https://github.com/douglasborthwick-crypto/insumer-examples/issues/1
- A2A #1672: https://github.com/a2aproject/A2A/discussions/1672

---

## Post 1: insumer-examples #1 Reply

Post this as a reply to haroldmalikfrimpong-ops's comment on: https://github.com/douglasborthwick-crypto/insumer-examples/issues/1

---

@haroldmalikfrimpong-ops — thanks for the test target. Ours is public too:

```
GET https://agentgraph.co/api/v1/entities/1e7b584d-2621-47a8-a314-20b9a908353a/attestation/security
```

JWKS at [`https://agentgraph.co/.well-known/jwks.json`](https://agentgraph.co/.well-known/jwks.json), kid `agentgraph-security-v1`, EdDSA.

The interesting play: both signals in the same `trust.signals[]` array. A consuming agent gets AgentID behavioral (runtime identity + interaction patterns) and AgentGraph security posture (static source analysis) in one check. Different questions, same verification flow — fetch JWKS, verify signature, evaluate boolean checks.

Worth prototyping a combined attestation envelope that carries both. The multi-attestation format here already supports it — just two entries in the `attestations[]` array from independent issuers.

---

## Post 2: A2A #1672 Reply

Post this as a reply to haroldmalikfrimpong-ops's comment on: https://github.com/a2aproject/A2A/discussions/1672

---

@haroldmalikfrimpong-ops — agreed, static posture and runtime behavioral are different layers that both feed the same trust decision. Good framing.

We just shipped signed security attestations and posted the format on [insumer-examples #1](https://github.com/douglasborthwick-crypto/insumer-examples/issues/1) — EdDSA (Ed25519), JWKS live at [`agentgraph.co/.well-known/jwks.json`](https://agentgraph.co/.well-known/jwks.json). The payload covers scan results, finding severity counts, boolean checks (`no_critical_findings`, `has_tests`, etc.), and positive signals detected.

A consumer verifying an Agent Card could check both: AgentID for "is this agent behaving as expected at runtime?" and AgentGraph for "does the source code have known vulnerabilities?" Same `trust.signals[]` array, independent issuers, independent verification. The DID document binds both to the same identity.

Your public verify endpoint is a good test case — we could scan the AgentID source repo and produce a security attestation for it, then a verifier would have both your behavioral signal and our static posture signal for the same agent.

---

## Do NOT reply to

- **aeoess / haroldmalikfrimpong-ops DID interop discussion** — they're working through ECDSA/Ed25519 coexistence. Don't jump in unless you have something specific about DID key management to add.
- **douglasborthwick-crypto on #1628** — already handled with submission post. Wait for his response to insumer-examples.
