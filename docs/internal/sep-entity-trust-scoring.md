# SEP: Entity-Level Trust Scoring for MCP

## Abstract

This SEP proposes adding entity-level trust metadata to the MCP protocol, enabling hosts and clients to make informed decisions about which agents and tools to trust based on verifiable, multi-dimensional trust scores rather than self-declared annotations.

## Motivation

Current trust-related SEPs (1913, 1984, 1487) allow tools and servers to self-declare their trust and sensitivity properties. However, these annotations are unverifiable — any server can claim `trustedHint: true` without external validation.

The missing layer is **entity-level trust**: cryptographically signed attestations from independent providers that verify an agent's identity, security posture, behavioral history, and community standing.

Example: An MCP server declares `sensitiveHint: true` (SEP-1913). But who verified this? Entity-level trust answers: "AgentGraph scanned this server's source code (score: 89/100), MoltBridge has 127 successful interactions on record, and AgentID verified the operator's identity."

## Proposal

### 1. Trust Profile Discovery

MCP servers SHOULD publish a trust profile at `/.well-known/trust-profile.json`:

```json
{
  "entity_id": "did:web:server.example",
  "trust_providers": [
    {
      "provider": "agentgraph",
      "type": "security_posture",
      "endpoint": "https://agentgraph.co/api/v1/public/scan/owner/repo",
      "jwks": "https://agentgraph.co/.well-known/jwks.json"
    }
  ],
  "composite_score": 89,
  "grade": "A",
  "last_verified": "2026-04-08T12:00:00Z"
}
```

### 2. Trust Attestation in Agent Cards

The A2A Agent Card `identity` block SHOULD support a `trust_attestations` array:

```json
{
  "identity": {
    "did": "did:web:server.example",
    "trust_attestations": [
      {
        "issuer": "did:web:agentgraph.co",
        "type": "security_posture",
        "score": 89,
        "grade": "A",
        "jws": "eyJhbGci...",
        "issued_at": "2026-04-08T12:00:00Z",
        "expires_at": "2026-04-15T12:00:00Z"
      }
    ]
  }
}
```

### 3. Trust-Tiered Capabilities

MCP hosts MAY use trust scores to gate capabilities:

| Trust Tier | Capabilities Granted |
|-----------|---------------------|
| verified (96+) | Full access, no confirmation |
| trusted (81-95) | Full access, log only |
| standard (61-80) | Limited tools, rate limited |
| minimal (41-60) | Read-only tools, user confirmation |
| restricted (21-40) | Sandboxed execution only |
| blocked (0-20) | Connection refused |

### 4. Trust Verification Flow

When an MCP client connects to a server:

1. Client fetches server's `/.well-known/trust-profile.json`
2. For each trust attestation, client fetches issuer's JWKS
3. Client verifies the JWS signature
4. Client checks attestation freshness (not expired)
5. Client applies trust-tiered capabilities based on composite score
6. Client logs the trust decision for audit

### 5. Multi-Provider Aggregation

The composite score SHOULD be computed from multiple independent providers:
- **Static analysis** (code security scanning)
- **Behavioral trust** (interaction history, anomaly detection)
- **Identity verification** (DID resolution, wallet binding)
- **Governance** (policy enforcement, delegation chains)

Cryptographically signed attestations weight higher than self-reported claims.

## Rationale

This approach is complementary to SEP-1913 (data-level annotations) and SEP-1984 (tool annotations). Those SEPs define WHAT trust properties exist. This SEP defines WHO verifies them and HOW to check.

The key insight: trust annotations without verifiable attestations are just claims. Entity-level trust with signed attestations makes those claims auditable.

## Backwards Compatibility

This SEP is additive. Servers that don't publish trust profiles are treated as "unverified" (no score). Existing servers continue to work without modification.

## Reference Implementation

- **AgentGraph MCP Server**: `pip install agentgraph-trust` — 10 tools including `check_trust_tier`
- **Trust Gateway Proxy**: `POST /api/v1/gateway/check` — enforcement decisions with signed JWS
- **JWKS**: `https://agentgraph.co/.well-known/jwks.json`
- **Open Agent Trust Registry**: 9 verified issuers with signed attestation format

## Open Questions

1. Should trust profiles be cached by the protocol, or fetched on every connection?
2. Should there be a minimum set of required trust providers?
3. How should trust decay be handled for long-running connections?
