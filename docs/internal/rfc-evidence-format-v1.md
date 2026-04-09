# RFC: Composable Trust Evidence Format for Multi-Provider Agent Attestations

**Status:** Draft
**Authors:** Kenne Ives (AgentGraph), Justin Headley (MoltBridge), Erik Newton (Verascore) — with input from AgentID (Harold Frimpong), RNWY, and the A2A/insumer working groups
**Date:** 2026-04-09
**Version:** 0.1.0

---

## 1. Problem Statement

The agent ecosystem lacks a standard format for exchanging trust signals between independent providers. Today, each trust provider (static analyzers, behavioral monitors, identity verifiers, on-chain auditors) emits attestations in proprietary formats. This creates three problems:

1. **No composability.** A gateway that wants to combine signals from AgentGraph's static scanner, MoltBridge's behavioral monitor, and RNWY's on-chain audit must write bespoke integrations for each.

2. **No portability.** An agent that earns trust on one platform cannot carry that trust to another. Each platform starts from zero.

3. **No separation of concerns.** Providers are forced to make enforcement decisions (allow/block) when their actual expertise is signal production. The enforcement decision should be made by a gateway that can weigh multiple signals together.

### Key Insight

**Providers produce signals. Gateways produce verdicts. Any provider can also act as a gateway.**

A static analyzer knows whether code contains `eval()` on untrusted input. A behavioral monitor knows whether an agent exfiltrated data at runtime. Neither signal alone is sufficient to decide whether an agent should operate. That decision benefits from an enforcement layer that can weigh all available evidence, apply policy, and issue a verdict. Crucially, any participant in the ecosystem can implement a gateway — the format is open and the decision logic is pluggable. The goal is interoperability, not centralization.

---

## 2. Scope

This RFC defines:

- A **JSON envelope** that carries attestations from multiple independent providers
- A **provider taxonomy** that classifies signal types
- An **evidence bundle** format for presenting multiple attestations to a gateway
- An **enforcement verdict** format returned by a gateway
- **Security requirements** for attestation verification

This RFC does NOT define:

- The internal format of any provider's attestation payload (provider-specific)
- Specific trust scoring algorithms
- Network transport or discovery protocols
- Token economics or incentive structures

---

## 3. Provider Taxonomy

Each provider is classified by its primary signal type. A provider MAY produce signals in multiple categories.

| Category | Signal Type | Example Providers | What It Measures |
|---|---|---|---|
| `static-analysis` | Code-level risk assessment | AgentGraph Trust Scanner | Secret hygiene, code safety, data handling, filesystem access |
| `behavioral` | Runtime behavior observation | MoltBridge | API call patterns, data flow, resource consumption, anomaly detection |
| `continuous-monitoring` | Ongoing operational audit | RNWY | On-chain activity, SLA compliance, uptime, incident history |
| `identity` | DID resolution and verification | AgentID | DID validity, controller verification, key rotation history |
| `peer-review` | Human or agent endorsements | AgentGraph Social Graph | Trust score from network, endorsement count, contestation history |

---

## 4. Attestation Envelope

Every attestation, regardless of provider, MUST be wrapped in this envelope.

```json
{
  "@context": [
    "https://www.w3.org/ns/credentials/v2",
    "https://agentgraph.co/ns/trust-evidence/v1"
  ],
  "type": "TrustAttestation",
  "version": "1.0.0",

  "provider": {
    "id": "did:web:agentgraph.co",
    "name": "AgentGraph Trust Scanner",
    "category": "static-analysis",
    "version": "0.3.0"
  },

  "subject": {
    "did": "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
    "repo": "haroldmalikfrimpong-ops/getagentid",
    "ref": "main",
    "commit": "a1b2c3d..."
  },

  "attestation": {
    "type": "SecurityAttestation",
    "confidence": 0.82,
    "payload": {
      "trust_score": 66,
      "grade": "B",
      "findings": {"critical": 0, "high": 2, "medium": 5, "total": 7}
    }
  },

  "issued_at": "2026-04-09T16:00:00Z",
  "expires_at": "2026-05-09T16:00:00Z",

  "jws": "eyJhbGciOiJFZERTQSIsImtpZCI6ImFnLTEifQ...",
  "jwks_url": "https://agentgraph.co/api/v1/public/scan/jwks.json"
}
```

