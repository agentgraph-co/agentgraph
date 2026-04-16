# Show HN Draft — INTERNAL REVIEW ONLY

## Title (under 80 chars)

**Show HN: Is This Agent Safe? Free security checker with scores no platform can revoke**
(78 chars — combines the consumer question with the independence angle)

---

## Body Comment (posted by you immediately after submission)

Anthropic temporarily banned OpenClaw's creator from Claude last week. The ban was reversed within hours, but it highlighted a structural problem: there's no independent way to verify whether an AI agent or tool is safe to use. Even a brief ban disrupted the entire developer ecosystem. Platform trust is revocable. Independent trust verification shouldn't be.

We built a free tool to answer the question: **agentgraph.co/check**

Paste any GitHub URL, package name, or agent name. Get an instant letter grade (A+ through F) with a plain-English safety verdict. No signup, no API key, no paywall.

**What's behind the grade:**

We scanned 231 OpenClaw marketplace skills (2,007 discovered). The results:
- 14,350 total security findings
- 98 critical findings across 20 repos
- 32% scored F (0-20)
- Average score: 57/100
- Top issues: filesystem access (8,239), unsafe exec (5,871), exfiltration patterns (146), hardcoded secrets (58)

The scanner is context-aware — an MCP server accessing the filesystem is doing its job, a regular library doing the same is suspicious. This reduced false positives dramatically.

**Why independent verification matters:**

Every scan result is a cryptographically signed attestation (EdDSA/Ed25519). You don't have to trust us — fetch our JWKS, verify the signature yourself. We're one of 9 independent issuers in a multi-attestation working group, each covering a different trust dimension (code security, behavioral trust, identity, compliance, on-chain audit).

No single platform controls the trust score. No one can revoke it.

**What you can do:**
- Check any tool: **agentgraph.co/check** (or agentgraph.co/check/owner/repo)
- API: `curl agentgraph.co/api/v1/public/scan/owner/repo`
- Add to CI: GitHub Action that comments trust grades on PRs
- MCP server: `pip install agentgraph-trust`
- Framework bridges: `pip install agentgraph-bridge-langchain` (also CrewAI, AutoGen, PydanticAI)

Each finding includes remediation hints. The goal is constructive, not just scores.

Listed on [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers). Open source: github.com/agentgraph-co/agentgraph

---

## Timing
- Post Tuesday April 15, 8-9am ET (5-6am PT)
- NOTE: 5am PT is early for Kenne — consider 9am ET (6am PT) or even 10am ET
- Monitor and respond to comments for 3-4 hours

## Key Comment Responses to Prepare

**"This is just a code scanner"**
→ It's a scanner + enforcement gateway + multi-provider aggregation. The scan is the entry point. The trust gateway lets agent frameworks check trust before executing ANY tool, combining signals from 9 independent providers. One query, multi-dimensional trust.

**"Anthropic can just ban you too"**
→ They already banned us from the MCP GitHub org (we posted too many discussion comments — our mistake). Our scans and attestations are still live. That's the point — the trust data is independently verifiable and can't be revoked by a platform decision.

**"False positives / this would flag legitimate tools"**
→ Context-aware MCP detection. We detect MCP server context (server.json, dependencies) and adjust scoring. A filesystem MCP server gets a pass on filesystem access. A random library doesn't.

**"How is this different from Snyk?"**
→ Snyk finds vulnerabilities. We answer "should I trust this agent?" — combining code security with identity verification, behavioral monitoring, and community trust. Plus the result is a signed attestation, not just a report.

**"Who decides what's trusted?"**
→ Nobody alone. 9 independent providers each cover a different dimension. Our RFC (co-authored with MoltBridge, Verascore, Revettr, RNWY) defines a composable format where any provider can emit signals and any gateway can consume them.

**"What about the GPT Store / ChatGPT plugins?"**
→ Great question. Today we cover GitHub-hosted tools and MCP servers. The /check page accepts names and searches our database. As more tools get scanned, coverage grows. The browser extension (coming soon) will show trust grades directly on GitHub, ClawHub, and directory pages.

---

## How to Post on HN — Step by Step

### If you don't have an account yet:
1. Go to https://news.ycombinator.com
2. Click "login" in the top right
3. Click "create account"
4. Username: `kenneives` or `agentgraph` (whatever is available)
5. Enter email and password
6. **Important:** New accounts CAN post Show HN immediately. No karma requirement.

### Posting the Show HN:

