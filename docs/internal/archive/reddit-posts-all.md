# Reddit Post Drafts — AgentGraph Trust Scanner

Created: 2026-04-09

---

## 1. r/LocalLLaMA

**Title:** We scanned 231 OpenClaw marketplace skills for security vulnerabilities. Here's what we found.

**Body:**

I've been building an open-source security scanner for AI agent tools and just finished a scan of 231 skills from the OpenClaw marketplace (out of 2,007 discovered). Sharing the raw data because I think this community will find it interesting.

**The numbers:**

- 14,350 total security findings across 231 packages
- 98 critical findings across 20 repos
- Average trust score: 57.0/100
- 32% of packages scored F (0-20 out of 100)
- 51% scored A/A+ — so the distribution is bimodal, not a normal curve

**Top finding categories:**

| Category | Count |
|----------|-------|
| Filesystem access | 8,239 |
| Unsafe exec (shell/eval) | 5,871 |
| Data exfiltration patterns | 146 |
| Hardcoded secrets | 58 |
| Dependency vulnerabilities | 29 |
| Obfuscation | 7 |

The filesystem access number is high partly because many tools legitimately need file access. The concerning part is the 5,871 unsafe exec findings — tools using `subprocess.Popen(shell=True)`, `eval()`, or equivalent patterns with user-controlled input.

**Methodology:**

Static analysis across multiple dimensions: dependency vulnerability scanning, code pattern matching for dangerous function calls, secret detection, and network exfiltration pattern analysis. Each finding is categorized by severity and type, then aggregated into a 0-100 trust score.

This is not a fuzzer or dynamic analysis tool — it's pattern-based static scanning. It catches the low-hanging fruit but won't find logic bugs. Think of it as a first-pass filter, not a comprehensive audit.

**The tool is open source and runs locally:**

- `pip install agentgraph-trust` (MCP server, works with Claude Desktop and other MCP clients)
- Public API: `GET https://agentgraph.co/api/v1/public/scan/{owner}/{repo}`
- Source: github.com/agentgraph-co/agentgraph

Everything runs locally when using the MCP server — no data sent anywhere unless you use the public API.

We're expanding to cover all 2,007 discovered skills. The bimodal distribution is interesting — it suggests the ecosystem has a core of well-maintained tools and a long tail of potentially risky ones.

Disclosure: I built this. Happy to answer questions about methodology or findings.

**What patterns are you seeing in the tools you run locally? Anyone else doing systematic security review of agent tool ecosystems?**

---

## 2. r/MachineLearning

**Title:** Security analysis of the AI agent tool ecosystem: 14,350 vulnerabilities across 231 packages

**Body:**

We conducted a systematic security analysis of 231 tool packages from the OpenClaw marketplace (out of 2,007 discovered) — the largest open-source AI agent tool ecosystem (190K+ GitHub stars, 512 known CVEs). Sharing findings and methodology.

**Dataset:** 231 OpenClaw marketplace skills (2,007 discovered, expanding coverage)

**Key findings:**

- 14,350 security findings total
- 98 critical-severity findings concentrated in 20 repos
- Trust score distribution is bimodal: 32% scored F (0-20), 51% scored A/A+ (81-100)
- Mean trust score: 57.0/100, but the bimodal distribution makes the mean misleading

**Finding taxonomy:**

- Filesystem access without sandboxing: 8,239 (57.4%)
- Unsafe code execution (eval/exec/shell): 5,871 (40.9%)
- Data exfiltration patterns: 146 (1.0%)
- Hardcoded credentials: 58 (0.4%)
- Dependency vulnerabilities: 29 (0.2%)
- Obfuscation: 7 (0.05%)

**Methodology:**

Multi-pass static analysis pipeline:
1. Dependency graph construction and known-vulnerability matching (CVE databases)
2. AST-level pattern detection for dangerous function calls (eval, exec, subprocess with shell=True, dynamic imports)
3. Network call analysis for data exfiltration patterns (outbound HTTP with local file reads)
4. Secret detection (entropy analysis + regex patterns for API keys, tokens, passwords)
5. Composite scoring: weighted aggregation normalized to 0-100

Limitations: This is static analysis only. No dynamic/runtime analysis, no fuzzing, no symbolic execution. False positive rate varies by category — filesystem access has the highest FP rate since many tools legitimately need file I/O.

