# AgentGraph Recruitment — Round 2

Drafted 2026-03-29. Each section includes a new Discussion/Issue post AND thread responses where relevant conversations already exist.

---

## 1. google/A2A (a2aproject/A2A) — 22.9K stars

### New Discussion Post (Show and Tell)

**Title:** AgentGraph — trust scoring and verified identity infrastructure for A2A agents

Hey A2A community! We've been following the identity and trust discussions here (#1672, #1501, #1628) and wanted to share what we've built — much of it directly addresses the problems being discussed.

[AgentGraph](https://agentgraph.co) is open-source trust infrastructure for AI agents. The core idea: every agent should have a **verifiable identity** (W3C DID) and a **trust score** backed by automated security analysis — not self-reported claims.

### What you get (~2 min)

1. **Import your agent from GitHub** — capabilities, framework, and metadata auto-detected
2. **Verified identity** — your agent gets a [W3C DID](https://www.w3.org/TR/did-core/), so identity is cryptographically verifiable across frameworks
3. **Automated security scan** — checks for hardcoded secrets, unsafe execution, data exfiltration, code obfuscation
4. **Trust score** (0-100) — deductions for findings, bonuses for security best practices
5. **Multi-source trust signals** — automatically discovers your project across npm, PyPI, Docker Hub, HuggingFace and aggregates community signals (stars, downloads, pulls) into the score
6. **README badge** — embeddable SVG that updates with each scan:

```markdown
[![AgentGraph Trust Score](https://agentgraph.co/api/v1/bots/YOUR_ENTITY_ID/badge.svg?style=compact&theme=dark)](https://agentgraph.co/profile/YOUR_ENTITY_ID)
```

### Why this matters for A2A

The Agent Card spec defines metadata fields for agent identity, but verification is left to external mechanisms. When Agent A delegates a task to Agent B, how do you verify B's capabilities and security posture? Right now you're trusting a JSON document and hoping for the best.

AgentGraph provides that verification layer:
- **DIDs for portable identity** — an agent's identity follows it across A2A, MCP, and any other protocol
- **Trust scores from actual analysis** — not self-reported, not just "who signed the cert"
- **Cross-registry signals** — if your agent has a GitHub repo, npm package, and Docker image, all three feed the trust score
- **Social graph** — community endorsements from developers who've used and vetted the agent

We're working toward A2A integration where an agent could check another agent's trust score before accepting a delegation — but the foundation starts with getting agents scanned, verified, and scored.

**Free for all open-source projects.** [agentgraph.co](https://agentgraph.co) | [Source](https://github.com/agentgraph-co/agentgraph)

---

### Thread Response: #1672 — "Agent Identity Verification for Agent Cards" (97 comments)

> This is a great thread. We've been building [AgentGraph](https://agentgraph.co) which addresses several of the problems discussed here — specifically the gap between "identity" (who is this agent?) and "trust" (should I delegate work to it?).
>
> Our approach:
> - **W3C DIDs** for portable, cryptographically verifiable agent identity — not tied to any single framework or hosting provider
> - **Automated security scanning** of the agent's source code — checks for hardcoded secrets, unsafe exec, data exfiltration, obfuscation
> - **Trust score (0-100)** derived from scan results + community signals (stars, downloads, endorsements) — not self-reported
> - **Multi-source discovery** — import from GitHub and we automatically find the same project on npm, PyPI, Docker Hub, HuggingFace and aggregate signals
>
> The key insight from this discussion: Agent Card identity verification needs both *identity binding* (is this agent who it claims to be?) and *trust assessment* (should I work with it?). TLS and JWS handle the first part. AgentGraph handles the second.
>
> Everything is open source: [github.com/agentgraph-co/agentgraph](https://github.com/agentgraph-co/agentgraph). Any A2A agent can get a free scan + badge at [agentgraph.co](https://agentgraph.co).

### Thread Response: #1501 — "Trust scoring extension for agent-to-agent delegation" (33 comments)

> Following this discussion closely — trust scoring for delegation is exactly what we've built at [AgentGraph](https://agentgraph.co).
>
> Our trust score is computed from:
> - Automated security scan results (hardcoded secrets, unsafe exec, data exfiltration patterns)
> - Community signals aggregated across registries (GitHub stars/forks, npm downloads, PyPI downloads, Docker pulls)
> - Verification status (OAuth-verified vs. self-claimed identity)
> - Community endorsements from other developers
> - Agent evolution trail (auditable history of changes)
>
> The `trust.signals[]` extension work in #1628 maps well to how we structure this. If A2A standardizes a signal format, AgentGraph could serve as one of the signal providers — "this agent was scanned on date X, score Y, findings Z."
>
> Open source: [github.com/agentgraph-co/agentgraph](https://github.com/agentgraph-co/agentgraph)

### Thread Response: #1628 — "trust.signals[] extension" (18 comments)

> The signal type taxonomy here is solid. From our experience building trust scoring at [AgentGraph](https://agentgraph.co), a few signals we've found high-value:
>
> - **security_scan**: automated static analysis results (severity, finding count, scan date)
> - **cross_registry**: same project discovered across multiple registries (GitHub + npm + PyPI + Docker) with aggregated community metrics
> - **verification_status**: how was identity verified — OAuth, challenge-response, or self-claimed? The weight should differ significantly.
> - **evolution_trail**: hash-linked history of agent changes — has this agent been stable or is it changing rapidly?
>
> We'd be happy to align our attestation output format with whatever `trust.signals[]` standardizes. Open source at [github.com/agentgraph-co/agentgraph](https://github.com/agentgraph-co/agentgraph).

---

## 2. modelcontextprotocol/modelcontextprotocol — 7.7K stars

### New Discussion Post (Show and Tell)

**Title:** AgentGraph — trust verification and security scanning for MCP servers

Hey MCP community! We've been watching the identity and security discussions here (SEP-2395, SEP-1289, #544) and wanted to share what we've built.

[AgentGraph](https://agentgraph.co) is open-source trust infrastructure for AI agents and MCP servers. We already have a working **MCP bridge** (10 tools) and a **security scanner** that checks MCP server repos for vulnerabilities.

### What you get (~2 min)

1. **Import your MCP server from GitHub** — auto-detects MCP patterns, tools, and framework
2. **Automated security scan** — checks for hardcoded secrets, unsafe tool definitions, data exfiltration patterns, command injection in tool implementations
3. **Trust score** (0-100) with detailed breakdown
4. **Verified identity** — [W3C DID](https://www.w3.org/TR/did-core/) for cryptographically verifiable server identity
5. **Multi-source discovery** — finds your project across npm, PyPI, Docker Hub automatically
6. **README badge:**

```markdown
[![AgentGraph Trust Score](https://agentgraph.co/api/v1/bots/YOUR_ENTITY_ID/badge.svg?style=compact&theme=dark)](https://agentgraph.co/profile/YOUR_ENTITY_ID)
```

### Why this matters for MCP

MCP's security model currently focuses on transport (OAuth, mTLS) and data labeling. What's missing is a way to verify the *identity and trustworthiness* of the server itself before your agent connects to it. As the Alibaba Cloud team flagged in #544, the attack surface grows with every new MCP server in the ecosystem.

AgentGraph addresses this:
- **Pre-connection trust check** — verify a server's trust score before your agent uses it
- **Supply chain scanning** — catches issues in dependencies, not just the server code
- **Cross-registry signals** — if the server also ships as an npm package and Docker image, all signals feed the score
- **MCP bridge** — our own MCP server exposes trust verification as tools that agents can call

**Free for all open-source MCP servers.** [agentgraph.co](https://agentgraph.co) | [Source](https://github.com/agentgraph-co/agentgraph)

---

### Thread Response: SEP-2395 — "MCPS — Cryptographic Security Layer for MCP" (9 comments)

> Great proposal. We've been building in a similar direction at [AgentGraph](https://agentgraph.co) — specifically the agent identity verification and tool definition integrity pieces.
>
> Our implementation uses W3C DIDs for server identity and automated security scanning for integrity verification. One thing we've found valuable that MCPS could benefit from: **trust scoring** that goes beyond binary pass/fail. A server with a minor finding (e.g., a non-critical dependency CVE) shouldn't be treated the same as one with active data exfiltration patterns. Severity-weighted scoring gives consumers a gradient to make informed decisions.
>
> Happy to share our scan methodology and scoring algorithm — everything is open source at [github.com/agentgraph-co/agentgraph](https://github.com/agentgraph-co/agentgraph).

### Thread Response: #544 — "MCP protocol exhibits insufficient security design" (19 comments, Alibaba Cloud)

> This thread aged well. The attack vectors Alibaba Cloud identified — OAuth credential theft, server impersonation, malicious tool injection — are exactly what we encounter when scanning MCP server repos at [AgentGraph](https://agentgraph.co).
>
> We've now scanned hundreds of MCP server repos and the most common findings are:
> - Hardcoded API keys/tokens in server implementations
> - Tool definitions with unrestricted file system or network access
> - No input validation on tool parameters (injection vectors)
> - Dependencies with known CVEs
>
> We publish trust scores and scan results publicly so MCP consumers can check before connecting. Any MCP server maintainer can get a free scan at [agentgraph.co](https://agentgraph.co) — takes about 30 seconds from GitHub import.

---

## 3. crewAIInc/crewAI — 47.5K stars

### New Discussion Post (Show and Tell)

**NOTE:** We already have an open issue (#5153) on CrewAI. Consider responding to existing threads instead of creating a new discussion to avoid appearing spammy.

### Thread Response: #4254 — "How are people handling paid external APIs for autonomous agents?" (21 comments)

> This is the trust problem in practice — when your crew calls an external tool autonomously, you're trusting that tool's identity and behavior without verification.
>
> We built [AgentGraph](https://agentgraph.co) to address exactly this. Any tool or agent can get a verified identity (W3C DID) and trust score based on automated security scanning — not self-reported claims. The score factors in code security, community signals (stars, downloads), and verification status.
>
> For CrewAI specifically: before your crew uses a tool from an unknown author, you could check its AgentGraph trust score. We're building toward runtime trust checks, but today any tool maintainer can get scanned and scored for free at [agentgraph.co](https://agentgraph.co).

### Thread Response: #4232 — "Managing agentic LLM systems in production" (14 comments)

> Production governance for multi-agent systems needs two things most tools don't provide: **verifiable identity** (which agent did what?) and **auditable trails** (what changed and when?).
>
> [AgentGraph](https://agentgraph.co) provides both — W3C DIDs for agent identity and evolution tracking that creates an auditable history of every agent change. Combined with trust scoring from automated security scans, you get a governance layer that answers "can I trust this agent?" and "what has it done?"
>
> Open source: [github.com/agentgraph-co/agentgraph](https://github.com/agentgraph-co/agentgraph)

---

## 4. BerriAI/litellm — 41.4K stars

### New Discussion Post (Show and Tell)

**Title:** AgentGraph — trust verification and security scanning for AI agent tools

Hey LiteLLM community! Following the supply chain discussion (#24575) and the AgentShield thread (#23545), wanted to share what we've built.

[AgentGraph](https://agentgraph.co) is open-source trust infrastructure for AI agents. We scan agent/tool repos for security vulnerabilities and generate trust scores — designed to complement gateway/proxy tools like LiteLLM.

### What you get (~2 min)

1. **Import your agent/tool from GitHub** — auto-detects framework and capabilities
2. **Automated security scan** — hardcoded secrets, unsafe execution, data exfiltration, supply chain issues
3. **Trust score** (0-100) with per-finding breakdown
4. **Multi-source discovery** — finds your project across npm, PyPI, Docker Hub, HuggingFace
5. **Verified identity** — W3C DID for cryptographically verifiable tool identity
6. **README badge:**

```markdown
[![AgentGraph Trust Score](https://agentgraph.co/api/v1/bots/YOUR_ENTITY_ID/badge.svg?style=compact&theme=dark)](https://agentgraph.co/profile/YOUR_ENTITY_ID)
```

### How it complements LiteLLM

LiteLLM brilliantly solves routing, cost management, and guardrails for LLM calls. AgentGraph solves the identity and trust side: **who** is making those calls, and **can you trust the tools** they're using?

After the recent supply chain incident, trust verification isn't optional anymore. LiteLLM handles the "how" of reaching LLMs safely. AgentGraph handles the "who" and "should we trust them."

**Free for all open-source projects.** [agentgraph.co](https://agentgraph.co) | [Source](https://github.com/agentgraph-co/agentgraph)

---

### Thread Response: #24575 — "Supply Chain Incident — Friday Townhall" (timely, post-breach)

> Supply chain attacks on AI tooling are going to accelerate. We built [AgentGraph](https://agentgraph.co) specifically for this — automated security scanning of agent/tool repos that catches hardcoded secrets, unsafe exec patterns, data exfiltration, and dependency vulnerabilities.
>
> Every scanned project gets a trust score (0-100) and verified identity (W3C DID). We also do multi-source discovery — import from GitHub and we automatically check npm, PyPI, Docker Hub for the same project and aggregate signals.
>
> Free for open-source projects. Would love to hear what signals would be most useful for the LiteLLM community to see in a trust score.

---

## 5. microsoft/agent-framework — 8.3K stars

### New Discussion Post (Show and Tell)

**Title:** AgentGraph — trust verification for third-party agent interactions

Hey Agent Framework community! Your README rightly notes that interacting with third-party servers or agents carries risk. We've been building infrastructure to reduce that risk.

[AgentGraph](https://agentgraph.co) is open-source trust infrastructure for AI agents. Import a GitHub repo and in ~2 minutes you get a security scan, trust score, verified identity, and embeddable badge.

### What you get

1. **Automated security scan** — hardcoded secrets, unsafe execution, data exfiltration, code obfuscation, supply chain issues
2. **Trust score** (0-100) with detailed breakdown and per-finding severity
3. **Verified identity** — [W3C DID](https://www.w3.org/TR/did-core/) for cryptographically verifiable agent identity
4. **Multi-source trust signals** — discovers your project across npm, PyPI, Docker Hub, HuggingFace automatically
5. **README badge:**

```markdown
[![AgentGraph Trust Score](https://agentgraph.co/api/v1/bots/YOUR_ENTITY_ID/badge.svg?style=compact&theme=dark)](https://agentgraph.co/profile/YOUR_ENTITY_ID)
```

### Why this matters for Agent Framework

When building with the Microsoft Agent Framework, you often integrate external agents and tools. The current security model relies on transport-level security (OAuth, API keys), but that only answers "is this connection authenticated?" — not "is this agent trustworthy?"

AgentGraph answers the trust question:
- **Pre-integration scan** — check a tool's security posture before adding it to your workflow
- **Verified identity** — DIDs that follow the agent across frameworks (Agent Framework, AutoGen, CrewAI, MCP)
- **Community signals** — aggregated from GitHub, npm, PyPI, Docker Hub

We also posted on the AutoGen repo (#7476) and got great feedback from the community. Would love to hear from Agent Framework users too.

**Free for all open-source projects.** [agentgraph.co](https://agentgraph.co) | [Source](https://github.com/agentgraph-co/agentgraph)

---

### Thread Response: #4363 — "Standardized Skill Manifest for Agent Security" (mentions Moltbook)

> This proposal resonates strongly. The "unsigned binaries" analogy is exactly right — the agent ecosystem today is where software was before code signing became standard.
>
> We've been building [AgentGraph](https://agentgraph.co) to address this: every agent/tool gets a verified identity (W3C DID) and a trust score from automated security scanning. The Moltbook security failures you reference (35K emails + 1.5M API tokens leaked) are exactly why we started — identity and trust can't be an afterthought.
>
> A standardized skill manifest + AgentGraph's trust scoring would be a powerful combination: the manifest declares capabilities, AgentGraph verifies security posture and tracks evolution. Open source at [github.com/agentgraph-co/agentgraph](https://github.com/agentgraph-co/agentgraph).

---

## 6. microsoft/autogen — Existing Thread Responses

### Thread Response: Discussion #7485 — "HDP — cryptographic chain-of-custody for multi-agent delegation" (new, today)

> Interesting approach. Chain-of-custody for delegation is critical — at [AgentGraph](https://agentgraph.co) we tackle this through evolution tracking (hash-linked history of every agent change) and W3C DIDs for identity continuity across delegations. The cryptographic audit trail means you can verify not just who delegated, but what version of the agent was running at delegation time.
>
> Would be curious how HDP handles identity verification at each hop — that's where DID-based identity shines over session-based approaches.

### Thread Response: Discussion #7481 — "A minimal HTTP registry + signal board for AI agents" (new, today)

> Nice work on the minimal registry concept. We've been building [AgentGraph](https://agentgraph.co) as a more comprehensive version of this — registry + trust scoring + security scanning + social graph. The signal board idea maps well to our trust score breakdown (security scan results, community signals, verification status).
>
> One thing we've found valuable: **multi-source discovery**. When you import from GitHub, we automatically check npm, PyPI, Docker Hub, and HuggingFace for the same project and aggregate all community signals into the trust score. Gives a much fuller picture than any single registry.

---

## Posting Strategy

### Priority Order
1. **a2aproject/A2A** — Post discussion + respond to #1672 (97 comments), #1501 (33 comments), #1628 (18 comments). Highest engagement, most relevant threads.
2. **modelcontextprotocol/modelcontextprotocol** — Post discussion + respond to SEP-2395 and #544. Security-focused community.
3. **BerriAI/litellm** — Post discussion + respond to #24575 (supply chain incident, timely).
4. **microsoft/agent-framework** — Post discussion + respond to #4363 (mentions Moltbook).
5. **crewAIInc/crewAI** — Thread responses only (already have #5153 open). Respond to #4254 and #4232.
6. **microsoft/autogen** �� Thread responses to #7485 and #7481 (both from today).

### Spacing
- Don't post all on the same day — spread over 2-3 days
- Do thread responses first (less visible, warms up presence)
- Post new discussions the next day

### Tone Guidelines (from Round 1)
- Lead with what they get, not what we are
- Badge CTA in every new discussion post
- Thread responses: address the specific problem, mention AgentGraph naturally, link to source
- Never more than one new discussion per repo
- Close with "free for open source" + links
