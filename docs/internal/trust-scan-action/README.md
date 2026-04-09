# AgentGraph Trust Scan Action

Scan your MCP server or AI agent tool for security issues in CI. Get a trust grade (A-F) with per-category sub-scores.

## Quick Start

```yaml
# .github/workflows/trust-scan.yml
name: Trust Scan
on: [push, pull_request]

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: agentgraph-co/trust-scan-action@v1
        with:
          min-score: 50  # Fail if score drops below 50
```

## Features

- **Context-aware** — MCP servers get scored differently than regular libraries
- **Per-category grades** — secret_hygiene, code_safety, data_handling, filesystem_access
- **PR comments** — auto-posts scan results on pull requests
- **Signed attestation** — EdDSA-signed JWS verifiable against our JWKS
- **No account needed** — uses the public scan API (no auth required)

## Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `repo` | Current repo | Repository to scan (owner/repo) |
| `min-score` | `0` | Minimum score to pass (0-100) |
| `comment` | `true` | Post results as PR comment |
| `badge` | `false` | Update README badge |

## Outputs

| Output | Description |
|--------|-------------|
| `score` | Trust score (0-100) |
| `grade` | Letter grade (A+/A/B/C/D/F) |
| `tier` | Trust tier |
| `scan-result` | clean/warnings/critical |
| `is-mcp-server` | Whether MCP context was detected |

## Badge

Add to your README:

```markdown
[![AgentGraph Trust](https://agentgraph.co/api/v1/public/scan/YOUR/REPO/badge)](https://agentgraph.co/api/v1/public/scan/YOUR/REPO)
```

## Links

- [Public Scan API](https://agentgraph.co/docs/trust-gateway)
- [MCP Tool](https://pypi.org/project/agentgraph-trust/)
- [Trust Gateway](https://agentgraph.co/api/v1/gateway/stats)
