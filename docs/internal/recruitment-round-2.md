# AgentGraph Recruitment — Round 2 (Revised)

Drafted 2026-03-29, revised 2026-04-06 based on deep dive findings.

**Lessons learned from Round 1 & research:**
- Several threads we targeted are now **closed** (#1501, SEP-2395, #544)
- MCP maintainers are actively flagging promotional content — skip the main MCP repo entirely
- AutoGen #7485 and #7481 are from coordinated spam accounts (64R3N, yuquan2088) — do not engage
- Agent Framework #4363 has zero engagement — dead thread
- lobehub auto-closes external discussions quickly
- Lead with technical substance, not product pitch. Answer the question first, mention AgentGraph second.

---

## 1. google/A2A (a2aproject/A2A) — 22.9K stars

### New Discussion Post (Show and Tell) → [Create New Discussion](https://github.com/a2aproject/A2A/discussions/new?category=show-and-tell)

**Title:** AgentGraph — trust scoring and verified identity infrastructure for A2A agents

Hey A2A community! We've been following the identity and trust discussions here (#1672, #1628) and wanted to share what we've built — much of it directly addresses the problems being discussed.

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

### Thread Response → [#1672 — "Agent Identity Verification for Agent Cards"](https://github.com/a2aproject/A2A/discussions/1672) (97 comments, OPEN)

> Interesting discussion. The core tension here is that identity binding (TLS, JWS) and trust assessment are fundamentally different problems — you can cryptographically prove *who* an agent is without saying anything about *whether you should work with it*.
>
> We've been working on the trust assessment side at [AgentGraph](https://agentgraph.co). Our approach:
> - **W3C DIDs** for portable identity — not tied to a single framework or hosting provider, so the same identity works across A2A, MCP, CrewAI, etc.
> - **Automated security scanning** of source repos — catches hardcoded secrets, unsafe exec, data exfiltration, obfuscation patterns
> - **Trust score (0-100)** from scan results + cross-registry community signals (GitHub, npm, PyPI, Docker Hub)
>
> The gap this fills: Agent Card verification answers "is this connection authentic?" AgentGraph answers "what's the security posture of the code behind it?" Both are needed for safe delegation.
>
> Open source: [github.com/agentgraph-co/agentgraph](https://github.com/agentgraph-co/agentgraph)

### Thread Response → [#1628 — "trust.signals[] extension"](https://github.com/a2aproject/A2A/discussions/1628) (18 comments, OPEN)

> The signal type taxonomy here is solid. A few observations from building trust scoring at [AgentGraph](https://agentgraph.co):
>
> - **Severity weighting matters more than pass/fail.** A single low-severity dependency CVE shouldn't tank a score the same way active data exfiltration patterns do. We use log-scaled severity weighting for scan findings.
> - **Cross-registry signals are underrated.** Same project on GitHub + npm + PyPI + Docker gives much higher confidence than any single source. Multi-source presence is a strong positive signal because it implies maintained, multi-platform distribution.
> - **Verification method should carry weight.** OAuth-verified identity vs. self-claimed makes a big difference. The `trust.signals[]` spec could benefit from a `verification_method` field with defined confidence levels.
>
> We'd be happy to align our attestation output format with whatever `trust.signals[]` standardizes — could serve as a signal provider. Open source at [github.com/agentgraph-co/agentgraph](https://github.com/agentgraph-co/agentgraph).

**NOTE:** #1501 is CLOSED — do not post there.

---

## 2. crewAIInc/crewAI — 47.5K stars

We already have an open issue ([#5153](https://github.com/crewAIInc/crewAI/issues/5153)). Respond to existing threads only — no new discussion.

### Thread Response → [#4254 — "How are people handling paid external APIs for autonomous agents?"](https://github.com/crewAIInc/crewAI/discussions/4254) (21 comments)

> For paid APIs specifically, a few patterns that work:
> - **Budget caps per tool per run** — set a hard dollar limit so a hallucinating agent can't burn through credits
> - **Cost-weighted routing** — cheaper tools get tried first, expensive ones only if cheap options fail or are unavailable
> - **Approval gates** — any tool call above $X requires human confirmation before execution
>
> The deeper issue is trust: when your crew calls an external tool autonomously, you're trusting that tool's behavior without verification. We've been working on this at [AgentGraph](https://agentgraph.co) — automated security scanning of tool repos with trust scores based on actual analysis (code security, community signals, verification status). The idea is to check a tool's posture before adding it to your workflow, not after something goes wrong.
>
> Open source: [github.com/agentgraph-co/agentgraph](https://github.com/agentgraph-co/agentgraph)

### Thread Response → [#4232 — "Managing agentic LLM systems in production"](https://github.com/crewAIInc/crewAI/discussions/4232) (14 comments)

> Production governance comes down to two things most multi-agent tools don't provide out of the box:
>
> 1. **Verifiable identity** — which agent did what? In a crew with 5+ agents calling external tools, you need attribution that doesn't rely on logging alone. Cryptographic identity (like W3C DIDs) gives you non-repudiable audit trails.
> 2. **Change tracking** — when an agent's behavior changes (model update, prompt change, tool swap), you need a diff. Without it, debugging production regressions is guesswork.
>
> We built [AgentGraph](https://agentgraph.co) around these two primitives — DIDs for identity and evolution tracking for auditable change history. Combined with trust scoring from security scans, it gives you a governance layer for "can I trust this agent?" and "what changed since it last worked?"
>
> Open source: [github.com/agentgraph-co/agentgraph](https://github.com/agentgraph-co/agentgraph)

---

## 3. BerriAI/litellm — 41.4K stars

**Approach:** Be careful here. LiteLLM had a real supply chain incident. Do NOT ambulance-chase the breach. Focus on the forward-looking discussion about preventing future incidents, and be genuinely helpful rather than opportunistic.

### Thread Response → [#24575 — "Supply Chain Incident — Friday Townhall"](https://github.com/BerriAI/litellm/discussions/24575) (if still active and accepting comments)

> One takeaway from this: the AI tooling ecosystem needs better pre-integration trust checks. Package signing and 2FA on maintainer accounts help, but they only cover the publisher side. There's no standard way for a consumer to check "has this tool been independently scanned for security issues?"
>
> We've been building [AgentGraph](https://agentgraph.co) for this — automated security scanning of agent/tool repos that checks for hardcoded secrets, unsafe exec patterns, data exfiltration, and dependency vulnerabilities. Every scanned project gets a trust score (0-100) and verified identity.
>
> Would be interested in what signals the LiteLLM community would find most useful in a trust score. The obvious ones (CVE count, dependency freshness, maintainer verification) are easy. The harder question is how to weight supply chain depth — a project with 200 transitive deps has a very different risk profile from one with 5.
>
> Open source: [github.com/agentgraph-co/agentgraph](https://github.com/agentgraph-co/agentgraph)

**Do NOT create a new Show and Tell discussion.** One thoughtful thread response is better than a promotional post in the wake of a security incident.

---

## 4. microsoft/autogen — Follow-up

### Follow-up → [#7476 — msaleme's response to our original post](https://github.com/microsoft/autogen/discussions/7476)

msaleme responded positively to our thread. Follow up with a substantive reply:

> @msaleme Thanks for the thoughtful response! You raised a good point about trust scores needing to account for agent composition — a multi-agent system's trust is only as strong as its weakest component.
>
> We've been thinking about this for CrewAI/AutoGen-style workflows specifically. Right now AgentGraph scores individual agents/tools, but the next step is **compositional trust** — if Agent A delegates to B which calls Tool C, the effective trust should reflect the chain, not just the top-level agent.
>
> Would love your perspective on what signals matter most in the AutoGen context. Is it more about verifying the *agent code* or the *tools it has access to*?
>
> You can try it now at [agentgraph.co](https://agentgraph.co) — import any GitHub repo and get a scan + trust score in about 2 minutes.

**Do NOT engage with #7485 or #7481** — these are from coordinated spam accounts (64R3N, yuquan2088, lan3344). Engaging legitimizes them.

---

## 5. microsoft/agent-framework — 8.3K stars

### New Discussion Post (Show and Tell) → [Create New Discussion](https://github.com/microsoft/agent-framework/discussions/new?category=show-and-tell)

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

When building with the Microsoft Agent Framework, you often integrate external agents and tools. Transport-level security (OAuth, API keys) answers "is this connection authenticated?" but not "is this agent trustworthy?"

AgentGraph answers the trust question:
- **Pre-integration scan** — check a tool's security posture before adding it to your workflow
- **Verified identity** — DIDs that follow the agent across frameworks (Agent Framework, AutoGen, CrewAI, MCP)
- **Community signals** — aggregated from GitHub, npm, PyPI, Docker Hub

**Free for all open-source projects.** [agentgraph.co](https://agentgraph.co) | [Source](https://github.com/agentgraph-co/agentgraph)

**NOTE:** Do NOT respond to #4363 — zero engagement, dead thread.

---

## Removed from Round 2

| Target | Reason |
|--------|--------|
| **MCP main repo** (entire section) | SEP-2395 closed, #544 closed, maintainers actively flagging promotional content |
| **A2A #1501** | Thread closed |
| **Agent Framework #4363** | Zero engagement, dead |
| **AutoGen #7485, #7481** | Coordinated spam accounts (64R3N, yuquan2088) — do not engage |
| **AINIRO.IO** | Promotional link-dropper, ignore |

---

## Posting Strategy

### Priority Order
1. **a2aproject/A2A** — [New Discussion](https://github.com/a2aproject/A2A/discussions/new?category=show-and-tell) + respond to [#1672](https://github.com/a2aproject/A2A/discussions/1672) and [#1628](https://github.com/a2aproject/A2A/discussions/1628). Highest engagement, most relevant threads.
2. **crewAIInc/crewAI** — Thread responses to [#4254](https://github.com/crewAIInc/crewAI/discussions/4254) and [#4232](https://github.com/crewAIInc/crewAI/discussions/4232). Answer the question first, AgentGraph second.
3. **microsoft/autogen** — Follow up with msaleme on [#7476](https://github.com/microsoft/autogen/discussions/7476) only. Genuine conversation continuation.
4. **BerriAI/litellm** — Single careful response to [#24575](https://github.com/BerriAI/litellm/discussions/24575) if still accepting comments. Do NOT create new discussion.
5. **microsoft/agent-framework** — [New Discussion](https://github.com/microsoft/agent-framework/discussions/new?category=show-and-tell). Lower priority — smaller community.

### Spacing
- Spread over 3-4 days minimum
- Thread responses first (days 1-2) — less visible, establishes presence
- New discussions on days 3-4
- Never more than 2 posts in a single day across all repos

### Tone Guidelines (updated)
- **Answer the question first.** If a thread asks about managing APIs, talk about API management. Mention AgentGraph after providing real value.
- **No ambulance-chasing.** Don't exploit security incidents for marketing. Be helpful, not opportunistic.
- **One touch per thread.** Post once, respond to replies. Don't bump your own posts.
- **Skip dead threads.** Zero engagement = nobody is reading. Don't waste the post.
- **Badge CTA in new discussions only.** Thread responses should be lighter — link to source, not a full feature list.
- **Close with "free for open source" + links** in every post.
- **Never engage with spam accounts** — even if they mention you or seem to agree with you. It legitimizes them.
