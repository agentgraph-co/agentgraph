# Public Scan API & Trust Gateway

Scan any GitHub repository for security issues and get a trust tier with recommended rate limits. No authentication required.

## Quick Start

```bash
curl https://agentgraph.co/api/v1/public/scan/{owner}/{repo}
```

Example:

```bash
curl https://agentgraph.co/api/v1/public/scan/tuya/tuya-openclaw-skills
```

## Response

```json
{
  "repo": "tuya/tuya-openclaw-skills",
  "trust_score": 95,
  "trust_tier": "trusted",
  "recommended_limits": {
    "requests_per_minute": 60,
    "max_tokens_per_call": 8192,
    "require_user_confirmation": false
  },
  "scan_result": "clean",
  "findings": {
    "critical": 0,
    "high": 0,
    "medium": 2,
    "total": 2,
    "categories": {"fs_access": 2}
  },
  "positive_signals": ["Authentication check", "Input validation"],
  "jws": "eyJhbGciOiJFZERTQSIs...",
  "jwks_url": "https://agentgraph.co/.well-known/jwks.json"
}
```

## Trust Tiers

Every scan returns a trust tier that maps to recommended execution limits:

| Tier | Score | Rate Limit | Token Budget | User Confirm |
|------|-------|-----------|-------------|-------------|
| **verified** | 96-100 | unlimited | unlimited | No |
| **trusted** | 81-95 | 60 req/min | 8K tokens | No |
| **standard** | 51-80 | 30 req/min | 4K tokens | No |
| **minimal** | 31-50 | 15 req/min | 2K tokens | Yes |
| **restricted** | 11-30 | 5 req/min | 1K tokens | Yes |
| **blocked** | 0-10 | denied | denied | N/A |

Framework authors can use these tiers to throttle tool execution — spend less compute on risky tools, let clean tools run freely.

## Signed Attestations

Every response includes a JWS (JSON Web Signature, RFC 7515) signed with Ed25519. Verify against the public JWKS:

```
https://agentgraph.co/.well-known/jwks.json
```

## Caching

Results are cached for 1 hour. Pass `?force=true` to bypass the cache and trigger a fresh scan.

## Rate Limits

The public API is rate-limited by IP address. For higher limits, contact us.

## Badge

Embed a trust score badge in your README:

```markdown
![Trust Score](https://agentgraph.co/api/v1/public/scan/{owner}/{repo}/badge)
```

## MCP Tool

Install the MCP server for Claude Code, Cursor, or any MCP client:

```bash
pip install agentgraph-trust
```

Add to your MCP config:

```json
{
  "mcpServers": {
    "agentgraph-trust": {
      "command": "agentgraph-trust",
      "env": {
        "AGENTGRAPH_URL": "https://agentgraph.co"
      }
    }
  }
}
```

Then ask your assistant: "Check the security of [repo name]"

## What the Scanner Checks

- **Hardcoded secrets** — API keys, tokens, passwords in source
- **Unsafe execution** — subprocess, eval, exec, shell=True
- **File system access** — reads/writes outside expected boundaries
- **Data exfiltration** — outbound network calls to unexpected destinations
- **Code obfuscation** — base64-encoded payloads, dynamic imports

Positive signals (auth checks, input validation, rate limiting, CORS) boost the trust score.
