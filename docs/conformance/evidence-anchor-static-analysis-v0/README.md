# EvidenceAnchor vectors — AgentGraph static-analysis scan attestations (v0)

Conformance vectors for anchoring an AgentGraph static-analysis **scan event** as an
EvidenceAnchor (per the integration path discussed on
[microsoft/agent-governance-toolkit#3111](https://github.com/microsoft/agent-governance-toolkit/issues/3111),
following the `argentum-core` `examples/conformance/agentoracle-v1` template).

## Model

```
action_ref = SHA-256(JCS({agent_id, action_type, scope, timestamp}))   # argentum-core action-ref-v1
```

- **`agent_id`** — the scanner identity (`did:web:agentgraph.co`).
- **`action_type`** — the scanner operation (`static_analysis.scan`).
- **`scope`** — the target tool identity (MCP server URI / package ref).
- **`timestamp`** — RFC 3339 (ms), the logical scan time.

The **verdict** (`grade`, `findings`, `cve_list`, `outcome`) is kept **out of the preimage**.
That's the load-bearing design choice: `action_ref` stays stable as the correlation key across
re-scans of the same target, while the evidence it points at can change — and a verifier can
confirm *identity* (the anchor) and *evidence* (the verdict) independently, with no access to
AgentGraph's infrastructure.

## Invariants tested

1. **Re-scan idempotency** — same `{agent_id, action_type, scope, timestamp}` → **same** `action_ref`
   (`pass_clean_mcp` ≡ `rescan_same_target_stable_ref`, even though the verdict differs).
2. **Distinct events** — a later `timestamp` → **different** `action_ref` (`rescan_later_distinct_ref`).
3. **Evidence independence** — the verdict is never in the `action_ref` preimage.

## Cases

| Vector | Expectation | Notes |
|---|---|---|
| `pass_clean_mcp` | PASS | grade A, 0 critical/high |
| `fail_critical_mcp` | FAIL | 2 critical / 3 high + a CVE |
| `rescan_same_target_stable_ref` | PASS | same preimage as the clean case → identical `action_ref` |
| `rescan_later_distinct_ref` | PASS | later timestamp → distinct `action_ref` |

## Reproduce

```bash
pip install rfc8785==0.1.4
python3 verify.py     # recomputes every action_ref offline + checks the invariants
```

`action_ref` uses the same RFC 8785 canonicalizer cross-validated byte-for-byte across the
AlgoVoi corpus (253/253), so these anchors are reproducible by any independent verifier.
