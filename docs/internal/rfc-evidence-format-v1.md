# RFC: Composable Trust Evidence Format for Multi-Provider Agent Attestations

**Status:** Draft
**Authors:** Kenne Ives (AgentGraph), Justin Headley (MoltBridge), Erik Newton (Verascore), Alexander Lawson (Revettr) — with input from AgentID (Harold Frimpong), RNWY, Concordia Protocol, Sanctuary Framework, and the A2A/insumer working groups
**Date:** 2026-04-11
**Version:** 0.2.0

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
| `static_analysis` | Code-level risk assessment | AgentGraph Trust Scanner | Secret hygiene, code safety, data handling, filesystem access |
| `behavioral` | Runtime behavior observation | MoltBridge | API call patterns, data flow, resource consumption, anomaly detection |
| `continuous_monitoring` | Ongoing operational audit | RNWY | On-chain activity, SLA compliance, uptime, incident history |
| `identity` | DID resolution and verification | AgentID | DID validity, controller verification, key rotation history |
| `peer_review` | Human or agent endorsements | AgentGraph Social Graph | Trust score from network, endorsement count, contestation history |
| `transactional` | Negotiation and settlement outcomes | Concordia Protocol | Commitment honor rate, session completion, dispute rate |
| `sovereignty` | Agent autonomy and self-custody posture | Sanctuary Framework | L1-L4 sovereignty layers (cognitive, operational isolation, selective disclosure, verifiable reputation) |
| `graph_structural` | Trust graph topology | MoltBridge | Endorsement density, path diversity, sybil cluster detection |
| `compliance_risk` | Regulatory compliance signals | Revettr | Sanctions screening (OFAC/EU/UN), domain hygiene, IP reputation, wallet screening |

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
    "category": "static_analysis",
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
| `aud` | `string` | URL or DID of the intended verifier. Included inside the JWS signed bytes so it cannot be stripped post-signature. When present, the attestation is scoped to a specific gateway. When absent, the attestation is treated as bearer — valid for any verifier. |
| `refresh_hint` | `object` | Hint for consumers on when to re-request this attestation. See Section 4.3. |
| `visibility` | `string` | One of `"public"`, `"restricted"`, `"private"`. Controls payload disclosure. See Section 4.4. Default: `"public"`. |
| `references` | `array` | Attestation chaining. Array of reference objects linking to upstream evidence. See Section 4.5. |

### 4.3 Refresh Hint

Providers MAY include a `refresh_hint` to indicate how consumers should re-request attestations:

```json
"refresh_hint": {
  "strategy": "event_driven",
  "events": ["code_push", "dependency_update"],
  "max_age_seconds": 86400
}
```

| Field | Type | Description |
|---|---|---|
| `strategy` | `string` | `"event_driven"` or `"ttl_only"`. If `ttl_only`, consumers just respect `expires_at`. |
| `events` | `string[]` | Event types that should trigger a re-request. Only meaningful when strategy is `event_driven`. |
| `max_age_seconds` | `number` | Hard upper bound on attestation age regardless of strategy. |

### 4.4 Visibility

The `visibility` field controls how the attestation payload is shared:

| Value | Meaning |
|---|---|
| `public` | Full payload visible to any consumer. Default. |
| `restricted` | Payload visible only to gateways that have a trust relationship with the provider. |
| `private` | Only the envelope metadata (provider, subject, confidence, timestamps) is shared. Payload omitted. Consumer must contact provider directly for details. |

This replaces the earlier discussion around encrypted evidence fields. Simpler, and the access control happens at the application layer rather than the crypto layer.

### 4.5 References (Attestation Chaining)

Attestations MAY reference upstream evidence via the `references` array:

```json
"references": [
  {
    "kind": "source_session",
    "urn": "urn:concordia:session:abc123",
    "verified_at": "2026-04-10T12:00:00Z"
  },
  {
    "kind": "upstream_envelope",
    "urn": "urn:trust-evidence:att:did:web:agentgraph.co:9f86d081",
    "verifier_did": "did:web:moltbridge.io",
    "hash": "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
  }
]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `kind` | `string` | Yes | One of: `source_session`, `list_update`, `chain_state`, `upstream_envelope`, `mandate_proof`. |
| `urn` | `string` | Yes | URN identifying the referenced resource. |
| `verified_at` | `string` | No | ISO 8601 timestamp of when the reference was verified. |
| `verifier_did` | `string` | No | DID of the entity that verified the reference. |
| `hash` | `string` | No | Content hash of the referenced resource for integrity verification. |

v1 scope is single back-pointer references. Full DAG traversal is deferred to v2 -- the consensus from the A2A thread is that it is overkill for the initial release.

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
    { "...AgentGraph static_analysis attestation..." : "..." },
    { "...MoltBridge behavioral attestation..." : "..." },
    { "...RNWY continuous_monitoring attestation..." : "..." },
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
        "category": "static_analysis",
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
        "category": "continuous_monitoring",
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
| **Attestation TTL** (`expires_at` on attestation) | How long a provider's signal is valid. | Varies by category (see table below). |
| **Verdict TTL** (`expires_at` on verdict) | How long a gateway's decision is valid. | 1-24 hours. Short because new evidence may arrive. |

### 8.1 Per-Category TTL Defaults

| Category | TTL | Refresh Strategy | Rationale |
|---|---|---|---|
| `static_analysis` | 24h | Code change webhook | Code changes can introduce vulns |
| `behavioral` | 1-7 days | Interaction frequency | Recent behavior more predictive |
| `continuous_monitoring` | 24h | Nightly pipeline (RNWY confirmed) | Aligned with scan cycle |
| `identity` | No fixed TTL | Key rotation event | Identity doesn't expire unless keys change |
| `peer_review` | 30 days | Manual | Human reviews have longer validity |
| `transactional` | 7 days | `session_completed`, `dispute_raised` | Transaction history matters when recent |
| `sovereignty` | No fixed TTL | Config change event | Stable across runtime lifetimes |
| `graph_structural` | 7 days | Graph topology change | Sybil detection updates with graph |
| `compliance_risk` | 1h TTL, 12h `max_age` | Event-driven (OFAC/EU/UN updates), **hard_fail** default | Compliance is fail-closed |

`compliance_risk` is unique: if the attestation cannot be refreshed within `max_age`, the gateway MUST treat the signal as absent and apply the cold-start policy. This is a hard fail -- compliance signals do not degrade gracefully.

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
6. If the `aud` field is present, confirm that `aud` matches the verifier's own URL or DID. Reject the attestation if it does not match. If `aud` is absent, accept the attestation as bearer (valid for any verifier). This prevents replay attacks where an attestation fetched from one agent's `.well-known` endpoint is presented to a different gateway than intended.

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
- `conditions: ["require:static_analysis", "require:behavioral", "restrict:write", "restrict:execute"]`

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

### 11.6 Concordia Protocol (Transactional Provider)

Produces `TransactionalAttestation` envelopes from negotiation and settlement sessions. Tracks commitment honor rate, session completion, and dispute outcomes. Emits `session_completed` and `dispute_raised` events for refresh_hint consumers.

### 11.7 Sanctuary Framework (Sovereignty Provider)

Produces `SovereigntyAttestation` envelopes assessing agent autonomy posture across four layers: L1 (cognitive autonomy), L2 (operational isolation), L3 (selective disclosure), L4 (verifiable reputation). Attestations are long-lived -- refreshed only on agent configuration changes.

### 11.8 Revettr (Compliance Risk Provider)

Produces `ComplianceRiskAttestation` envelopes from regulatory screening pipelines. Covers OFAC/EU/UN sanctions lists, domain hygiene, IP reputation, and wallet screening. Provider DID: `did:web:revettr.com`, signing algorithm: ES256, kid: `revettr-attest-v1`. Compliance attestations use hard_fail semantics (see Section 8.1).

> **Note:** Verascore (`did:web:verascore.io`) also functions as a gateway/aggregator in addition to its continuous monitoring provider role. It can consume evidence bundles from other providers and produce enforcement verdicts.

---

## 12. Open Questions

### Resolved in v0.2

1. **Attestation chaining.** ~~Should attestations be able to reference other attestations?~~ **Resolved:** Single back-pointer via `references[]` (Section 4.5). Full DAG traversal deferred to v2 -- consensus is it's overkill for the initial release.

2. **Revocation.** ~~How does a provider revoke an attestation before its `expires_at`?~~ **Resolved (v1):** `GET /attestation/{id}/status` returning `active|revoked|expired`. v2 will add event-driven push for high-stakes categories (compliance_risk, transactional).

3. **Privacy.** ~~Should the payload support encrypted fields?~~ **Resolved:** `visibility` field (Section 4.4) with `public|restricted|private` values. Simpler than encrypted_evidence -- access control at the application layer, not the crypto layer.

4. **Versioning.** ~~How do we handle breaking changes?~~ **Resolved:** Semver on the envelope schema. Gateways MUST support current major version N and previous major version N-1 during a 6-month deprecation window. Providers SHOULD emit the latest version but MAY emit N-1 during the transition.

### Still Open

5. **Incentives.** Should providers be compensated for producing attestations? If so, this RFC should define a payment claim field. Deferred to post-v1.

6. **Cross-gateway verdict portability.** When gateway A issues a verdict, can gateway B trust it? Or must B re-evaluate the evidence bundle independently? Related to the gateway-as-provider pattern.

7. **Attestation size limits.** Should the envelope define a maximum payload size? Large behavioral observation windows could produce multi-MB payloads.

---

## 13. Validity Temporal Modes

Cross-category temporal validity model, per nanookclaw + Douglas consensus from the A2A thread. Every attestation's temporal validity falls into one of three modes:

### 13.1 Sequence Mode

Every event is a verification point against a prior baseline. The attestation is valid as long as subsequent events do not diverge from the established baseline.

- **Failure condition:** Divergence from baseline (e.g., behavioral anomaly after a period of normal operation).
- **Best for:** `behavioral`, `continuous_monitoring`, `transactional`.
- **Example:** A behavioral monitor establishes a baseline API call pattern. Each new observation is compared against it. Divergence triggers re-attestation.

### 13.2 Windowed Mode

Verification happens at interval boundaries. The attestation covers a fixed time window and is replaced by the next window's attestation.

- **Failure condition:** Boundary aliasing -- events that fall between windows may be missed.
- **Constraint:** `minimum_window` -- the shortest allowable window to prevent aliasing.
- **Best for:** `static_analysis`, `peer_review`, `graph_structural`.
- **Example:** A static analysis scan runs nightly. The attestation covers the 24h window. Events between scan boundaries are not individually verified.

### 13.3 State-Bound Mode

The signature commits to a specific state read. The attestation is valid as long as the underlying state has not changed.

- **Failure condition:** Head reorg -- the state the attestation was signed against is no longer canonical.
- **Constraints:** `minimum_depth` (how many confirmations before the state read is trusted), backstop `max_age` (hard expiration even if state hasn't changed).
- **Best for:** `identity`, `sovereignty`, `compliance_risk`.
- **Example:** An identity attestation commits to a DID document at a specific resolution. If the DID document is updated (key rotation), the attestation is invalidated regardless of TTL.

Gateways SHOULD declare which temporal mode they expect per category. Providers SHOULD indicate which mode their attestation uses via a `validity_mode` field in the attestation payload.

---

## 14. Governance and Future Organization

This RFC is currently maintained in the AgentGraph repository (`agentgraph-co/agentgraph`). For v1.0, the specification will move to the `trust-evidence-format` GitHub organization, co-owned by AgentGraph, Verascore, and Revettr. Governance will follow a lightweight RFC process with approval from at least two co-owners for breaking changes.

---

## Appendix A: Provider Registration

Providers register with a gateway by submitting:

```json
{
  "provider_did": "did:web:example.com",
  "name": "Example Trust Provider",
  "category": "static_analysis",
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