### 4.1 Required Fields

| Field | Type | Description |
|---|---|---|
| `@context` | `string[]` | JSON-LD context. MUST include the trust-evidence namespace. |
| `type` | `string` | Always `"TrustAttestation"`. |
| `version` | `string` | Envelope schema version (semver). |
| `provider.id` | `string` | DID of the attestation provider. |
| `provider.category` | `string` | One of the taxonomy categories from Section 3. |
| `subject.did` | `string` | DID of the agent being attested. |
| `attestation.type` | `string` | Provider-defined attestation type. |
| `attestation.confidence` | `number` | 0.0-1.0. Provider's confidence in this attestation. |
| `attestation.payload` | `object` | Provider-specific data. Opaque to the envelope. |
| `issued_at` | `string` | ISO 8601 timestamp. |
| `expires_at` | `string` | ISO 8601 timestamp. After this, the attestation MUST NOT be used. |
| `jws` | `string` | JSON Web Signature over the envelope (excluding `jws` field itself). |
| `jwks_url` | `string` | URL to the provider's public key set for verification. |

### 4.2 Optional Fields

| Field | Type | Description |
|---|---|---|
| `subject.repo` | `string` | Repository identifier (owner/name). |
| `subject.ref` | `string` | Git ref (branch, tag). |
| `subject.commit` | `string` | Git commit SHA. |
| `provider.name` | `string` | Human-readable provider name. |
| `provider.version` | `string` | Provider software version. |

---

## 5. Evidence Bundle

When a gateway needs to make an enforcement decision, it collects attestations from multiple providers into an evidence bundle.

```json
{
  "type": "EvidenceBundle",
  "version": "1.0.0",
  "subject": {
    "did": "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
  },
  "attestations": [
    { "...AgentGraph static-analysis attestation..." : "..." },
    { "...MoltBridge behavioral attestation..." : "..." },
    { "...RNWY continuous-monitoring attestation..." : "..." },
    { "...AgentID identity attestation..." : "..." }
  ],
  "collected_at": "2026-04-09T16:05:00Z",
  "collector": "did:web:agentgraph.co#gateway"
}
```

The bundle is an input to the enforcement decision layer. It carries no opinion -- only evidence.

---

## 6. Enforcement Verdict

The gateway consumes an evidence bundle and returns a verdict. The verdict is the enforcement decision, not a trust score.

```json
{
  "type": "EnforcementVerdict",
  "version": "1.0.0",
  "gateway": {
    "id": "did:web:agentgraph.co#gateway",
    "name": "AgentGraph Trust Gateway",
    "version": "1.0.0"
  },
  "subject": {
    "did": "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
  },
  "verdict": "conditional_allow",
  "conditions": [
    "restrict:filesystem_write",
    "restrict:network_egress_unallowlisted",
    "monitor:behavioral"
  ],
  "reasoning": {
    "composite_score": 0.68,
    "decisive_factors": [
      {
        "provider": "did:web:agentgraph.co",
        "category": "static-analysis",
        "weight": 0.35,
        "signal": "B grade, 2 high findings (filesystem + eval)"
      },
      {
        "provider": "did:web:moltbridge.io",
        "category": "behavioral",
        "weight": 0.30,
        "signal": "No anomalies in 14-day observation window"
      },
      {
        "provider": "did:web:rnwy.com",
        "category": "continuous-monitoring",
        "weight": 0.20,
        "signal": "99.2% uptime, no SLA violations"
      },
      {
        "provider": "did:web:agentid.dev",
        "category": "identity",
        "weight": 0.15,
        "signal": "DID resolved, controller verified, key age 47 days"
      }
    ],
    "policy": "default-v1"
  },
  "evidence_bundle_hash": "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "issued_at": "2026-04-09T16:05:01Z",
  "expires_at": "2026-04-09T17:05:01Z",
  "jws": "eyJhbGciOiJFZERTQSIsImtpZCI6Imd3LTEifQ..."
}
```

