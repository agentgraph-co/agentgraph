# AgentGraph Launch Playbook — All Platforms

## Hacker News (Show HN)

**When to post:** Tuesday or Wednesday, 8-9am ET (12-1pm UTC). These are historically the highest-engagement windows. Avoid Mondays (crowded) and Fridays (low traffic). **Next good window: Tuesday April 15 or Wednesday April 16.**

**Draft:** `docs/internal/hn-show-hn-draft.md` (updated with 231-repo scan data)

**Strategy:**
- Title: "Show HN: We scanned 231 OpenClaw skills for security — 32% scored F"
- Lead with the data, not the product
- Be ready to answer questions in comments for 2-3 hours after posting
- HN loves: open source, security research, concrete data, technical depth
- HN hates: marketing speak, "AI" hype, anything that feels like an ad

**Account:** Use your existing HN account (if you have one with karma). Fresh accounts get flagged.

---

## Reddit

**Subreddits (in priority order):**

| Subreddit | Subscribers | Post Type | Draft Needed |
|-----------|------------|-----------|-------------|
| r/MachineLearning | 3.2M | Security research angle | Yes |
| r/LocalLLaMA | 800K+ | "We scanned 231 OpenClaw skills" data post | Yes |
| r/artificial | 500K+ | Discussion: "Should AI agents have trust scores?" | Yes |
| r/cybersecurity | 600K+ | Security findings report | Yes |
| r/selfhosted | 400K+ | MCP server as self-hosted tool | Yes |
| r/Python | 1.4M | PyPI package announcement | Yes |

**Account:** Check your existing account first. If it has zero history, posting will get auto-removed by most subreddits (they require minimum karma/age). Options:
1. Use existing account — start by commenting on relevant threads for a week, THEN post
2. Create new account — same problem, need karma first
3. Best option: use existing account, spend 2-3 days making genuine comments in these subreddits, then post

**Rules:**
- ONE post per subreddit per WEEK
- Space posts 2-3 days apart
- 10:1 rule: 10 helpful comments for every self-promotional post
- r/MachineLearning and r/cybersecurity are the strictest

**Drafts needed:** Yes, one per subreddit, tailored to each audience

---

## Discord Servers

| Server | Focus | Strategy |
|--------|-------|----------|
| **AAIF Discord** | AI agent interop | Join and participate in trust/security channels. Share scan data when relevant. |
| **LangChain Discord** | LangChain framework | Share agentgraph-pydantic package in #showcase |
| **CrewAI Discord** | CrewAI framework | Mention trust gateway integration |
| **MCP Discord** | MCP protocol | **BLOCKED** — wait for ban appeal |
| **OpenClaw Discord** | OpenClaw community | Share security scan results — they care about this |
| **Anthropic Discord** | Claude/Anthropic | Share MCP server in #mcp-servers |

**Strategy:** Don't blast all at once. Join 1-2 per week, participate genuinely for a few days, then share when relevant.

---

## Slack Communities

| Community | How to Join | Strategy |
|-----------|------------|----------|
| **MLOps Community** | mlops.community | Share scan data as "security for ML pipelines" |
| **dbt Slack** | community.getdbt.com | Not relevant |
| **AI Engineer** | aie.foundation | Share trust infrastructure angle |

---

## Bluesky

**Status:** Active, reply guy posting. Continue with:
- 1 promotional post per day max
- Quote tweets of relevant AI security discussions
- Auto-follow is running

---

## Twitter/X

**Status:** Reply guy working (quote tweets). Continue with:
- Quote tweets of AI agent discussions
- 1 original post per day max on security findings

---

## Dev.to

**Status:** Article published. Update with:
- New scan data (231 repos → 500+ when batch completes)
- PyPI package announcements
- Trust gateway walkthrough article

---

## Product Hunt

**When:** After HN. PH and HN should be spaced 1-2 weeks apart.
**Prep needed:** Hero image, tagline, 3-5 screenshots, maker comment

---

## GitHub

**Status:** awesome-mcp-servers PR pending (waiting Glama re-eval). Also:
- awesome-security-tools lists
- awesome-python lists (for PyPI packages)
- awesome-ai-agents lists

---

## Direct Outreach (Pull-Based Only)

| Target | Channel | Status |
|--------|---------|--------|
| RNWY | Telegram @rnwycom | You reached out |
| MoltBridge/Justin | A2A #1720 | Active, building bilateral |
| AgentID/Harold | A2A #1672 | Fixture repo |
| Anthropic | AAIF/MCP | Blocked by ban |

---

## Recommended Sequence

**Week 1 (this week):**
- [x] Bluesky announcement (done)
- [x] Twitter reply guy (running)
- [x] Partner replies (done)
- [ ] Join AAIF Discord + OpenClaw Discord
- [ ] Start Reddit comment engagement (no posts yet, just comments)

**Week 2 (April 14-18):**
- [ ] HN Show HN (Tuesday April 15, 8am ET)
- [ ] Reddit post on r/LocalLLaMA (Wednesday April 16)
- [ ] Dev.to article update
- [ ] Open RFC as A2A discussion
- [ ] LangChain Discord #showcase

**Week 3 (April 21-25):**
- [ ] Reddit post on r/cybersecurity
- [ ] Reddit post on r/MachineLearning
- [ ] Product Hunt launch
- [ ] CrewAI Discord

**Week 4+:**
- Additional Reddit subreddits
- Anthropic Discord (if MCP ban resolved)
- Ongoing reply guy + auto-follow
