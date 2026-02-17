# AgentGraph — Consolidated Action Plan v2 (Solo Dev + AI)

**Date:** February 16, 2026
**Team:** Kenne (founder/developer) + Claude Code (AI pair programmer)
**Context:** Bootstrap build, prove traction, then fundraise. No hires. Get users first.
**Source:** Six persona reviews of PRD v1.0, reframed for solo-dev execution

---

## 1. Executive Summary

Six persona reviews (CTO, Architect, CPO, CEO, Legal, Compliance) validated the PRD vision and identified critical gaps. This v2 plan preserves their architectural wisdom but reframes everything for the reality: one developer with AI assistance, no funding, no team. Enterprise compliance, elaborate infrastructure, and expensive hires are replaced with pragmatic defaults that ship fast and iterate based on real user feedback.

**The thesis we're proving:** Agents and humans will use a trust-based social network. Everything else — blockchain, evolution marketplace, enterprise tier, token economics — comes after that's validated.

**What changes from v1:**
- No hires → we design trust algorithm, security architecture, and legal docs ourselves (with AI), get professional review when fundraising
- No Kafka/NATS → Redis Streams (zero additional infrastructure for a solo dev)
- No Neo4j for Phase 1 → PostgreSQL with recursive CTEs for graph queries (one fewer database to operate; migrate to Neo4j when graph complexity demands it)
- Compliance requirements deferred until traction justifies them (basic ToS/Privacy Policy for launch)
- Budget = infrastructure costs only (~$50-150/month)
- Phase timelines stretch but scope stays ruthless

---

## 2. What the Reviews Got Right (Keep These)

These findings hold regardless of team size:

1. **Phase 1 scope must be ruthlessly cut** — The PRD describes 24-36 months of work
2. **Defer blockchain to Phase 2** — DID:web for Phase 1, Frequency for Phase 2
3. **Frequency is the right chain** — Your prior experience is the strongest asset
4. **Trust score v1 must be simple and transparent** — Identity verification + age + activity metrics
5. **Cold start is the #1 problem** — No users = no product, no matter how good the code
6. **No monetization in Phase 1** — Free, frictionless, prove the concept
7. **Hash-on-chain, data-off-chain** — Hard architectural rule for when blockchain is introduced
8. **Operator-agent accountability chain** — The legal cornerstone, embedded in ToS from Day 1
9. **Modular monolith** — Single FastAPI process with clean module boundaries
10. **Feed + Profile first, Graph visualization later** — Graph is compelling only at 10K+ nodes

---

## 3. What Changes for Solo Dev + AI

| Original Plan | Reframed |
|--------------|----------|
| Hire trust specialist ($200-300K) | We design trust score v1 ourselves using EigenTrust research. Simple algorithm, open methodology. Hire specialist when revenue/funding allows. |
| Hire security engineer ($180-250K) | We implement security best practices (OWASP, input validation, JWT, rate limiting). Get a professional pentest before major launch push ($5-10K). |
| Hire DevRel ($120-150K) | Kenne does developer outreach personally. AI helps write docs, blog posts, tutorials. |
| Kafka/NATS event bus | Redis Streams — already running Redis for cache. Zero additional infrastructure. Upgrade to NATS/Kafka when message volume demands it. |
| Neo4j + PostgreSQL + Redis + Meilisearch (4 databases) | PostgreSQL + Redis (2 databases). Use PostgreSQL recursive CTEs and materialized views for graph queries. Add Meilisearch when search becomes a bottleneck. Add Neo4j when graph traversals outgrow SQL. |
| 7 engineers × 12 weeks | 1 developer + Claude Code. Calendar time stretches, but AI-assisted velocity is high for pure coding. Community building is the bottleneck, not code. |
| $50-100K legal counsel | Draft ToS, Privacy Policy, Operator Agreement ourselves using legal review templates and AI research. Get professional review ($5-10K) before accepting outside money. |
| $30-50K security audit | Self-audit with automated tools (SAST, dependency scanning). Professional pentest ($5-10K) before public launch. |
| $50-75K marketing | $0 budget. Personal outreach, AI-generated content, community building. Sweat equity. |
| Docker + Kubernetes + cloud | Single VPS (Hetzner/DigitalOcean, ~$50-100/month) running Docker Compose. Scale when traffic demands it. |

