# RFC: Evidence Interchange Format for Multi-Provider Agent Trust

**Status:** Draft  
**Authors:** AgentGraph (@kenneives), MoltBridge (@JKHeadley), Verascore (@eriknewton)  
**Context:** A2A Agent Identity Verification WG, insumer multi-attestation stack  

## Abstract

This RFC proposes a standardized format for exchanging signed trust evidence between independent providers. The format enables any aggregator to consume attestations from any producer, verify their authenticity, and compose multi-dimensional trust profiles.

## Motivation

The agent trust ecosystem has grown to 8+ independent providers, each covering different trust dimensions (security posture, behavioral trust, identity verification, governance, execution history, etc.). Today, each provider uses slightly different payload formats, making cross-provider consumption brittle.

We need a standard that:
1. Allows any provider to produce signed evidence that any consumer can verify
2. Supports different evidence types with type-specific fields
3. Includes freshness and confidence metadata so consumers can make informed weighting decisions
4. Is backward-compatible with the existing JWKS + compact JWS model proven by the insumer WG

## Specification

### 1. Discovery

Every provider MUST publish:
- `/.well-known/jwks.json` — RFC 7517 JSON Web Key Set with at least one signing key
- Each key MUST include `kid` (Key ID) and `alg` (Algorithm — EdDSA or ES256)

### 2. Attestation Envelope

Every attestation is a compact JWS (RFC 7515): `header.payload.signature`

**Header:**
```json
{
  "alg": "EdDSA",
  "kid": "provider-key-id-v1"
}
```

**Payload (required fields):**
```json
{
  "type": "TrustAttestation",
  "version": "1.0",
  "issuer": {
    "id": "did:web:provider.example",
    "name": "ProviderName",
    "jwks": "https://provider.example/.well-known/jwks.json"
  },
  "subject": {
    "id": "did:web:agent.example",
    "type": "agent"
  },
  "provider_type": "static_analysis",
  "evidence_type": "security_posture",
  "issuedAt": "2026-04-08T12:00:00Z",
  "scannedAt": "2026-04-08T11:55:00Z",
  "expiresAt": "2026-04-09T12:00:00Z",
  "confidence": 0.85,
  "evidence": { }
}
```

### 3. Provider Type Taxonomy

| Type | Description | Example Providers |
|------|-------------|-------------------|
| `static_analysis` | Source code security scanning | AgentGraph |
| `behavioral` | Runtime behavior and interaction patterns | RNWY, MoltBridge |
| `identity` | Agent identity verification | AgentID |
| `governance` | Policy enforcement and delegation | APS |
| `transactional` | Transaction and settlement records | SAR/nutstrut |
| `compliance` | Regulatory compliance and sanctions | Revettr |
| `sovereignty` | Self-custodied identity and disclosure | Verascore/Sanctuary |
| `execution_history` | Append-only execution records | WTRMRK |

### 4. Evidence Type Fields

**4.1 static_analysis (AgentGraph)**
```json
{
  "trust_score": 89,
  "trust_tier": "trusted",
  "category_scores": {
    "secret_hygiene": 100,
    "code_safety": 85,
    "data_handling": 90,
    "filesystem_access": 75
  },
  "findings_summary": {
    "critical": 0, "high": 2, "medium": 5, "total": 7
  },
  "positive_signals": ["auth_check", "input_validation", "rate_limiting"],
  "files_scanned": 150,
  "primary_language": "Python"
}
```

**4.2 behavioral (RNWY)**
```json
{
  "signal_depth": { "value": 72, "zone": "Established" },
  "risk_intensity": { "value": 15, "zone": "Low" },
  "reviewer_credibility": { "pct_low_history": 5.2 },
  "commerce_jobs_completed": 45,
  "sybil_flags": 0
}
```

**4.3 behavioral (MoltBridge)**
```json
{
  "interaction_count": 127,
  "success_rate": 0.94,
  "last_interaction": "2026-04-07T15:30:00Z",
  "dispute_count": 2,
  "graph_path": ["did:key:z6Mk...A", "did:key:z6Mk...B"]
}
```

### 5. Confidence Field

The `confidence` field (0.0-1.0) indicates how much weight a consumer should give this attestation:

| Factor | Effect on Confidence |
|--------|---------------------|
| Cryptographically signed (JWS verified) | +0.3 base |
| Provider has JWKS published | +0.2 |
| Cross-corroborated by another provider | +0.2 |
| Evidence is fresh (< 24h) | +0.1 |
| Provider is in a verified registry (OATR) | +0.2 |

### 6. Expiration Model

Different evidence types decay at different rates:

| Evidence Type | Recommended TTL | Decay Behavior |
|---------------|-----------------|----------------|
| static_analysis | 7 days | Slow — code changes infrequently |
| behavioral | 24 hours | Fast — behavior can shift quickly |
| identity | 30 days | Slow — identity is stable |
| transactional | Per-transaction | Event-based, no decay |
| execution_history | Never expires | Append-only, immutable |

### 7. Verification Flow

1. Consumer receives a JWS attestation
2. Extract `kid` from JWS header
3. Fetch issuer's JWKS from `issuer.jwks` URL
4. Find key matching `kid`
5. Verify signature using the public key
6. Check `expiresAt` for freshness
7. Check `confidence` to decide weighting
8. Incorporate evidence into composite trust decision

### 8. Canonicalization

Payload MUST be serialized using JCS (RFC 8785) before signing:
- Sorted keys
- No whitespace
- Integer-valued floats without decimal (1.0 → 1)
- Null values stripped

This ensures byte-identical serialization across Python and TypeScript runtimes.

## Existing Implementations

- **AgentGraph**: JWKS live at `agentgraph.co/.well-known/jwks.json`, EdDSA
- **MoltBridge**: JWKS live at `api.moltbridge.ai/.well-known/jwks.json`, EdDSA
- **AgentID**: JWKS live at `getagentid.dev/.well-known/jwks.json`, EdDSA
- **RNWY**: JWKS live at `rnwy.com/.well-known/jwks.json`, ES256
- **insumer WG**: 8/8 providers verified through this format

## Open Questions

1. Should the format support multi-signature attestations (co-signed by multiple providers)?
2. Should there be a revocation mechanism for attestations?
3. How should graph traversal evidence (transitive trust paths) be encoded?