**The bimodal distribution is the most interesting result.** It suggests the ecosystem self-segregates into "production-quality" tools maintained by experienced developers and a long tail of tools that were likely published without security review. This mirrors findings in npm and PyPI ecosystem studies.

The scanner and scoring system are open source: github.com/agentgraph-co/agentgraph. The public API endpoint is available for programmatic access.

Disclosure: I'm the creator of this tool.

**Has anyone seen similar bimodal security distributions in other package ecosystems? Interested in whether this pattern is unique to AI agent tools or a general property of young ecosystems.**

---

## 3. r/cybersecurity

**Title:** Automated security scanning of AI agent marketplaces reveals systemic issues — 14,350 findings across 231 tools

**Body:**

AI agent tool marketplaces are growing fast, but security review hasn't kept up. I built an automated scanner and pointed it at the OpenClaw marketplace (the largest open-source agent tool ecosystem). Here's what the data shows.

**Context:** OpenClaw has 190K+ GitHub stars and already has 512 known CVEs including CVE-2026-25253 (CVSS 8.8). Their skills marketplace lets anyone publish tools that agents execute with the user's permissions. There is no mandatory security review for published skills.

**Scan results (231 skills out of 2,007 discovered):**

- 14,350 total findings
- 98 critical findings in 20 repos
- 5,871 unsafe code execution patterns (eval, exec, subprocess with shell=True)
- 8,239 unsandboxed filesystem access instances
- 146 data exfiltration patterns (outbound HTTP paired with local file reads)
- 58 hardcoded secrets

**The threat model:**

When you install an OpenClaw skill, it runs with your agent's permissions. If the agent has filesystem access, the skill has filesystem access. If the agent can make HTTP calls, the skill can exfiltrate data. There's no permission scoping or sandboxing at the marketplace level.

The 146 exfiltration patterns are the most concerning. These are cases where a tool reads local files and makes outbound HTTP requests in the same execution path. Some are legitimate (e.g., uploading a file to an API the user requested), but the pattern is indistinguishable from data theft without runtime context.

**What the data suggests:**

- 32% of scanned tools scored F (0-20 trust score) — these have multiple critical or high-severity findings
- The ecosystem has no gate-keeping equivalent to app store review
- Supply chain attacks via agent tool marketplaces are a real and underexplored attack surface

**The scanner:**

Open source, runs locally. Available as an MCP server (`pip install agentgraph-trust`) or via public API (`GET https://agentgraph.co/api/v1/public/scan/{owner}/{repo}`). Static analysis only — AST pattern matching, dependency scanning, secret detection, and exfiltration pattern analysis.

Source: github.com/agentgraph-co/agentgraph

Disclosure: I built this tool.

**Are any of you seeing agent tool supply chain attacks in the wild yet? Curious whether this is still theoretical or if incident response teams are already dealing with it.**

---

## 4. r/artificial

**Title:** Should AI agents have verifiable trust scores? We scanned the OpenClaw marketplace and the results are concerning.

**Body:**

There's a lot of discussion about AI safety at the model level — alignment, guardrails, RLHF. But there's a layer below that getting almost no attention: the tools and skills that agents use.

When an AI agent installs a "skill" from a marketplace, it's essentially running third-party code with whatever permissions the agent has. There's no verification, no security review, no trust score. You're just... trusting that the skill author didn't include anything malicious.

I built an open-source scanner and tested this assumption against 231 skills from the OpenClaw marketplace (out of 2,007 discovered) — the biggest open-source agent tool ecosystem.

**What we found:**

- 14,350 security findings
- 5,871 instances of unsafe code execution (eval, exec, shell commands)
- 146 data exfiltration patterns
- 32% of tools scored F on a 0-100 trust scale
- 98 critical findings across 20 repos

The distribution was bimodal — most tools are either quite good (51% scored A/A+) or quite bad (32% scored F). There's very little middle ground.

**The bigger question:**

Right now, when you use an AI agent, you have no way to verify:
- Whether the tools it's using have been security-reviewed
- Whether the agent's behavior has changed since you last used it
- Whether other users have flagged issues
- What the agent's track record looks like

This is roughly where the web was before SSL certificates and package managers were before checksum verification. The infrastructure for trust doesn't exist yet.

I think agents (and agent tools) need verifiable, auditable trust scores — computed from actual code analysis, not self-reported claims. That's what I'm building with AgentGraph (open source: github.com/agentgraph-co/agentgraph).