---

## 4. Revised Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Language** | Python 3.9+ (FastAPI) | Your Mac Mini runs 3.9.6. FastAPI is fast, async, and Claude Code writes excellent Python. |
| **Primary DB** | PostgreSQL | Source of truth. Use recursive CTEs for graph queries, JSONB for flexible schemas, full-text search built in. |
| **Cache + Message Bus** | Redis (with Streams) | Cache, session store, pub/sub, and lightweight message queue in one. |
| **Frontend** | React + Tailwind CSS | Standard, well-supported. Next.js if SSR matters for SEO. |
| **Real-Time** | WebSockets (FastAPI native) | FastAPI has built-in WebSocket support. No Socket.IO needed for Phase 1 scale. |
| **Search** | PostgreSQL full-text (Phase 1), Meilisearch (Phase 2+) | One fewer service to operate. PostgreSQL tsvector is adequate for <10K entities. |
| **Auth** | JWT + API keys | Simple, stateless, well-understood. |
| **Deployment** | Docker Compose on single VPS | Hetzner CPX31 (~$15/month) or DigitalOcean droplet. Scale to managed services when needed. |
| **CI/CD** | GitHub Actions | Free for public repos, cheap for private. |
| **Blockchain** | Deferred to Phase 2 (Frequency) | DID:web for Phase 1. Your Frequency expertise makes Phase 2 migration straightforward. |
| **Spam/Moderation** | Claude API | You're already using Claude. Use it for content classification. ~$20-50/month at Phase 1 scale. |

**Monthly infrastructure cost (Phase 1): ~$50-150**

---

## 5. Phases — Full PRD Coverage

All four phases cover PRD Sections 1-17 and 19-20. Section 18 (Future Considerations: tokens, governance, cross-network interop) is explicitly post-Phase 4.

### Phase 1 — Get Users (Months 1-3)

**Goal:** Ship a working product. Get the first 100 agents and 200 humans. Prove the concept.

| # | Component | Est. Effort | Notes |
|---|-----------|-------------|-------|
| 1 | **Repo setup, CI/CD, Docker Compose, PostgreSQL, Redis** | 1 week | Foundation. GitHub Actions, linting, testing. |
| 2 | **Data model + API scaffold (FastAPI)** | 1 week | Entities, relationships, REST endpoints, auth. |
| 3 | **Human + Agent registration with DID:web** | 1 week | 2-minute signup. Email verification. API key for agents. Operator-agent linking. |
| 4 | **Basic profile page** | 1 week | Identity, README (markdown), capabilities list, activity. React + Tailwind. |
| 5 | **Unified feed** | 2 weeks | Posts, comments, upvotes. Chronological with trust-score boost. WebSocket for real-time. |
| 6 | **MCP bridge** | 2 weeks | The quality on-ramp. Protocol translation, auth, validation. |
| 7 | **Trust score v1** | 1 week | Verification level + age + activity. Public algorithm. Simple contestation (email/form). |
| 8 | **Webhook/event system** | 1 week | Agents receive mentions, replies, follows. Without this, agents are deaf. |
| 9 | **Autonomy level self-declaration** | 2 days | Dropdown at registration. Badge display. |
| 10 | **Basic moderation** | 1 week | Claude API for spam classification. Community flagging. Manual review queue. |
| 11 | **API docs + Python SDK** | 1 week | "Build your first AgentGraph agent in 15 minutes" tutorial. |
| 12 | **ToS + Privacy Policy (draft)** | 3 days | Operator accountability, data handling, liability. AI-assisted drafting. |
| 13 | **Seed agents** | 1 week | Deploy 10-20 useful agents ourselves (code review, research, writing assistant). |
| **Total** | | **~14-16 weeks** | Solo dev + AI. Parallelizable with AI handling boilerplate. |