### 6.1 Verdict Values

| Verdict | Meaning |
|---|---|
| `allow` | Agent is permitted to operate with full capabilities. |
| `conditional_allow` | Agent is permitted with specific restrictions listed in `conditions`. |
| `provisional_allow` | Agent has insufficient evidence. Limited capabilities until more signals arrive. |
| `block` | Agent is denied. Gateway SHOULD include reasoning. |
| `refer` | Gateway cannot decide. Escalate to human review. |

### 6.2 Condition Syntax

Conditions use a `verb:scope` format:

- `restrict:<capability>` -- Deny a specific capability
- `monitor:<category>` -- Require ongoing monitoring from a provider in this category
- `require:<attestation_type>` -- Block until this attestation type is provided
- `expire:<duration>` -- Verdict is valid for shorter than default TTL

---

## 7. Confidence Weighting

Gateways SHOULD apply weighting to attestations based on the following factors.

### 7.1 Recency Decay

An attestation's effective confidence decays over time:

```
effective_confidence = confidence * decay_factor(age)

decay_factor(age) =
  1.0                          if age < 7 days
  1.0 - 0.1 * (age_days - 7)  if 7 <= age < 14 days
  0.3                          if 14 <= age < 30 days
  0.0                          if age >= expires_at
```

Gateways MAY use different decay curves but MUST NOT use an attestation past its `expires_at`.

### 7.2 Interaction Volume

Behavioral attestations carry more weight when based on more observations:

```
volume_factor =
  0.5   if interactions < 100
  0.8   if 100 <= interactions < 1000
  1.0   if interactions >= 1000
```

### 7.3 Provider Reliability

Gateways SHOULD track provider accuracy over time. A provider whose attestations frequently conflict with other providers' observations gets reduced weight.

```
reliability = correct_predictions / total_predictions
```

This is internal to the gateway and not part of the wire format.

---

## 8. Expiration Semantics

Two distinct TTLs apply:

| TTL | Controls | Typical Range |
|---|---|---|
| **Attestation TTL** (`expires_at` on attestation) | How long a provider's signal is valid. | 1-30 days depending on category. Static analysis: 30 days. Behavioral: 7 days. Continuous monitoring: 24 hours (RNWY confirmed — nightly pipeline). Identity: 90 days. |
| **Verdict TTL** (`expires_at` on verdict) | How long a gateway's decision is valid. | 1-24 hours. Short because new evidence may arrive. |

A verdict MUST expire before any attestation in its evidence bundle expires.

When an attestation expires, the gateway SHOULD re-request it from the provider. If the provider is unavailable, the gateway applies the cold-start policy for that signal category.

---

## 9. Security Requirements

### 9.1 Attestation Verification

Every attestation MUST be signed with JWS (RFC 7515). Gateways MUST verify signatures before consuming attestations.

Verification steps:
1. Fetch the provider's JWKS from `jwks_url`.
2. Verify the `jws` over the attestation envelope (with `jws` field removed).
3. Confirm the signing key's `kid` matches a key in the JWKS.
4. Confirm `expires_at` has not passed.
5. Confirm `provider.id` resolves to a known, registered provider.

### 9.2 Provider Key Rotation

Providers MUST support key rotation via JWKS. The JWKS endpoint MUST:

- Include all active signing keys
- Retain retired keys for at least 30 days after rotation (to verify in-flight attestations)
- Return `Cache-Control: max-age=3600` (gateways cache for 1 hour max)

### 9.3 Transport Security

- All `jwks_url` values MUST use HTTPS.
- Gateways MUST pin provider TLS certificates or use certificate transparency logs.
- Evidence bundles in transit between providers and gateways MUST use mTLS.

### 9.4 Replay Prevention

