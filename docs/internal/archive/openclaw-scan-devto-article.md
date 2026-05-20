---
title: "We Scanned 231 OpenClaw Skills for Security Vulnerabilities — Here's What We Found"
published: true
canonical_url: https://agentgraph.co/blog/openclaw-scan
description: "14,350 findings across 231 OpenClaw skill repos. 32% scored F. 98 critical findings in 20 repos. Here's the data, free PyPI packages, and a trust gateway for enforcement."
tags: security, ai, agents, opensource
cover_image:
---

AI agents are running third-party code on your machine. Last week, [Anthropic announced extra charges for OpenClaw support in Claude Code](https://techcrunch.com/2026/04/04/anthropic-says-claude-code-subscribers-will-need-to-pay-extra-for-openclaw-support/), drawing fresh attention to the ecosystem. We wanted to answer a straightforward question: how safe are the most popular OpenClaw skills?

We first published results from 25 repos. We have now expanded the scan to 231 repositories out of 2,007 discovered — nearly a 10x increase in coverage — and the picture has gotten worse.

## Why Independent Trust Verification Matters Now

Anthropic just temporarily banned OpenClaw's creator from accessing Claude ([TechCrunch, April 10](https://techcrunch.com/2026/04/10/anthropic-temporarily-banned-openclaws-creator-from-accessing-claude/)). Whether you agree with their decision or not, it highlights a structural gap: platform trust is revocable. There's no independent way to verify whether an AI agent or tool is safe to use.

That's why we built **[agentgraph.co/check](https://agentgraph.co/check)** — a free, instant safety checker for any AI agent, MCP server, or skill. Paste a URL, get a letter grade. The result is a cryptographically signed attestation that you can verify yourself. No platform controls the score.

## Methodology

We used AgentGraph's [open-source security scanner](https://github.com/agentgraph-co/agentgraph) to analyze 231 OpenClaw skill repositories from GitHub (out of 2,007 discovered). The scanner inspects source code for:

- **Hardcoded secrets** (API keys, tokens, passwords in source)
- **Unsafe execution** (subprocess calls, eval/exec, shell=True)
- **File system access** (reads/writes outside expected boundaries)
- **Data exfiltration patterns** (outbound network calls to unexpected destinations)
- **Code obfuscation** (base64-encoded payloads, dynamic imports)

It also detects positive signals: authentication checks, input validation, rate limiting, and CORS configuration. Each repo receives a trust score from 0 to 100.

## Results Summary

All 231 repositories scanned successfully. The aggregate numbers:

| Metric | Value |
|--------|-------|
| Repos discovered | 2,007 |
| Repos scanned | 231 |
| Total findings | 14,350 |
| Critical | 98 |
| High | 6,192 |
| Medium | 8,045 |
| Repos with critical findings | 20 (9%) |
| Average trust score | 57.0 / 100 (Grade C) |
| Repos scoring F (0-20) | 74 (32%) |

Findings by category: file system access accounted for 8,239, unsafe execution patterns for 5,871, data exfiltration patterns for 146, hardcoded secrets for 58, dependency vulnerabilities for 29, and code obfuscation for 7.

## Score Distribution

| Score Range | Grade | Repos | Percentage |
|-------------|-------|-------|------------|
| 81 - 100 | A / A+ | 118 | 51% |
| 61 - 80 | B / B+ | — | — |
| 41 - 60 | C | — | — |
| 21 - 40 | D | — | — |
| 0 - 20 | F | 74 | 32% |

The distribution remains bimodal. More than half of repos score A or above, but over a quarter score F. Repos tend to be either clean or deeply problematic, with almost nothing in the middle. There is no gentle gradient between "secure" and "insecure" — it is one or the other.

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

The finding categories tell the story: 5,871 unsafe execution patterns means eval, exec, subprocess, and shell=True calls scattered across these codebases. 8,239 file system access findings means code reaching into the filesystem in ways that may not be bounded. 146 data exfiltration patterns and 58 hardcoded secrets round out the picture.

Anthropic's decision to gate OpenClaw behind additional pricing starts to make more sense in this context. The cost is not just computational — it is risk.

## New: PyPI Packages and Trust Gateway

Since the initial scan, we have shipped three PyPI packages:

- **[agentgraph-trust](https://pypi.org/project/agentgraph-trust/)** (v0.3.1) — the MCP server for scanning tools directly from Claude Code or any MCP-compatible client
- **[agentgraph-agt](https://pypi.org/project/agentgraph-agt/)** — the AgentGraph Trust CLI for CI pipelines and local use
- **[open-agent-trust](https://pypi.org/project/open-agent-trust/)** — a lightweight library for embedding trust checks into any Python agent framework

We have also built a **trust gateway** — an enforcement layer that sits between your agent runtime and third-party tools. Instead of scanning after the fact, the gateway intercepts tool invocations at runtime and makes enforcement decisions based on the tool's trust score: allow, throttle, require user confirmation, or block entirely. The trust tiers (detailed below) drive these decisions automatically.

The gateway turns scan results into policy. A tool scoring 0/100 does not just get a warning — it gets denied execution unless the user explicitly overrides.

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
- **MCP Server**: [pypi.org/project/agentgraph-trust](https://pypi.org/project/agentgraph-trust/) (v0.3.1) | [source](https://github.com/agentgraph-co/agentgraph/tree/main/sdk/mcp-server)
- **CLI**: [pypi.org/project/agentgraph-agt](https://pypi.org/project/agentgraph-agt/)
- **Library**: [pypi.org/project/open-agent-trust](https://pypi.org/project/open-agent-trust/)

## Try It Now

**[agentgraph.co/check](https://agentgraph.co/check)** — Paste any GitHub repo URL, MCP server name, or agent package and get an instant letter grade. No signup, no API key, no cost. The result is a signed attestation you can independently verify.

**7 PyPI packages** available now:

| Package | Purpose |
|---------|---------|
| [agentgraph-trust](https://pypi.org/project/agentgraph-trust/) | MCP server — scan tools from Claude Code or any MCP client |
| [agentgraph-agt](https://pypi.org/project/agentgraph-agt/) | CLI for CI pipelines and local scanning |
| [open-agent-trust](https://pypi.org/project/open-agent-trust/) | Lightweight library for embedding trust checks in any Python agent |
| [agentgraph-scanner](https://pypi.org/project/agentgraph-scanner/) | Core scanning engine |
| [agentgraph-attestation](https://pypi.org/project/agentgraph-attestation/) | Cryptographic attestation signing and verification |
| [agentgraph-gateway](https://pypi.org/project/agentgraph-gateway/) | Trust gateway enforcement layer |
| [agentgraph-badges](https://pypi.org/project/agentgraph-badges/) | Trust badge generation for READMEs |

**[GitHub Action](https://github.com/agentgraph-co/agentgraph-trust-action)** — Add trust scanning to any CI pipeline. Runs on every PR, blocks merges that introduce tools below your trust threshold. Drop it into your workflow in two lines:

```yaml
- uses: agentgraph-co/agentgraph-trust-action@v1
  with:
    fail-below: 50
```

---

The agent ecosystem needs trust infrastructure. We are building it at [agentgraph.co](https://agentgraph.co).
