# A2A trust.signals[] — AgentGraph Signal Provider Submission

## Instructions

1. **Post on [insumer-examples #1](https://github.com/douglasborthwick-crypto/insumer-examples/issues/1) FIRST** — copy the "insumer-examples #1 Comment" section below
2. **Then reply on [A2A #1628](https://github.com/a2aproject/A2A/discussions/1628)** — copy the "#1628 Reply" section below
3. Order matters — Douglas will click through to insumer-examples from your #1628 reply

---

## Post 1: insumer-examples #1 Comment

Post this as a comment on: https://github.com/douglasborthwick-crypto/insumer-examples/issues/1

---

## AgentGraph — Security Posture Attestation

**Issuer:** AgentGraph ([agentgraph.co](https://agentgraph.co))
**Dimension:** Security Posture — has this agent's source code been scanned for vulnerabilities, and what is the severity profile of findings?
**Algorithm:** EdDSA (Ed25519)
**JWKS:** [`https://agentgraph.co/.well-known/jwks.json`](https://agentgraph.co/.well-known/jwks.json)
**kid:** `agentgraph-security-v1`

### Signed payload fields

| Field | Description |
|-------|-------------|
| `scan.result` | `clean` / `warnings` / `critical` |
| `scan.findings.{critical,high,medium,total}` | Finding counts by severity |
| `scan.positiveSignals[]` | Security best practices detected (auth, rate limiting, input validation, etc.) |
| `scan.checks.no_critical_findings` | Boolean — no critical-severity findings |
| `scan.checks.no_high_findings` | Boolean — no high-severity findings |
| `scan.checks.has_readme` | Boolean |
| `scan.checks.has_license` | Boolean |
| `scan.checks.has_tests` | Boolean |
| `scan.filesScanned` | Number of files analyzed |
| `scan.framework` | Detected framework (mcp, langchain, crewai, etc.) |
| `trust.overall` | Composite trust score (0.0–1.0) |
| `trust.scanComponent` | Scan-only component of trust score |
| `expiresAt` | 24-hour TTL |

### Live endpoint

```
GET https://agentgraph.co/api/v1/entities/{entity_id}/attestation/security
```

Any scanned entity on the platform returns a signed attestation at this URL.

### Sample signed payload

```json
{
  "payload": {
    "@context": "https://schema.agentgraph.co/attestation/security/v1",
    "type": "SecurityPostureAttestation",
    "issuer": {
      "id": "did:web:agentgraph.co",
      "name": "AgentGraph",
      "url": "https://agentgraph.co"
    },
    "subject": {
      "id": "did:web:agentgraph.co:entities:1e7b584d-2621-47a8-a314-20b9a908353a",
      "entity_id": "1e7b584d-2621-47a8-a314-20b9a908353a",
      "display_name": "Design Bridge - MCP"
    },
    "issuedAt": "2026-04-06T20:35:47.115252+00:00",
    "expiresAt": "2026-04-07T20:35:47.115252+00:00",
    "scan": {
      "result": "warnings",
      "scannedAt": "2026-04-04T15:59:28.788497+00:00",
      "framework": "mcp",
      "trustScore": 0,
      "findings": {
        "critical": 0,
        "high": 24,
        "medium": 3,
        "total": 27
      },
      "positiveSignals": ["Rate limiting", "CORS configuration", "Input validation"],
      "checks": {
        "no_critical_findings": true,
        "no_high_findings": false,
        "has_readme": true,
        "has_license": true,
        "has_tests": true
      },
      "filesScanned": 33,
      "primaryLanguage": "TypeScript"
    },
    "trust": {
      "overall": 0.0944,
      "scanComponent": 0.0
    }
  },
  "signature": "eC1LwjRgPoSP3o3kIZ7tFUn5JMDbZ_sN1swT8vWhCFI7mOjwyfZgQ4ra40wOo6FdeGZ-TMpU6q-slw_HOSW6Bw",
  "algorithm": "EdDSA",
  "key_id": "agentgraph-security-v1",
  "jwks_url": "https://agentgraph.co/.well-known/jwks.json"
}
```

### Verification

Signing input is canonical JSON of the `payload` object — sorted keys, compact separators (`JSON.stringify` with `sort_keys=True, separators=(",", ":")` in Python, or equivalent `JSON.stringify` with sorted keys in JS). Signature is base64url-encoded raw Ed25519 (64 bytes). Verify against the public key at the JWKS endpoint using kid `agentgraph-security-v1`.

Open source: [github.com/agentgraph-co/agentgraph](https://github.com/agentgraph-co/agentgraph) — signing module at [`src/signing.py`](https://github.com/agentgraph-co/agentgraph/blob/main/src/signing.py), attestation endpoint at [`src/api/security_attestation_router.py`](https://github.com/agentgraph-co/agentgraph/blob/main/src/api/security_attestation_router.py).

---

## Post 2: A2A #1628 Reply

Post this as a comment on: https://github.com/a2aproject/A2A/discussions/1628

---

@douglasborthwick-crypto — glad to hear it fills a gap. We shipped the infrastructure this afternoon.

- **JWKS**: [`https://agentgraph.co/.well-known/jwks.json`](https://agentgraph.co/.well-known/jwks.json)
- **kid**: `agentgraph-security-v1`
- **Algorithm**: EdDSA (Ed25519)
- **Dimension**: "Security Posture" — has this agent's source code been scanned for vulnerabilities, and what is the severity profile of findings?

Full sample signed payload posted on [insumer-examples #1](https://github.com/douglasborthwick-crypto/insumer-examples/issues/1).

---

## Reference

- JWKS live at: https://agentgraph.co/.well-known/jwks.json
- Sample attestation: https://agentgraph.co/api/v1/entities/1e7b584d-2621-47a8-a314-20b9a908353a/attestation/security
- Signature verified locally on 2026-04-06
- insumer-examples repo: https://github.com/douglasborthwick-crypto/insumer-examples
- insumer-examples issue #1: https://github.com/douglasborthwick-crypto/insumer-examples/issues/1
- A2A #1628: https://github.com/a2aproject/A2A/discussions/1628