Each attestation MUST include a unique `jti` (JWT ID) claim in its JWS. Gateways MUST maintain a seen-set of `jti` values for the attestation's validity period to prevent replay.

---

## 10. Cold Start

When an agent has valid identity but no attestation history, the gateway issues a provisional verdict:

- `verdict: "provisional_allow"`
- Restricted to read-only capabilities
- Short TTL (24 hours)
- `conditions: ["require:static-analysis", "require:behavioral", "restrict:write", "restrict:execute"]`

See `fixtures/agentgraph-cold-start.json` for the full cold-start attestation format.

---

## 11. Reference Implementations

### 11.1 AgentGraph Trust Gateway (Enforcement)

The gateway consumes evidence bundles and produces verdicts. Reference implementation at `agentgraph-co/agentgraph` in `src/trust/gateway.py`.

- Accepts attestations via `/api/v1/gateway/evaluate` (POST)
- Returns enforcement verdicts
- Configurable policy engine (default-v1 ships with the weights in Section 7)
- Caches verdicts for their TTL period

### 11.2 AgentGraph Trust Scanner (Static Analysis Provider)

Produces `SecurityAttestation` envelopes from repository scans. Available as:
- CLI: `agentgraph-trust scan <repo>`
- GitHub Action: `agentgraph-co/trust-scan-action`
- API: `POST /api/v1/public/scan`

### 11.3 MoltBridge Behavioral Monitor (Behavioral Provider)

Produces `BehavioralAttestation` envelopes from runtime observation. Tracks API call patterns, data flow volumes, and anomaly scores over observation windows.

### 11.4 RNWY On-Chain Auditor (Continuous Monitoring Provider)

Produces `ComplianceAttestation` envelopes from on-chain activity analysis. Tracks SLA adherence, uptime, and incident response times.

### 11.5 AgentID Identity Verifier (Identity Provider)

Produces `IdentityAttestation` envelopes from DID resolution. Verifies controller ownership, key validity, and rotation history.

---

## 12. Open Questions

1. **Attestation chaining.** Should attestations be able to reference other attestations? Example: a behavioral attestation that says "we observed this agent after it received a B grade from static analysis."

2. **Revocation.** How does a provider revoke an attestation before its `expires_at`? Options: revocation lists, short TTLs, or status endpoints.

3. **Privacy.** Some behavioral data may be sensitive. Should the payload support encrypted fields that only the gateway can decrypt?

4. **Versioning.** How do we handle breaking changes to the envelope schema? Version negotiation between providers and gateways.

5. **Incentives.** Should providers be compensated for producing attestations? If so, this RFC should define a payment claim field.

---

## Appendix A: Provider Registration

Providers register with a gateway by submitting:

```json
{
  "provider_did": "did:web:example.com",
  "name": "Example Trust Provider",
  "category": "static-analysis",
  "jwks_url": "https://example.com/.well-known/jwks.json",
  "attestation_types": ["SecurityAttestation"],
  "callback_url": "https://example.com/api/v1/scan"
}
```

The gateway validates the DID, fetches the JWKS, and stores the provider record. Providers appear in the gateway's provider registry at `/api/v1/gateway/providers`.

---

## Appendix B: Full Example Flow

1. Agent `did:key:z6Mk...` requests access to a platform.
2. Platform's gateway queries registered providers for attestations on this DID.
3. AgentGraph returns a `SecurityAttestation` (static scan from 3 days ago, confidence 0.82).
4. MoltBridge returns a `BehavioralAttestation` (14-day observation, confidence 0.91).
5. RNWY returns a `ComplianceAttestation` (on-chain audit, confidence 0.75).
6. AgentID returns an `IdentityAttestation` (DID verified, confidence 0.99).
7. Gateway assembles an evidence bundle, applies weighting (recency, volume, reliability).
8. Gateway issues verdict: `conditional_allow` with `restrict:filesystem_write`.
9. Platform enforces the verdict, granting the agent access with filesystem write disabled.
10. Verdict expires in 1 hour. Gateway re-evaluates with fresh attestations.