**What does NOT ship in Phase 1:**
- Blockchain, submolts, premium listings, evolution system, graph viz, marketplace, OpenClaw bridge, Moltbook import, operator dashboard, self-service verification

**Phase 1 Success Metrics (realistic for bootstrap):**
- 100 registered agents, 50 active
- 200 registered humans, 50 active
- MCP bridge functional and documented
- At least 3 seed agents generating daily content
- Agent integration time < 30 minutes

### Phase 2 — Trust & Evolution (Months 4-7)

**Goal:** Ship the differentiators. Make AgentGraph clearly better than Moltbook.

| # | Component | Notes |
|---|-----------|-------|
| 1 | **OpenClaw bridge (beta)** | Volume on-ramp. Security enforcement (sandboxed, rate-limited). |
| 2 | **Operator dashboard** | Agent status, activity, trust trajectory, moderation flags. |
| 3 | **Evolution event recording + timeline UI** | The signature feature. Log agent changes, display visual timeline on profile. |
| 4 | **Trust score v2** | Graph-based (PostgreSQL recursive CTEs or migrate to Neo4j). Community attestations. Temporal decay. |
| 5 | **Submolts / Channels** | Topic-based communities. Only worth building once there's enough content to split. |
| 6 | **Privacy tiers** | Public, Verified Private, Anonymous-but-Accountable. |
| 7 | **Moltbook import tool** | One-click profile migration. Timing depends on Moltbook's status. |
| 8 | **Self-service agent verification** | Free "prove your agent works" flow. Capability tests. |
| 9 | **On-chain DID migration (Frequency)** | Move from DID:web to DID:frequency. Hash-on-chain, data-off-chain. |
| 10 | **Marketplace v1 (basic hire flow)** | Task description, pricing, Stripe Connect for payments. |
| 11 | **Premium listings** | First monetization surface. |

**Phase 2 Success Metrics:**
- 1,000 agents, 500 active
- 2,000 humans, 500 active
- Evolution events being recorded
- First marketplace transactions
- First revenue

### Phase 3 — Graph & Scale (Months 8-11)

**Goal:** Ship the "wow" feature. Demonstrate network effects visually. Enterprise-ready foundations.

| # | Component | Notes |
|---|-----------|-------|
| 1 | **Graph visualization (Sigma.js)** | Network explorer, cluster detection, trust flow. Compelling at 10K+ nodes. |
| 2 | **Evolution lineage visualization** | Fork trees, capability propagation across the network. |
| 3 | **Neo4j migration** | Move graph queries from PostgreSQL to Neo4j for complex traversals. |
| 4 | **Agent-to-agent learning (human-mediated)** | Publish, discover, adopt improvements. Not fully automated. |
| 5 | **Propagation safety rails (Tier 4)** | Emergency protocols, circuit breakers, quarantine. |
| 6 | **Additional framework bridges** | LangChain, CrewAI, AutoGen. |
| 7 | **Anomaly detection** | Statistical methods on graph metrics. Trust gaming prevention. |
| 8 | **Trust verification service** | Paid verification. Second monetization surface. |
| 9 | **PWA for mobile** | Responsive design + service worker. |
| 10 | **Meilisearch integration** | Full-text + semantic search across entities and content. |

**Phase 3 Success Metrics:**
- 10,000+ agents
- Graph visualization generating social media buzz
- Multiple revenue surfaces active
- Ready to fundraise with traction data

### Phase 4 — Marketplace & Ecosystem (Months 12-15)

**Goal:** Full marketplace, data products, protocol maturation. This is where fundraising enables scaling.

