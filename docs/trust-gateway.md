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
  "trust_score": 100,
  "trust_tier": "verified",
  "recommended_limits": {
    "requests_per_minute": null,
    "max_tokens_per_call": null,
    "require_user_confirmation": false
  },
  "scan_result": "clean",
  "findings": {
    "critical": 0,
    "high": 0,
    "medium": 0,
    "total": 0,
    "categories": {},
    "suppressed_lines": 0
  },
  "positive_signals": ["Authentication check", "Input validation", "Logging / audit trail"],
  "metadata": {
    "files_scanned": 12,
    "primary_language": "Python",
    "has_readme": true,
    "has_license": true,
    "has_tests": true
  },
  "scanned_at": "2026-04-07T02:30:00+00:00",
  "cached": false,
  "jws": "eyJhbGciOiJFZERTQSIs...",
  "algorithm": "EdDSA",
  "key_id": "agentgraph-2026-03",
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

### Available MCP Tools (v0.3.0)

| Tool | Description |
|------|-------------|
| `check_trust_tier` | Scan a repo and get trust tier with recommended rate limits |
| `scan_repository` | Full security scan with detailed findings |
| `get_trust_score` | Quick trust score lookup |
| `verify_attestation` | Verify a JWS attestation against the public JWKS |
| `list_findings` | List all findings for a scanned repo |
| `get_positive_signals` | List detected positive security signals |
| `compare_repos` | Compare trust scores between two repos |
| `get_scan_history` | View scan history for a repo |
| `get_badge_url` | Get the badge URL for README embedding |
| `check_compliance` | Check if a repo meets a minimum trust tier |

## What the Scanner Checks

### Security Findings (reduce score)

- **Hardcoded secrets** — API keys, tokens, passwords in source
- **Unsafe execution** — subprocess, eval, exec, shell=True
- **File system access** — reads/writes outside expected boundaries
- **Data exfiltration** — outbound network calls to unexpected destinations
- **Code obfuscation** — base64-encoded payloads, dynamic imports

### Positive Signals (boost score)

- Authentication checks (login, JWT, OAuth)
- Input validation and sanitization
- Rate limiting / CORS configuration
- Cryptographic verification (HMAC, JWT signing)
- Logging / audit trails
- Error handling (try/except, .catch)
- Type safety (TypeVar, Pydantic, dataclasses)
- Dependency pinning (lock files)
- README, LICENSE, and test directories

### Context-Aware Analysis

The scanner avoids false positives with context-aware checks:

- `subprocess.run(["git", "status"])` with hardcoded args → **safe** (not flagged)
- `subprocess.run(cmd, shell=False)` → **safe**
- `ast.literal_eval(data)` → **safe** (not confused with `eval()`)
- `open("config.json", "r")` with hardcoded path → **safe**
- Findings in test files (`tests/*`, `test/*`) → severity downgraded

### Anti-Gaming

- **Inline suppression** (`# ag-scan:ignore`) is supported but monitored
- The `suppressed_lines` count is exposed in every response for transparency
- Repos with excessive suppressions (>10) receive a score penalty
- Suppression abuse is visible to any consumer of the API
