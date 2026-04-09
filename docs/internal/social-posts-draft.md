# Social Posts Draft — INTERNAL REVIEW ONLY

## Bluesky Thread (3 posts)

### Post 1
We scanned 78 of the top 100 OpenClaw skills. 3,924 security findings.

35 critical across 7 repos. 26% of skills scored F (0-20). Average trust score: 63.8/100.

Top categories: filesystem access (2,074 findings), unsafe exec (1,781), data exfiltration (43), hardcoded secrets (23).

Context-aware scanning means MCP tool servers get scored differently — filesystem access in a file server is expected. This reduced false positives dramatically.

### Post 2
Also shipped:
• Trust gateway proxy — one API call checks trust + enforces rate limits
• Multi-provider aggregation — queries RNWY behavioral + MoltBridge interaction data alongside our scan
• Per-finding remediation hints — not just "what's wrong" but "how to fix it"
• Signed JWS decisions for audit trails

### Post 3
Try it:
curl agentgraph.co/api/v1/public/scan/crewAIInc/crewAI

No auth needed. Returns trust tier, category sub-scores, and a signed attestation you can verify against our JWKS.

Also: pip install agentgraph-trust for the MCP tool.

We're one of 9 verified issuers in the multi-attestation working group.

---

## Dev.to Article Ideas

### Option A: "Context-Aware Security Scanning for AI Agent Tools"
- The problem: generic scanners flag MCP servers for doing their job
- Our solution: detect MCP context, discount expected patterns
- Data: 78 repos scanned (OpenClaw Top 100), 3,924 findings, before/after comparison
- How to use: curl examples, pip install
- ~800 words

### Option B: "We Built a Trust Gateway Proxy for AI Agents"
- The problem: agents connect to tools without checking trust
- Our solution: one API call returns allow/block + signed decision
- Multi-provider: security scan + behavioral + identity from different providers
- Framework integration: works with any framework
- ~1000 words

### Option C: "I Scanned 78 OpenClaw Skills — Here's What I Found"
- Massive scale-up from the original 25-repo scan to 78 repos (OpenClaw Top 100)
- 3,924 total findings: 35 critical, 1,633 high, 2,256 medium
- Average trust score: 63.8/100 — 26% of skills score F, 56% score A/A+
- Top categories: filesystem access (2,074), unsafe exec (1,781), exfiltration (43), hardcoded secrets (23)
- Constructive framing with remediation hints
- ~1200 words

**Recommended: Option C** — the scale (78 repos, nearly 4K findings) makes this far more compelling than the original 25-repo article. Most shareable data angle.
