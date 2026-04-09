# Community Hub Posts — Draft v2

## 1. jlowin/fastmcp — Discussion (Show and tell)

**Title:** Free security scanning + trust badges for MCP servers

**Body:**

Hey FastMCP community! We built [AgentGraph](https://agentgraph.co) — open-source trust infrastructure for AI agents — and wanted to share something that might be useful for MCP server authors.

### What it does

Import your MCP server's GitHub repo and in ~2 minutes you get:

- **Automated security scan** — checks for hardcoded secrets, unsafe execution patterns (`shell=True`, `eval()`), data exfiltration, code obfuscation
- **Trust score** (0-100) based on scan findings, positive security signals, and project health
- **Verified identity** — your server gets a [W3C DID](https://www.w3.org/TR/did-core/) (decentralized identifier), so clients can cryptographically verify who they're talking to
- **Embeddable badge** for your README (4 styles, multiple sizes)

### Badge example

Drop this in your README and it updates automatically with each scan:

```markdown
[![AgentGraph Trust Score](https://agentgraph.co/api/v1/bots/YOUR_ENTITY_ID/badge.svg?style=compact&theme=dark)](https://agentgraph.co/profile/YOUR_ENTITY_ID)
```

### Quick setup (~2 min)

1. Sign up at [agentgraph.co](https://agentgraph.co)
2. Import your GitHub repo — capabilities, framework, and metadata are auto-detected
3. Security scan runs automatically
4. Copy your badge embed code from the Badge Studio

The scanner checks for real issues — not just linting. It flags patterns like `shell=True` in subprocess calls, hardcoded API keys, outbound data exfiltration, and obfuscated code. It also recognizes positive signals like authentication checks, input validation, rate limiting, and CORS configuration.

False positive? Suppress individual lines with `# ag-scan:ignore` — [full docs here](https://github.com/agentgraph-co/agentgraph/blob/main/docs/security-scan-false-positives.md).

### Why this matters

MCP servers execute code on users' machines. As the ecosystem grows, users need a way to evaluate which servers to trust. A verified identity + security scan gives users confidence that a server is what it claims to be and has been vetted for common vulnerability patterns.

Free for all open-source projects. [AgentGraph is open source](https://github.com/agentgraph-co/agentgraph) — feedback and contributions welcome.

---

## 2. microsoft/autogen — Discussion (Show and tell)

**Title:** AgentGraph — open-source trust verification for AI agents

**Body:**

Hi AutoGen community! Sharing a project that addresses a growing concern in multi-agent systems: **how do you know which agents and tools to trust?**

[AgentGraph](https://agentgraph.co) is open-source trust infrastructure for AI agents. Import a GitHub repo and in ~2 minutes you get a security scan, trust score, verified identity, and an embeddable badge.

### What you get

- **Automated security scan** — checks for hardcoded secrets, unsafe execution, data exfiltration, code obfuscation
- **Trust score** (0-100) — deductions for findings, bonuses for security best practices (auth checks, input validation, rate limiting)
- **Verified identity** — every agent gets a [W3C DID](https://www.w3.org/TR/did-core/) (decentralized identifier) so its identity is cryptographically verifiable, not just a display name
- **Trust-scored social graph** — see how agents relate to each other, with community endorsements from other developers
- **README badge** — shows your trust score, updates automatically with each scan:

```markdown
[![AgentGraph Trust Score](https://agentgraph.co/api/v1/bots/YOUR_ENTITY_ID/badge.svg?style=compact&theme=dark)](https://agentgraph.co/profile/YOUR_ENTITY_ID)
```

### Why this matters for AutoGen

Multi-agent conversations involve tools calling other tools. When an AutoGen agent uses an MCP server or external tool, there's currently no standard way to verify that tool's identity or security posture. You're trusting a display name and hoping for the best.

AgentGraph provides that verification layer — verified identity (DID) + automated security scan + trust score. We already have bridges for multiple agent frameworks and are working toward runtime trust checks (verify before execution).

**Try it:** [agentgraph.co](https://agentgraph.co) — free scan + badge in ~2 minutes. We're in early access and would genuinely love feedback.

[Source code](https://github.com/agentgraph-co/agentgraph) | [Scan false-positive docs](https://github.com/agentgraph-co/agentgraph/blob/main/docs/security-scan-false-positives.md)

---

## 3. crewAIInc/crewAI — Discussion (Show and tell)

**Title:** Trust verification for AI agent crews — AgentGraph (open source)

**Body:**

Hey CrewAI community! As agent crews get more complex and pull in tools from different authors, we think trust verification is going to become essential. Sharing what we've built.

[AgentGraph](https://agentgraph.co) is open-source trust infrastructure for AI agents. The core idea: every agent and tool should have a **verifiable identity** and a **trust score** based on actual security analysis — not self-reported claims.

### What you get (~2 min setup)

1. **Import your tool/agent from GitHub** — capabilities, framework, and metadata auto-detected
2. **Verified identity** — your agent gets a [W3C DID](https://www.w3.org/TR/did-core/) (decentralized identifier), so its identity is cryptographically verifiable
3. **Automated security scan** — checks for hardcoded secrets, unsafe execution, data exfiltration, code obfuscation
4. **Trust score** (0-100) — deductions for findings, bonuses for best practices (auth, input validation, rate limiting)
5. **README badge** — embeddable SVG that updates with each scan:

```markdown
[![AgentGraph Trust Score](https://agentgraph.co/api/v1/bots/YOUR_ENTITY_ID/badge.svg?style=compact&theme=dark)](https://agentgraph.co/profile/YOUR_ENTITY_ID)
```

6. **Public profile** — trust breakdown, scan results, community endorsements, and an auditable trail of your agent's evolution

### Why this matters for CrewAI

When you're assembling a crew with tools from different authors, trust is implicit. You're hoping the tool does what it says and nothing else. A verified identity + security scan backed trust badge gives you (and your users) a quick signal about whether a tool has been vetted.

We're building toward runtime trust checks — verify a tool's identity and trust score before your crew uses it — but the foundation starts with getting tools scanned, verified, and scored.

**Free for all open-source projects.** [agentgraph.co](https://agentgraph.co) — we're in early access and would love feedback.

[GitHub](https://github.com/agentgraph-co/agentgraph) — contributions welcome.

---

## 4. pydantic/pydantic-ai — Issue (Feature request)

**Title:** Integration: AgentGraph trust verification for PydanticAI agents

**Body:**

### Feature request

We've built [AgentGraph](https://agentgraph.co), open-source trust infrastructure for AI agents, and we already have a working **PydanticAI bridge** that scans PydanticAI agent definitions for security issues.

### What it does today

- Scans PydanticAI agent repos for security vulnerabilities (hardcoded secrets, unsafe tool definitions, data exfiltration patterns)
- Detects PydanticAI-specific patterns:
  - Tools with unrestricted system access
  - Result validators that can be manipulated
  - Untyped results that bypass validation
  - Command injection in tool implementations
- Generates a trust score (0-100) based on findings and positive security signals
- Issues a verified identity ([W3C DID](https://www.w3.org/TR/did-core/)) so agent identity is cryptographically verifiable
- Provides embeddable trust badges for READMEs:

```markdown
[![AgentGraph Trust Score](https://agentgraph.co/api/v1/bots/YOUR_ENTITY_ID/badge.svg?style=compact&theme=dark)](https://agentgraph.co/profile/YOUR_ENTITY_ID)
```

### What we'd love to explore

A lightweight integration where PydanticAI agents could optionally verify the trust score and identity of MCP servers or external tools before using them:

```python
from pydantic_ai import Agent
from agentgraph import trust_check

agent = Agent('openai:gpt-4o', tools=[
    trust_check(min_score=70),  # verify identity + trust before execution
])
```

### Try it (~2 min)

Any PydanticAI project can get a free security scan + verified identity + trust badge at [agentgraph.co](https://agentgraph.co) — import your GitHub repo and it runs automatically.

[AgentGraph source](https://github.com/agentgraph-co/agentgraph) | [Scanner false-positive docs](https://github.com/agentgraph-co/agentgraph/blob/main/docs/security-scan-false-positives.md)

Happy to discuss integration approaches if there's interest.

---

## 5. appcypher/awesome-mcp-servers — PR (add listing)

**Title:** Add AgentGraph — trust verification and security scanning for MCP servers

**PR body:**

Adds AgentGraph to the Security section (or Tools section if no Security category exists).

**AgentGraph** — Open-source trust infrastructure for MCP servers. Verified identity (W3C DIDs), automated security scanning (secrets, unsafe exec, exfiltration, obfuscation), trust scoring (0-100), and embeddable README badges.

- Website: https://agentgraph.co
- GitHub: https://github.com/agentgraph-co/agentgraph
- License: AGPL-3.0

**README entry to add:**

```markdown
- [AgentGraph](https://agentgraph.co) - Trust verification and security scanning for MCP servers. Verified identity (W3C DIDs), automated vulnerability detection, trust scoring, and embeddable badges. ([Source](https://github.com/agentgraph-co/agentgraph))
```
