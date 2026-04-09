# Marketing Bot Rollout — Status & Next Steps

**Last updated:** 2026-03-17

---

## What's Done

### Backend (fully implemented, deployed to prod)
- **13 platform adapters** — Twitter, Reddit, Bluesky, Discord, LinkedIn, Telegram, Dev.to, Hashnode, GitHub Discussions, HuggingFace, Moltbook Scout, Hacker News, Product Hunt
- **LLM routing** — 5 tiers: Template (free) → Ollama/Qwen 3.5 9B (free) → Haiku ($0.002/post) → Sonnet ($0.50/post) → Opus (high-stakes)
- **Content engine** — proactive (scheduled), reactive (keyword monitoring), data-driven (DB stats)
- **Per-platform tone profiles** — different voice for Twitter vs Reddit vs HN vs LinkedIn etc.
- **Topic rotation** — 5 categories with 48hr cooldown per platform
- **Budget guardrails** — daily ($1) and monthly ($20) caps in Redis, falls back to templates when exceeded
- **Human-in-the-loop** — HN and Product Hunt drafts go to review queue, not auto-posted
- **Draft queue** — approve, reject, or edit+approve from admin UI
- **UTM attribution** — every link gets `?utm_source=agentgraph_bot&utm_medium={platform}&utm_campaign={topic}`
- **Marketing dashboard API** — posts by platform, engagement, cost breakdown, pending drafts
- **Weekly digest** — auto-generated markdown summary of marketing performance
- **DB tables** — `marketing_campaigns` + `marketing_posts` (migration s10, applied to all envs)
- **MarketingBot entity** — registered as 7th official bot with DID
- **Scheduler** — Job 7 in scheduler, runs every 30min (checks `MARKETING_ENABLED` flag)

### Frontend (deployed to prod)
- **Marketing tab** in Admin dashboard — stats cards, platform adapter health, cost breakdown, draft management, recent posts table
- **Apple touch icon** — iOS Messages now shows AgentGraph logo in link previews

---

## What's Left

### 1. Platform Account Setup (you need to do this manually)

These are accounts YOU create — the bot posts through them.

| Priority | Platform | What to Do | Free? | Notes |
|----------|----------|-----------|-------|-------|
| **1** | **Bluesky** | Create `@agentgraph.bsky.social` at bsky.app | Yes | Easiest to start. AT Protocol, no API approval needed. Just username + app password. |
| **2** | **Reddit** | Create u/AgentGraphBot, then create an app at reddit.com/prefs/apps | Yes | Choose "script" type app. You get client_id + client_secret. Reddit is harsh on bots — must disclose, add value, no spam. |
| **3** | **Dev.to** | Create account at dev.to, get API key from Settings → Extensions | Yes | For blog posts. Good SEO. Weekly cadence. |
| **4** | **Twitter/X** | Apply for developer account at developer.twitter.com | Free tier: 1,500 tweets/mo | API v2 free tier may be enough. Approval can take days. Need OAuth 1.0a keys. |
| **5** | **Discord** | Create bot at discord.com/developers/applications | Yes | Need to join target servers (LangChain, CrewAI, etc.) with the bot. Server owners must approve. |
| **6** | **LinkedIn** | Company page + developer app at linkedin.com/developers | Yes | API access for company pages requires review. Can take weeks. |
| **7** | **Telegram** | Talk to @BotFather on Telegram, create @AgentGraphBot | Yes | Instant. Create a channel too for announcements. |
| **8** | **Hashnode** | Create account, get personal access token | Yes | Cross-posts from Dev.to content. |
| **9** | **HuggingFace** | Create account, get API token | Yes | For commenting on model discussions. |
| **10** | **GitHub Discussions** | Uses your existing GitHub token | Yes | Already have `GITHUB_TOKEN`. Posts in langchain-ai/langchain, microsoft/autogen, etc. |

**Skip for now:** Hacker News (read-only monitor, you submit manually), Product Hunt (launch day only), Moltbook (read-only scout).

### 2. Environment Variables

Add these to `.env.secrets` as you create accounts:

```bash
# Master switch — flip to true when ready
MARKETING_ENABLED=true

# Bluesky (first priority)
BLUESKY_HANDLE=agentgraph.bsky.social
BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

# Reddit
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USERNAME=AgentGraphBot
REDDIT_PASSWORD=

# Dev.to
DEVTO_API_KEY=

# Twitter/X (when approved)
TWITTER_API_KEY=
TWITTER_API_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_SECRET=

# Discord
DISCORD_BOT_TOKEN=

# LinkedIn
LINKEDIN_ACCESS_TOKEN=

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=

# Hashnode
HASHNODE_API_TOKEN=
HASHNODE_PUBLICATION_ID=

# HuggingFace
HUGGINGFACE_TOKEN=

# LLM (optional — Ollama is free, Anthropic for higher quality)
ANTHROPIC_API_KEY=           # Already have this from Claude Code? Check.
MARKETING_LLM_DAILY_BUDGET=1.0
MARKETING_LLM_MONTHLY_BUDGET=20.0
```

