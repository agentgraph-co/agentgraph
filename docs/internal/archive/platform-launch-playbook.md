# AgentGraph Launch Playbook — All Platforms

**Launch:** Tuesday May 12, 2026, 8:00am ET (embargo lifts; litepaper publishes at `agentgraph.co/state-of-agent-security-2026`)
**Last refreshed:** 2026-05-08 (Friday, T-4)

---

## Hacker News (Show HN)

**When to post:** Tuesday May 12, **8-9am ET** (synchronous with embargo lift). Tue 8-9am ET is historically the highest-engagement HN window. Avoid Mondays (crowded), Fridays (low traffic). Tuesday is the launch day; this is the canonical move.

**Title (updated for current scan dataset):** Pick one of:
- **"Show HN: We scanned 5 agent distribution surfaces — only 0.41% of x402 endpoints implement the protocol correctly"** (sharpest number, leads with x402 surprise)
- **"Show HN: State of Agent Security 2026 — 35,689 signed scans across x402 + MCP + OpenClaw + npm + PyPI"** (broadest framing, leads with the corpus)
- **"Show HN: 55% of MCP servers have at least one critical or high-severity finding (8-impl byte-match validated dataset)"** (security-trade angle)

**Recommendation: title #1** — the 0.41% x402 number is the most counterintuitive and HN-loved finding ("everyone says x402 is the agent payment standard, only 107 of 26,302 endpoints actually implement it"). Counterintuitive + concrete + open data = HN catnip.

**Draft body:** `docs/internal/hn-show-hn-draft.md` — needs current-numbers refresh (was written for 231-repo OpenClaw-only era; now reflects 5-surface 35K-scan corpus).

**Strategy:**
- Lead with the data, not the product
- Be ready to answer questions in comments for **2-3 hours after posting** (12pm-3pm ET window blocked off)
- HN loves: open source, security research, concrete data, technical depth, reproducibility
- HN hates: marketing speak, "AI" hype, anything that feels like an ad
- Anchor the reproducibility angle: "every scan is signed, anyone can verify with `node scripts/verify-ctef-byte-match.mjs`"

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

## Recommended Sequence — Launch Week (May 12, 2026)

### Sunday May 10 (T-2)
- [x] Brax / Frequency conversation (Project Liberty) — set, post-call litepaper PDF as follow-up
- [ ] Final litepaper skim by Kenne (post-edits version)
- [ ] Walk through this playbook to confirm Tuesday execution
- [ ] Confirm marketing bot adapters healthy (Bluesky, Dev.to, GH Discussions, HuggingFace)
- [ ] Confirm HN account is logged in / verified working
- [ ] Pre-write HN reply-guy responses for predictable comments (e.g., "why is this just a litepaper not a product launch?", "isn't this just a marketing exercise?")

### Monday May 11 (T-1)
- [ ] Press embargo emails — final any remaining sends not done Friday
- [ ] Confirm `agentgraph.co/state-of-agent-security-2026` landing page is staged + ready to flip live at 8am ET Tuesday
- [ ] Confirm the embargo PDF is rendered, signed, hosted
- [ ] Quiet day — last-minute partner DMs only; don't burn signal

### Tuesday May 12 (LAUNCH DAY) — execution sequence

**8:00am ET — Embargo lifts.**
- [ ] **Flip `agentgraph.co/state-of-agent-security-2026` live** (publish landing page; canonical URL)
- [ ] **Submit HN Show HN** — see title options + body in HN section above; post immediately at 8am ET so the launch lands during peak HN traffic
- [ ] **Post on Bluesky + Twitter/X** — short thread with 2-3 anchor stats (0.41% x402, ~57% MCP+npm+PyPI, 8-impl substrate) + link to landing page
- [ ] **Post in AAIF Discord, LangChain Discord, OpenClaw Discord** — `#showcase` or `#announcements`-style channels only
- [ ] **GH Discussion or repo announcement** on `agentgraph-co/agentgraph`

