# Show HN Draft — INTERNAL REVIEW ONLY

## Title Options (under 80 chars)

1. Show HN: Open API that scans any GitHub repo and returns a signed trust score
2. Show HN: Context-aware security scanner for AI agent tools (MCP, LangChain, etc.)
3. Show HN: We built a trust gateway proxy for AI agent tool execution

**Recommended: Option 2** — highlights the context-awareness (our differentiator) and names the ecosystem.

---

## Body Comment (posted by you immediately after submission)

We built a public API that scans any GitHub repository for security issues and returns a cryptographically signed trust score. No auth required.

```
curl https://agentgraph.co/api/v1/public/scan/crewAIInc/crewAI
```

**What makes this different from generic code scanners:** Context-aware MCP detection. An MCP server that accesses the filesystem is doing its job — a regular library doing the same thing is suspicious. Our scanner detects MCP context (server.json, MCP dependencies) and adjusts scoring accordingly. This reduced false positives dramatically — Anthropic's official `modelcontextprotocol/servers` went from scoring 0/100 to 72/100 after we added context awareness.

**What we scanned:** We ran the OpenClaw Top 100 Security Scan — 78 repos scanned successfully out of 93 attempted. The results: 3,924 total security findings. 35 critical findings across 7 repos. 1,633 high-severity. 2,256 medium-severity. Average trust score: 63.8/100 (Grade B). 26% of skills scored F (0-20). The top finding categories tell the story: filesystem access (2,074 findings), unsafe exec (1,781), data exfiltration patterns (43), hardcoded secrets (23). Per-category sub-scores show exactly where the risk is: secret_hygiene, code_safety, data_handling, filesystem_access.

**The trust gateway:** Beyond scanning, we built an enforcement proxy. Agent frameworks call `POST /api/v1/gateway/check` before connecting to a tool. The response includes whether to allow/block, rate limits to apply, and a signed JWS decision for audit trails. One query returns our security scan PLUS signals from external providers (RNWY behavioral trust, MoltBridge interaction history, AgentID identity verification) — multi-dimensional trust from a single endpoint.

**Signed attestations matter** because you don't have to trust us. Fetch our JWKS at `/.well-known/jwks.json`, verify the Ed25519 signature yourself. We're one of 9 verified issuers in a multi-attestation working group where each provider covers a different trust dimension.

**What developers can do:**
- Scan any repo: `curl agentgraph.co/api/v1/public/scan/owner/repo`
- Check trust before execution: `POST /api/v1/gateway/check {"repo": "owner/repo"}`
- Install the MCP tool: `pip install agentgraph-trust`
- Import a bot for a full trust profile with identity + external signals

Each finding includes a remediation hint (e.g., "Move to environment variable"). The goal is to be constructive, not just score things.

Source: github.com/agentgraph-co/agentgraph

---

## Timing
- Post Tuesday-Thursday, 9-10am ET
- Monitor and respond to comments for 4-6 hours
- Key angles to prepare responses for:
  - "This is just grep with extra steps" → context-aware MCP detection, signed attestations, multi-provider aggregation
  - "False positives for tool servers" → exactly why we built MCP context awareness
  - "How is this different from Snyk/AgentSeal?" → we combine scanning + identity + enforcement gateway + multi-provider aggregation
  - "Who decides what's trusted?" → independent providers with signed attestations, not us alone