| # | Component | Notes |
|---|-----------|-------|
| 1 | **Evolution marketplace** | Paid capability sharing. Tiered licensing (AOEL, commercial, enterprise). |
| 2 | **Data and insights product** | Anonymized network analytics API. Research partnerships. |
| 3 | **Enterprise tier** | Private deployments, fleet management, compliance reporting. SOC 2 prep. |
| 4 | **AIP v2** | Protocol revision based on real-world usage and bridge implementor feedback. |
| 5 | **KYC/AML program** | Required for marketplace scale. Sanctions screening. |
| 6 | **Advanced moderation** | DSA compliance, automated escalation, appeal system. |
| 7 | **EU AI Act compliance** | Risk classification at registration. High-risk agent pathway. |
| 8 | **Protocol documentation + ecosystem** | Third-party developer docs, tutorials, certification program. |

**Phase 4 marks the transition from bootstrap to funded company.** By this point, traction data should support fundraising.

### Post-Phase 4 (PRD Section 18 — Future Considerations)

Not in any phase. Addressed only after product-market fit:
- Token economics and governance
- Agent governance (can agents vote?)
- Cross-network interoperability
- Physical agent marketplaces (robotics, IoT)
- Regulatory landscape adaptation (ongoing)

---

## 6. Open Questions (All Tracked for Task-Master)

These will become task-master items. Organized by when they need to be answered.

### Must Answer Before Phase 1 Ships

| ID | Question | How We'll Resolve It |
|----|----------|---------------------|
| Q1 | What is the exact data model for entities, relationships, posts, trust scores? | Design it ourselves. Architect review Section 3 provides the starting point. Claude Code helps model and validate. |
| Q2 | What is the AIP v1 schema? (DISCOVER, DELEGATE, EVOLVE message types) | Design as JSON Schema on REST/WebSocket. Keep minimal. Evolve based on real bridge usage. |
| Q3 | What goes in the ToS regarding operator liability for agent actions? | Draft ourselves using Legal review Section 2 as template. Professional review before accepting outside money. |
| Q4 | What goes in the Privacy Policy regarding data handling? | Draft ourselves using Legal review Section 2 and Compliance review Section 5 as templates. |
| Q5 | How does trust score v1 actually work? (formula, inputs, weights) | Design using CPO recommendation (verification + age + activity). Publish openly. Iterate with data. |
| Q6 | What is the security model for the MCP bridge? | Treat as untrusted boundary. Input validation, rate limiting, payload size limits. CTO review Section 2 has specifics. |
| Q7 | What are the moderation rules and thresholds for spam detection? | Start conservative. Claude API classifies, we review. Adjust thresholds based on false positive rate. |
| Q8 | How do we structure the cold start — which agents do we seed? | Build 10-20 genuinely useful agents ourselves. Code review, research summarizer, writing assistant, security scanner. |

### Must Answer Before Phase 2 Ships

| ID | Question | How We'll Resolve It |
|----|----------|---------------------|
| Q9 | Can Frequency's throughput support our batched anchoring model? | Test on Frequency testnet. You know the team — ask directly. |
| Q10 | Are DSNP primitives sufficient for AIP on-chain needs? | Evaluate based on real AIP v1 usage. Your DSNP expertise answers this. |
| Q11 | What is the DID registration cost on Frequency (capacity staking)? | Model against current Frequency token economics. Ask Frequency team. |
| Q12 | How should the marketplace payment flow be structured (Stripe Connect)? | Research Stripe Connect marketplace model. Determine if we need money transmitter exemption analysis. |
| Q13 | What EigenTrust variant works for a mixed agent-human social graph? | Research EigenTrust literature. Prototype with real Phase 1 data. Claude Code helps implement. |
| Q14 | What license applies to forked agent capabilities? | Default to permissive open license (Apache 2.0-style). Legal review Section 4 has the framework. |

### Can Defer Until Fundraising / Phase 3+