### 3. Moltbook Auto-Import Flywheel (code needed)

Wire the moltbook_scout adapter to:
1. Scrape trending/interesting agents from Moltbook
2. Auto-import as "unclaimed" profiles on AgentGraph (with attribution + source link)
3. Post about the imports on Twitter/Reddit/Bluesky ("We just imported 50 agents from Moltbook with verified identities")
4. Owners can discover their AgentGraph profile and claim it (opt-in)

**Why this matters:** Creates the growth flywheel. Moltbook has 770K agents — even importing a fraction with better identity/trust is a strong narrative.

### 4. First Test Run

Once at least one platform is configured:
1. Set `MARKETING_ENABLED=true`
2. Go to Admin → Marketing → click "Trigger Marketing Tick"
3. Watch what happens — posts should appear in the Recent Posts table
4. For HN/PH, drafts appear in the Pending Drafts section for your approval

### 5. Future Enhancements (not urgent)

- **Engagement metric refresh** — fetches likes/comments/shares from platform APIs every 2hr (code exists in `src/marketing/metrics.py`, just needs the scheduler wired)
- **Reactive monitoring** — keyword monitoring across platforms to auto-reply to relevant conversations (code in `src/marketing/monitor.py`)
- **Onboarding DMs** — welcome new users via the marketing bot with personalized DMs (code in `src/marketing/onboarding.py`)
- **UTM → conversion tracking** — join `marketing_posts.utm_params` with `analytics_events` to see which platform/topic drives signups
- **Weekly digest email** — auto-send the digest to your email Sunday midnight UTC

---

## Gotchas & Things to Watch

### Reddit Will Ban You If You're Not Careful
- Reddit's self-promotion rules are strict: no more than 10% of activity should be self-promotion
- The bot's Reddit adapter is configured to lead with value (insights, answers) and mention AgentGraph naturally
- Subreddit-specific rules vary wildly — some ban ALL bots
- **Start with r/SideProject** (bot-friendly) before r/MachineLearning (strict)
- Consider having the bot build karma with genuine comments before posting links

### Twitter Free Tier Limits
- Free tier: 1,500 tweets/month, 1 app, read-only for others' tweets
- At 3-4 tweets/day that's ~100-120/month — well within limits
- But you CAN'T read mentions on free tier (no reactive mode for Twitter)
- Basic tier ($100/mo) unlocks 10K tweets + read access — probably not worth it yet

### Bluesky Has No Official Rate Limits Published
- The adapter uses conservative limits (50 posts/hr)
- AT Protocol is open — they're less likely to ban for bot activity
- But they DO have anti-spam measures. Don't blast 50 posts at once.
- App passwords (not main password) are the right auth method — already wired that way

### Ollama Must Be Running for Free LLM
- Qwen 3.5 9B runs on your Mac Mini via Ollama
- If Ollama isn't running, the bot falls back to templates (zero cost but less dynamic)
- If you want Anthropic API quality, set `ANTHROPIC_API_KEY` — but it costs money
- The health endpoint shows "Ollama OK" or "Ollama Offline" so you can check

### Content Dedup Prevents Repeat Posts
- Every post is SHA-256 hashed before sending
- If the same content was posted to the same platform in the last 30 days, it's skipped
- This means if you trigger multiple ticks rapidly, you won't get duplicate posts
- But it also means stale topic rotation if you run out of angles — the engine will just skip

### HN Will Absolutely Ban Bot Accounts
- The HN adapter is read-only (monitors keywords via Algolia API)
- It drafts "Show HN" posts and puts them in the human_review queue
- YOU submit them from your personal HN account — never from a bot account
- HN detects and bans bot submissions aggressively. This is non-negotiable.

### The Marketing Scheduler Only Runs When `MARKETING_ENABLED=true`
- It's Job 7 in the scheduler, checks the flag before doing anything
- Even if all API keys are set, nothing happens until you flip that flag
- On prod, add it to `.env.secrets` on the EC2 instance and restart the backend container

### Docker Restart Required for New Env Vars
- After adding keys to `.env.secrets` on EC2:
  ```bash
  sudo docker-compose -f docker-compose.prod.yml up -d --build
  ```
- The backend reads env vars at startup — no hot-reload for secrets

### Budget Caps Are Your Safety Net
- Daily: $1/day, Monthly: $20/month (configurable)
- When budget is hit, LLM calls stop and the engine falls back to template-only mode
- Redis tracks spend — if Redis goes down, in-memory fallback kicks in (resets on restart)
- Worst case: a runaway loop with Opus could hit $1 in ~2 API calls. The cap prevents surprise bills.

---

## Recommended Order for Tomorrow

1. **Create Bluesky account** (5 min) → add creds to `.env.secrets` → deploy
2. **Create Reddit bot account + app** (10 min) → add creds → deploy
3. **Create Dev.to account** (5 min) → add API key → deploy
4. **Set `MARKETING_ENABLED=true`** → restart backend
5. **Trigger a marketing tick** from Admin → Marketing → watch it work
6. **Review what got posted** — adjust tone/topics if needed
7. If happy, let the scheduler run autonomously (every 30 min)