The scanner is available as a local MCP server: `pip install agentgraph-trust`

Disclosure: I'm the creator.

**Do you think trust scores for AI agents and tools are necessary? Or will the market self-correct as the ecosystem matures?**

---

## 5. r/Python

**Title:** agentgraph-trust: MCP server for security scanning AI agent tools [pip install agentgraph-trust]

**Body:**

I built a Python package that scans AI agent tools (MCP servers, OpenClaw skills, LangChain tools) for security vulnerabilities and generates trust scores.

**Install:**

```bash
pip install agentgraph-trust
```

**What it does:**

- Static analysis of Python/JS/TS packages for security issues
- Scans for: unsafe exec/eval, unsandboxed file access, data exfiltration patterns, hardcoded secrets, dependency vulnerabilities
- Generates a 0-100 trust score with categorized findings
- Works as an MCP server (compatible with Claude Desktop, Cursor, etc.) or standalone

**Usage as MCP server:**

Add to your MCP client config:

```json
{
  "mcpServers": {
    "agentgraph-trust": {
      "command": "agentgraph-trust",
      "args": ["--stdio"]
    }
  }
}
```

Then ask your AI assistant to "scan {owner}/{repo} for security issues" and it will use the tool automatically.

**Public API (no install needed):**

```python
import httpx

resp = httpx.get("https://agentgraph.co/api/v1/public/scan/owner/repo")
data = resp.json()
print(f"Trust score: {data['trust_score']}/100")
print(f"Findings: {data['total_findings']}")
```

**What I found scanning 231 OpenClaw marketplace skills (out of 2,007 discovered):**

- 14,350 findings total
- Top categories: filesystem access (8,239), unsafe exec (5,871), exfiltration (146), hardcoded secrets (58)
- Average trust score: 57.0/100
- Bimodal distribution: 51% scored A/A+, but 32% scored F

**Tech stack:** Python, AST-based analysis, runs entirely locally (no data sent anywhere unless you use the public API endpoint). Open source: github.com/agentgraph-co/agentgraph

Currently expanding the scan to cover all 2,007 discovered packages. Looking for contributors, especially anyone with experience in:
- Static analysis tooling
- JavaScript/TypeScript AST parsing
- Security vulnerability taxonomies

Disclosure: I'm the author.

**What other security checks would you want to see in a tool like this? Anything specific to the AI agent tool ecosystem that traditional SAST tools miss?**

---

## 6. r/selfhosted

**Title:** Open-source MCP server for checking AI tool security before you install them — runs entirely local

**Body:**

If you're running AI agents locally (Claude Desktop, Cursor, local LLM setups with MCP), you're probably installing MCP servers and other tools from GitHub without much review. I built a tool that lets you scan them first.

**What it is:**

A local MCP server that performs security analysis on AI agent tools. You point it at a GitHub repo and it tells you what it found — unsafe code execution, file access patterns, potential data exfiltration, hardcoded secrets, dependency vulnerabilities.

**Install:**

```bash
pip install agentgraph-trust
```

Add to your MCP config and you can ask your assistant "scan this repo before I install it."

**Privacy:**

- Runs entirely on your machine
- No telemetry, no phoning home
- The only network call is cloning the repo you ask it to scan
- There IS a public API (`agentgraph.co/api/v1/public/scan/...`) if you prefer not to run locally, but the local MCP server is fully standalone

**Why I built it:**

I scanned 231 tools from the OpenClaw marketplace (out of 2,007 discovered) and found 14,350 security issues including 5,871 unsafe exec patterns and 146 data exfiltration patterns. 32% of the tools scored F on a 0-100 trust scale. The AI agent tool ecosystem has no equivalent of app store review — anyone can publish anything.

If you self-host your AI stack, you're already making good decisions about control and privacy. This just adds a security check to your workflow before you give a random GitHub repo access to your filesystem.

**What it checks:**

- eval/exec/subprocess with shell=True
- Unsandboxed filesystem read/write
- Outbound HTTP paired with local file reads (exfiltration pattern)
- Hardcoded API keys and secrets
- Known CVEs in dependencies

Open source: github.com/agentgraph-co/agentgraph

Disclosure: I'm the creator.

**How are you vetting the MCP servers and AI tools you install? Manual code review, or just trusting the repo stars?**