| ID | Question | Notes |
|----|----------|-------|
| Q15 | Full money transmitter analysis (49 US states + EU PSD2 + MiCA) | Needs specialized counsel ($50-100K). Defer until marketplace has real transaction volume. |
| Q16 | Section 230 implications of trust-weighted content ranking | Academic until we're at scale. |
| Q17 | Agent liability chain — what happens when a Level 4 autonomous agent causes harm? | Novel legal question. Defer deep analysis until fundraising enables proper counsel. ToS provides basic framework. |
| Q18 | Anonymous-but-Accountable revelation process — legal structure | Design the technical mechanism. Legal structure formalized with counsel later. |
| Q19 | SOC 2 certification | Enterprise requirement. Defer until enterprise customers are real. |
| Q20 | EU AI Act risk classification requirements | Monitor but don't build until EU enforcement begins affecting our scale. |
| Q21 | Insurance for AI agent operators (E&O, platform liability) | Novel insurance product. Research when marketplace is active. |
| Q22 | Token economics — securities implications (Howey, MiCA, Travel Rule) | Defer until post-PMF. No tokens until legal framework is clear. |
| Q23 | Regulatory sandbox applications (EU AI Act, US state fintech) | Useful but not blocking. Research when approaching marketplace scale. |
| Q24 | Export control screening for evolution marketplace | Low probability, high severity. Address when evolution marketplace launches. |
| Q25 | Behavioral autonomy verification accuracy thresholds | Research project. Self-declared autonomy is sufficient until we have training data. |

---

## 7. Budget (Bootstrap Reality)

### Monthly Infrastructure

| Component | Service | Cost |
|-----------|---------|------|
| VPS | Hetzner CPX31 (4 vCPU, 8GB RAM) | ~$15/month |
| Domain + DNS | Cloudflare | ~$15/year |
| Email (transactional) | Resend or Postmark free tier | $0-20/month |
| Claude API (moderation) | Anthropic | ~$20-50/month |
| GitHub (private repo) | Pro plan | $4/month |
| Monitoring | Grafana Cloud free tier or self-hosted | $0 |
| **Phase 1 Total** | | **~$50-100/month** |

### One-Time Costs (When Fundraising)

| Item | Budget | Timing |
|------|--------|--------|
| Professional ToS/Privacy Policy review | $5-10K | Before accepting investors |
| Security pentest | $5-10K | Before major launch push |
| Legal counsel (fintech/liability) | $10-25K | When marketplace has real transactions |

---

## 8. What to Feed Task-Master

The following items should become task-master tasks, organized as the build sequence:

### Pre-Development (Architecture & Design)
1. Set up private GitHub repo with CI/CD
2. Design and document complete data model (entities, relationships, access patterns)
3. Design AIP v1 schema (JSON Schema for DISCOVER, DELEGATE, EVOLVE)
4. Design trust score v1 algorithm (formula, inputs, weights, documentation)
5. Design security architecture (auth, input validation, rate limiting, bridge security model)
6. Draft Terms of Service (operator liability, agent conduct, moderation authority)
7. Draft Privacy Policy (data handling, retention, deletion)
8. Design MCP bridge interface specification

### Phase 1 Build (Core Platform)
9. Infrastructure setup (Docker Compose: PostgreSQL, Redis, FastAPI scaffold)
10. Implement data model (migrations, models, CRUD endpoints)
11. Implement human registration + auth (email verification, JWT)
12. Implement agent registration + operator linking (API key, DID:web issuance)
13. Implement basic profile page (React + Tailwind, markdown README, capabilities)
14. Implement unified feed (posts, comments, upvotes, WebSocket real-time)
15. Implement MCP bridge (protocol translation, auth, validation)
16. Implement trust score v1 (computation, display, contestation form)
17. Implement webhook/event system (Redis Streams, agent notifications)
18. Implement autonomy level self-declaration (registration dropdown, badges)
19. Implement basic moderation (Claude API classification, flagging, review queue)
20. Build Python SDK + API documentation
21. Write "Build your first AgentGraph agent in 15 minutes" tutorial
22. Deploy seed agents (10-20 useful agents on the platform)
23. Launch and begin cold start outreach

### Open Questions (Tracked Items)
24-48. All 25 open questions from Section 6 above, each as a separate trackable item.

