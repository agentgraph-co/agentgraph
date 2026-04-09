# OpenClaw Security Scan — Social Media Posts

Data source: AgentGraph security scanner results (25 OpenClaw skills)
Article link: https://dev.to/agentgraph/we-scanned-25-openclaw-skills-for-security-vulnerabilities-heres-what-we-found

---

## Bluesky Post (300 chars max)

We scanned 25 OpenClaw skills for security vulnerabilities.

1,195 findings. 25 critical. Average trust score: 51/100.

Their own skill registry scored 0/100. Their security plugin also scored 0/100.

Scanner is open source. Full results: [DEV.TO LINK]

---

## Twitter/X Thread

### Tweet 1 (hook)

We scanned 25 popular OpenClaw skills for security vulnerabilities.

1,195 findings. 25 critical, 615 high, 555 medium.

Average trust score: 51/100. Over a third scored below 20.

Thread with results:

### Tweet 2 (the irony)

The two most notable results:

OpenClaw's official skill registry (clawhub) scored 0/100.

Their security plugin (secureclaw) also scored 0/100.

The tools meant to secure the ecosystem are themselves among the least secure packages in it.

### Tweet 3 (what we built)

We built an open-source scanner that runs static analysis across agent skill repos and produces a trust score from 0-100.

Results are published as cryptographically signed attestations (Ed25519, JWS) — verifiable by anyone against our public JWKS.

Available as an MCP tool for Claude Code and any agent framework.

### Tweet 4 (CTA)

Check your own tools:

pip install agentgraph-trust

Works with Claude Code, Cursor, any MCP client. Returns signed security attestations you can verify.

Full breakdown: [DEV.TO LINK]

Scanner is open source: github.com/agentgraph-co/agentgraph

---

## HuggingFace Community Post

**Title:** Security scan of 25 OpenClaw skills: 1,195 vulnerabilities, average trust score 51/100

AI agent ecosystems are growing fast, but security tooling has not kept pace. We ran our open-source security scanner against 25 of the most popular OpenClaw skills to measure the current state of supply-chain security in agent tool registries.

The results: 1,195 total findings across 25 repositories. 25 critical-severity issues, 615 high, 555 medium. The average trust score was 51.1 out of 100, and 36% of scanned skills scored below 20.

Two results stand out. OpenClaw's own skill registry (clawhub) and their security plugin (secureclaw) both scored 0 out of 100. The infrastructure meant to vet and secure the ecosystem carries the highest risk.

This matters for anyone building with agent frameworks. When an LLM selects and executes a tool, it inherits that tool's attack surface. There is no human in the loop checking whether a skill dependency has unsafe execution patterns or an overly broad permission scope.

We published the scanner as an open-source MCP tool. Scan results are recorded as cryptographically signed attestations (Ed25519, JWS) — verifiable by anyone against our public JWKS endpoint.

Full methodology and per-repo results: https://dev.to/agentgraph/we-scanned-25-openclaw-skills-for-security-vulnerabilities-heres-what-we-found

---

## GitHub Discussion Post

**Title:** Security audit results: 25 OpenClaw skills scanned, 1,195 findings

**Body:**

We ran the AgentGraph security scanner against 25 of the most-installed OpenClaw skills. This post summarizes the results and links to the full report.

### Summary

| Metric | Value |
|---|---|
| Skills scanned | 25 |
| Total findings | 1,195 |
| Critical | 25 |
| High | 615 |
| Medium | 555 |
| Average trust score | 51.1 / 100 |
| Skills scoring below 20/100 | 36% (9 of 25) |
| Skills with critical findings | 4 |

### Notable results

- **clawhub** (OpenClaw's skill registry): 0/100
- **secureclaw** (OpenClaw's security plugin): 0/100

Both of these are infrastructure-level packages that other skills depend on. A compromised registry or security plugin has cascading impact across the ecosystem.

### Score distribution

```
  0-20:  ||||||||| 36%
 21-40:  |          4%
 41-60:              0%
 61-80:  |||||     20%
 81-100: |||||||||| 40%
```

The distribution is bimodal — skills are either clean or deeply problematic, with almost nothing in between.

### Methodology

The scanner performs static analysis on source code, checking for:
- Hardcoded secrets (API keys, tokens, credentials)
- Unsafe execution patterns (subprocess, eval, exec, shell=True)
- Unbounded file system access
- Data exfiltration patterns (outbound calls to unexpected destinations)
- Code obfuscation (base64 payloads, dynamic imports)

It also detects positive signals: auth checks, input validation, rate limiting. Trust score (0-100) is computed from weighted findings offset by positive signals and best practices (README, LICENSE, tests). Results are published as cryptographically signed attestations (Ed25519, JWS).

### Links

- Full report: https://dev.to/agentgraph/we-scanned-25-openclaw-skills-for-security-vulnerabilities-heres-what-we-found
- Scanner source: `src/scanner/` in this repo
- Scan script: `scripts/scan_openclaw_skills.py`
- MCP server: `sdk/mcp-server/agentgraph_trust/`

### Next steps

We plan to expand coverage beyond OpenClaw to other agent skill registries and framework plugin ecosystems. If you want a specific repo scanned, open an issue.
