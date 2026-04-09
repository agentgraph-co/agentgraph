# Reddit Strategy Draft — INTERNAL REVIEW ONLY

## Target Subreddits (in order of priority)

### 1. r/ClaudeAI (~200K members)
**Framing:** "Built an MCP tool that scans any GitHub repo for security issues"
**Why:** Direct MCP users, likely to try `pip install agentgraph-trust`
**Self-promo rules:** Check wiki. Usually OK if useful tool, not spammy.
**Post type:** Text post with curl example

### 2. r/LocalLLaMA (~500K members)  
**Framing:** "We scanned 78 of the top 100 OpenClaw skills — 14,350 security findings, 32% scored F"
**Why:** Technical audience interested in agent infrastructure
**Self-promo rules:** Strict. Must be genuinely useful, not marketing.
**Post type:** Results/data post, link to API in comments not title

### 3. r/MachineLearning (~3M members)
**Framing:** "Context-aware security scanning for AI agent tools [P]"
**Why:** Largest technical AI audience
**Self-promo rules:** [P] tag for projects. Must be substantive.
**Post type:** Project post with technical details

### 4. r/artificial (~500K members)
**Framing:** "The MCP ecosystem has a trust problem — here's data"
**Why:** Broader AI audience, more casual
**Post type:** Discussion post referencing our data

### 5. r/LangChain (~50K members)
**Framing:** "We built a trust gateway for LangChain tool execution"
**Why:** Direct framework users
**Post type:** Tool announcement

## Timing
- Post AFTER HN (next day or same day if HN doesn't take off)
- Different framing per subreddit (not cross-posting same text)
- Space posts 2-3 hours apart to avoid pattern detection
- Engage in comments — don't just drop and leave

## Key Rules
- NO "we scanned your framework and it sucks" framing
- YES "here's a tool that helps you check your MCP servers"
- Lead with the value (free API, no auth needed)
- Include the curl one-liner in every post
- Don't mention competitors by name (AgentSeal, Snyk)
