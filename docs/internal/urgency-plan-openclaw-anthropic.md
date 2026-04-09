# Urgency Plan: OpenClaw + Anthropic Awareness — INTERNAL REVIEW ONLY

## Goal
Get AgentGraph on Anthropic's radar as the trust infrastructure layer for MCP.

## Why Now
- AAIF (Agentic AI Foundation) is actively reviewing trust-related SEPs
- SEP-1913 (Trust Annotations) has a Microsoft sponsor but NO entity-level trust
- Agent Guard submitted as AAIF project — direct overlap, we need to be visible
- MCP spec explicitly punts on trust scoring — we fill that gap
- 9 verified issuers in the multi-attestation WG validates the approach

## Anthropic Path (3 tracks)

### Track 1: AAIF SEP Process (highest impact, 2-4 weeks)
1. Join AAIF Discord (discord.gg/9zTwngHAMy)
2. Comment on SEP-1913 PR #1913 — position entity-level trust
3. Submit our own SEP for entity-level trust scoring
4. Target sponsors: David Soria Parra (Anthropic, TC chair) or Sambhav (Bloomberg)
5. Reference implementation: our MCP server + gateway proxy

### Track 2: MCP Registry + Community (ongoing)
1. Already published on official MCP Registry ✓
2. Already on mcp.so ✓
3. agentgraph-trust on PyPI ✓
4. Pydantic AI community asked for package (share on Slack)
5. Scan popular MCP repos → share results constructively

### Track 3: Direct Dev Relations (opportunistic)
1. Anthropic Dev Relations team — reach out via Twitter/email
2. Reference our A2A Discussion #1720 (active multi-party thread)
3. Reference the OATR registration (9th verified issuer)
4. Offer to present at Anthropic's MCP community call (if one exists)

## OpenClaw Path

### Community Engagement
- OpenClaw Discord (if public) — share scanner as a tool
- GitHub Discussions on openclaw/openclaw — security-focused contribution
- ClawHub security research — our scan data shows real issues

### What NOT to Do
- Don't publish confrontational "OpenClaw is insecure" content
- Don't push unsolicited issues on repos (learned this lesson)
- Don't name-and-shame specific vulnerable skills

### What TO Do
- Publish constructive security guide for OpenClaw skill authors
- Offer the scanner as a CI tool for skill validation
- Reference real data (3,924 findings across 78 repos, 1,781 unsafe exec patterns, 26% score F) without blaming
- Position as "here's how to make your skills safer"

## Timeline
- This week: Join AAIF Discord, comment on SEP-1913
- Next week: Submit entity-level trust SEP, share on Pydantic Slack
- Week 3: HN Show HN post, Reddit strategy
- Week 4: AAIF working group engagement (if accepted)

## Success Metrics
- SEP gets a sponsor within 2 weeks
- Anthropic dev relations engagement (any response)
- 10+ repos scanned via public API per day
- 3+ bots imported on AgentGraph