1. Go to https://news.ycombinator.com/submit
2. **Title:** `Show HN: Is This Agent Safe? Free security checker with scores no platform can revoke`
3. **URL:** `https://agentgraph.co/check`
4. **Text:** Leave BLANK. The URL is the submission. You'll add the detailed comment separately.
5. Click "submit"

### Immediately after submitting:

1. Your post will appear. Click into it.
2. In the comment box, paste the **Body Comment** from above (the section starting with "Anthropic temporarily banned...")
3. Submit the comment.

### Post-submission (next 2-3 hours):

1. Stay on the page and refresh every 10-15 minutes
2. Reply to every comment — be helpful, technical, and honest
3. Don't be defensive — HN rewards humility
4. If someone points out a flaw, acknowledge it: "Good catch, fixing that"
5. Upvote thoughtful comments (even critical ones)
6. **Do NOT ask friends to upvote** — HN detects vote rings and will kill the post

### Timing:
- Post at **8:30am PT / 11:30am ET** on Tuesday April 15
- 11:30am ET is still a good window — lunchtime East Coast, morning West Coast
- Monitor until at least noon PT

### What success looks like:
- 10+ upvotes = made the front page briefly
- 50+ upvotes = solid Show HN
- 100+ = great launch
- Comments > upvotes = high engagement (good sign)

---

## COPY-PASTE VERSION (plain text, no markdown — HN doesn't support it)

```
Anthropic temporarily banned OpenClaw's creator from Claude last week. The ban was reversed within hours, but it highlighted a structural problem: there's no independent way to verify whether an AI agent or tool is safe to use. Even a brief ban disrupted the entire developer ecosystem. Platform trust is revocable. Independent trust verification shouldn't be.

We built a free tool to answer that question. Paste any GitHub URL, package name, or agent name. Get an instant letter grade (A+ through F) with a plain-English safety verdict. No signup, no API key, no paywall.

What's behind the grade:

We scanned 231 OpenClaw marketplace skills (2,007 discovered). The results: 14,350 total security findings. 98 critical findings across 20 repos. 32% scored F (0-20). Average score: 57/100. Top issues: filesystem access (8,239), unsafe exec (5,871), exfiltration patterns (146), hardcoded secrets (58).

The scanner is context-aware — an MCP server accessing the filesystem is doing its job, a regular library doing the same is suspicious. This reduced false positives dramatically.

Why independent verification matters:

Every scan result is a cryptographically signed attestation (EdDSA/Ed25519). You don't have to trust us — fetch our JWKS and verify the signature yourself. We're one of 9 independent issuers in a multi-attestation working group, each covering a different trust dimension (code security, behavioral trust, identity, compliance, on-chain audit).

No single platform controls the trust score. No one can revoke it.

What you can do: check any tool on our homepage, use the public API, add our GitHub Action to CI for trust grades on PRs, or pip install agentgraph-trust for the MCP server. We also have framework bridges for LangChain, CrewAI, AutoGen, and PydanticAI.

Each finding includes remediation hints. The goal is constructive, not just scores. Listed on awesome-mcp-servers. Open source on GitHub under agentgraph-co.
```

## NO-URL VERSION (if HN blocks URLs — use this one)

```
Anthropic temporarily banned OpenClaw's creator from Claude last week. The ban was reversed within hours, but it highlighted a structural problem: there's no independent way to verify whether an AI agent or tool is safe to use. Platform trust is revocable. Independent trust verification shouldn't be.

We built a free tool to answer that question. Paste any GitHub repo URL, package name, or agent name and get an instant letter grade (A+ through F) with a plain-English safety verdict. No signup needed.

What we found scanning 231 OpenClaw marketplace skills: 14,350 total security findings. 98 critical across 20 repos. 32% scored F. Average score 57 out of 100. Top issues: filesystem access (8,239 findings), unsafe exec (5,871), exfiltration patterns (146), hardcoded secrets (58).

The scanner is context-aware — an MCP server accessing the filesystem is doing its job. A regular library doing the same is suspicious. This reduced false positives dramatically.

Every scan result is a cryptographically signed attestation (EdDSA/Ed25519). You don't have to trust us — verify the signature yourself. We're one of 9 independent issuers in a working group covering code security, behavioral trust, identity, compliance, and on-chain audit. No single platform controls the score.

We have pip-installable packages for MCP, LangChain, CrewAI, AutoGen, and PydanticAI. A GitHub Action that comments trust grades on PRs. And the checker on our homepage works for any public repo.

Each finding includes remediation hints. The goal is constructive, not just scores. Listed on awesome-mcp-servers. Open source under agentgraph-co on GitHub.
```