**8:30am - 11:30am ET — HN reply-guy window.**
- [ ] **Block 3 hours for HN comment engagement** — this is THE most leveraged time-block of launch day. HN comment quality determines whether the post rises or falls within the first ~3 hours.
- [ ] Reply substantively to every comment that's not a flame
- [ ] Have the verifier scripts URL + reproducibility framing ready to drop on any "is this real?" comment
- [ ] Have Erik Newton's #1725 public articulation handy as social proof for any "are partners real?" comment

**11:30am ET — First press check.**
- [ ] Check email — has any embargoed reporter reached out?
- [ ] Check who's tweeted / quote-tweeted the launch (partners: Erik Newton, aeoess, Davide Crapis, ArkForge, Foxbook)
- [ ] If any tier-1 press wants a quote / interview, drop other channels and respond

**12:00pm - 5:00pm ET — Reddit + Dev.to wave.**
- [ ] Post on `r/MachineLearning` — use a discussion-framing title, NOT a launch announcement (r/ML aggressively removes self-promo)
- [ ] Post on `r/cybersecurity` — security-research framing
- [ ] Post on `r/LocalLLaMA` — agent-tool-quality angle
- [ ] Post on `r/AIAgents` if exists / `r/artificial`
- [ ] Bot-auto-post to Dev.to (if marketing bot adapter is wired)
- [ ] Continue HN engagement

**Evening (after 5pm ET):**
- [ ] Bot-auto-post to HuggingFace (if adapter wired)
- [ ] Crypto Twitter / X thread — different angle than morning thread (lead with the OKX APP / Alchemy / x402 framing instead of security)
- [ ] LinkedIn post (Kenne's network)

### Wednesday May 13 (T+1)
- [ ] Continued HN engagement (comments slow but still high-leverage)
- [ ] Reddit comment monitoring across all submitted threads
- [ ] First-day metrics check: HN ranking, agentgraph.co landing page traffic, partner amplification volume
- [ ] Press follow-up emails to any reporter who replied "interested but not today"

### Thursday May 14 (T+2)
- [ ] Continued press follow-ups
- [ ] Bluesky + Twitter post #2 (different stat from launch day)

### Week 2 (May 19-23) — Second-beat moves
- [ ] **CTEF v0.3.2 publish** (substrate-side announcement, separate news cycle)
- [ ] **Frequency partnership announcement** (per Brax Sunday conversation outcome)
- [ ] **ethereum-magicians thread #25098** substantive ERC-8004 engagement
- [ ] **Product Hunt launch** (PH and HN should be 1-2 weeks apart per file rules)
- [ ] Begin Dev.to series (HF / LangChain / CrewAI / etc. per master plan §14)

### Week 3+ (May 26+) — Long tail
- [ ] HuggingFace Spaces/Agents surface scan publication (T+7)
- [ ] LangChain Hub templates scan (T+14)
- [ ] CrewAI marketplace scan (T+21)
- [ ] AutoGen + Microsoft-anchored agents (T+28)
- [ ] Glama / mcp.so / PulseMCP / Smithery extended scan pipeline (T+1 through T+5 per master plan §18f)
- [ ] Anthropic Discord if MCP ban resolved
- [ ] Ongoing reply guy + auto-follow

---

## Launch-day quality gates (before flipping `/state-of-agent-security-2026` live)

Critical pre-flight checks at 7:30-7:55am ET Tuesday:

- [ ] `agentgraph.co/.well-known/jwks.json` returns 200 with `agentgraph-security-v1` kid
- [ ] `agentgraph.co/.well-known/did.json` returns 200 with verificationMethod
- [ ] `agentgraph.co/.well-known/cte-test-vectors.json` returns 200 with v0.3.1 vectors
- [ ] `agentgraph.co/.well-known/interop-harness.json` returns 200 with 8 byte-match impls
- [ ] `agentgraph.co/check` loads without errors
- [ ] `agentgraph.co/scans` loads with current corpus count (35,689+)
- [ ] `agentgraph.co/api/v1/public/scan/agentgraph-co/agentgraph` returns valid JWS
- [ ] No Sentry alerts on `agentgraph-prod` in last 24 hours
- [ ] Login works (use the kenne@agentgraph.co credential check from memory)

If any fail, **do not flip live** — diagnose and fix first. Rolling-launch is fine; broken-launch isn't.
