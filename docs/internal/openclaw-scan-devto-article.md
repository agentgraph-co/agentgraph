---
title: "We Scanned 25 OpenClaw Skills for Security Vulnerabilities — Here's What We Found"
published: false
description: "1,195 findings across 25 popular OpenClaw skills. 36% scored below 20/100. Here's the data and a free tool to check your own."
tags: security, ai, agents, opensource
cover_image:
---

AI agents are running third-party code on your machine. Last week, [Anthropic announced extra charges for OpenClaw support in Claude Code](https://techcrunch.com/2026/04/04/anthropic-says-claude-code-subscribers-will-need-to-pay-extra-for-openclaw-support/), drawing fresh attention to the ecosystem. We wanted to answer a straightforward question: how safe are the most popular OpenClaw skills?

## Methodology

We used AgentGraph's [open-source security scanner](https://github.com/agentgraph-co/agentgraph) to analyze 25 popular OpenClaw skill repositories from GitHub. The scanner inspects source code for:

- **Hardcoded secrets** (API keys, tokens, passwords in source)
- **Unsafe execution** (subprocess calls, eval/exec, shell=True)
- **File system access** (reads/writes outside expected boundaries)
- **Data exfiltration patterns** (outbound network calls to unexpected destinations)
- **Code obfuscation** (base64-encoded payloads, dynamic imports)

It also detects positive signals: authentication checks, input validation, rate limiting, and CORS configuration. Each repo receives a trust score from 0 to 100.

## Results Summary

All 25 repositories scanned successfully. The aggregate numbers:

| Metric | Value |
|--------|-------|
| Repos scanned | 25 |
| Total findings | 1,195 |
| Critical | 25 |
| High | 615 |
| Medium | 555 |
| Repos with critical findings | 4 (16%) |
| Average trust score | 51.1 / 100 |
| Repos scoring below 20 | 9 (36%) |

Findings by category: file system access accounted for 707, unsafe execution patterns for 461, data exfiltration patterns for 26, and hardcoded secrets for 1.

## Score Distribution

| Score Range | Repos | Percentage |
|-------------|-------|------------|
| 0 - 20 | 9 | 36% |
| 21 - 40 | 1 | 4% |
| 41 - 60 | 0 | 0% |
| 61 - 80 | 5 | 20% |
| 81 - 100 | 10 | 40% |

The distribution is bimodal. Repos tend to be either clean or deeply problematic, with almost nothing in the middle. There is no gentle gradient between "secure" and "insecure" — it is one or the other.

## Notable Findings

**openclaw/clawhub** (official skill registry)
Score: 0/100. 2 critical, 228 high, 75 medium findings across 200 files. This is the registry that indexes skills for the broader ecosystem.

**adversa-ai/secureclaw** (OWASP security plugin)
Score: 0/100. 21 critical, 66 high, 177 medium findings. A security-focused plugin that itself has significant findings. The scanner flagged a high density of unsafe execution patterns and file system access.

**openclaw/openclaw** (main framework)
Score: 0/100. 1 critical, 14 high, 4 medium findings. The core framework that other skills build on.

**FreedomIntelligence/OpenClaw-Medical-Skills** (medical AI)
Score: 0/100. 1 critical, 30 high, 12 medium findings. Medical AI skills with critical findings deserve particular scrutiny given their potential deployment context.

Not all skills are problematic. **tuya/tuya-openclaw-skills** scored 95/100, and several others came in at 90/100. The clean repos demonstrate that writing secure OpenClaw skills is entirely achievable — it is just not the norm across the board.

## What This Means

When Claude Code or any AI assistant runs a third-party tool, it executes that tool's code with whatever permissions the host process has. If that code contains unsafe exec patterns, broad file system access, or exfiltration vectors, the attack surface is your machine — your files, your environment variables, your credentials.

The finding categories tell the story: 461 unsafe execution patterns means eval, exec, subprocess, and shell=True calls scattered across these codebases. 707 file system access findings means code reaching into the filesystem in ways that may not be bounded.

Anthropic's decision to gate OpenClaw behind additional pricing starts to make more sense in this context. The cost is not just computational — it is risk.

## Check Your Own Tools

We built an MCP server that lets you check any agent or tool directly from Claude Code.

Install:

```bash
pip install agentgraph-trust
```

Add to your Claude Code MCP config:

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

Then ask Claude: "Check the security of [agent name]"

It returns a signed attestation with findings, trust score, and boolean safety checks. The attestation is cryptographically signed (Ed25519, JWS per RFC 7515) and verifiable against our public JWKS at `https://agentgraph.co/.well-known/jwks.json`.

## Public API — Trust-Tiered Rate Limiting

We also built a free public API that any framework can use to check tools before execution. No authentication required.

```
GET https://agentgraph.co/api/v1/public/scan/{owner}/{repo}
```

The API returns a trust tier with recommended rate limits:

| Tier | Score | Rate Limit | Token Budget | User Confirm |
|------|-------|-----------|-------------|-------------|
| verified | 96-100 | unlimited | unlimited | No |
| trusted | 81-95 | 60/min | 8K | No |
| standard | 51-80 | 30/min | 4K | No |
| minimal | 31-50 | 15/min | 2K | Yes |
| restricted | 11-30 | 5/min | 1K | Yes |
| blocked | 0-10 | denied | denied | N/A |

Every response includes a signed JWS attestation. Framework authors can use the trust tier to throttle tool execution — spend less compute on risky tools, let clean tools run freely.

This is the foundation for a trust gateway: instead of binary accept/deny, graduated throttling based on verified security posture.

You can also embed a trust badge in your README:

```
![Trust Score](https://agentgraph.co/api/v1/public/scan/{owner}/{repo}/badge)
```

## Full Data

The scanner and full results are open source:

- **Scanner**: [github.com/agentgraph-co/agentgraph](https://github.com/agentgraph-co/agentgraph)
- **MCP Server**: [pypi.org/project/agentgraph-trust](https://pypi.org/project/agentgraph-trust/) | [source](https://github.com/agentgraph-co/agentgraph/tree/main/sdk/mcp-server)

---

The agent ecosystem needs trust infrastructure. We are building it at [agentgraph.co](https://agentgraph.co).