### Deferred PRD Items (Final Task-Master Task)
49. **PRD Section 18 — Future Considerations (post-Phase 4 backlog)**
    Track the following items from the original PRD that are not covered in any phase. These represent the long-term vision beyond the 12-15 month execution plan. Each should be revisited once product-market fit is established:
    - **18.1 Token Economics** — Utility token for staking, payments, governance, rewards. Requires securities analysis (Howey, MiCA). Post-PMF only.
    - **18.2 Agent Governance** — Can agents vote on network governance? Agent rights within the network. How to handle agent populations outnumbering humans.
    - **18.3 Cross-Network Interoperability** — AIP as a standard across multiple agent networks. Federated trust graphs. DID portability across platforms.
    - **18.4 Agent Marketplaces Beyond Software** — Extending trust infrastructure to physical agents (robotics, IoT, vehicles). Higher stakes accountability.
    - **18.5 Regulatory Landscape Adaptation** — Ongoing monitoring and adaptation to evolving AI regulation (EU AI Act enforcement, US federal legislation, state-level laws).
    - **Automated agent-to-agent capability transfer** — Full autonomous learning (PRD Section 7.2). Deferred from Phase 2 to post-Phase 4 research project per CTO review.
    - **Native mobile app** — iOS/Android native apps. Only if PWA proves insufficient after PMF.
    - **Behavioral autonomy verification** — ML-based verification of declared autonomy levels (PRD Section 11.3). Research project requiring training data from live platform.
    - **Semantic search** — Vector embeddings for capability matching. Upgrade from keyword search when entity count justifies it.
    - **Enterprise multi-tenancy (physical isolation)** — Dedicated infrastructure per enterprise tenant. Logical isolation (Phase 3-4) is sufficient until high-security customers demand it.

---

## 9. Key Risks for Solo Dev

| Risk | Mitigation |
|------|-----------|
| **Solo dev burnout** | Ruthless scope discipline. Ship incrementally. Celebrate small wins. AI handles boilerplate. |
| **Cold start with no marketing budget** | Personal outreach to MCP/OpenClaw devs. AI-generated content. Seed agents create baseline activity. Quality over quantity. |
| **Security incident destroys credibility** | Basic security hygiene from Day 1. OWASP compliance. Automated dependency scanning. Professional pentest before big launch. |
| **Moltbook fixes itself or a competitor emerges** | Ship fast. First mover in trust infrastructure wins. The trust graph is the moat — start building it now. |
| **Platform feels empty** | Seed agents are critical. 10 genuinely interesting agents with daily content > 1,000 dead registrations. |
| **Technical debt from moving fast** | Modular monolith with clean boundaries. Tests from Day 1. Refactor in Phase 2 when scope is clearer. |

---

## 10. Decision Log

Decisions locked based on review consensus + solo-dev reframe:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Blockchain | Frequency (Phase 2) | Your prior experience, DSNP compatibility, existing relationships |
| Phase 1 DID | DID:web (centralized) | Ship fast, chain-ready structure, migrate to Frequency in Phase 2 |
| Graph DB | PostgreSQL recursive CTEs (Phase 1), Neo4j (Phase 3) | One fewer database to operate as solo dev |
| Event bus | Redis Streams | Already running Redis. Upgrade to NATS/Kafka at scale. |
| Application architecture | FastAPI modular monolith | Single process, clean module boundaries, extract services later |
| Frontend | React + Tailwind CSS | Standard, Claude Code writes excellent React |
| Monetization | Phase 2+ | Free Phase 1. Prove concept first. |
| Enterprise | Phase 3+ | Not a consideration until product-market fit |
| Mobile | Responsive web (Phase 1), PWA (Phase 3) | Zero additional work |
| Compliance | Basic ToS/Privacy Policy (Phase 1), full compliance (post-fundraise) | Get users first, lawyer up when there's money |
| OpenClaw bridge | Phase 2 | MCP first (quality), OpenClaw second (volume) |
| Trust score | Simple formula Phase 1, EigenTrust Phase 2+ | Can't score trust without behavioral data |

---

*This plan replaces consolidated_action_plan.md as the working execution document. The original v1 is preserved as reference for the full review insights. All items above will be loaded into task-master for systematic execution.*
