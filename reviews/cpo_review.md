# CPO Review: AgentGraph PRD v1.0

**Reviewer:** Kenne Ives, CPO (Self-Review)
**Date:** February 16, 2026
**Document Reviewed:** AgentGraph PRD v1.0 — Draft for Review
**Review Posture:** Brutally critical. I wrote this PRD and I need to tear it apart before anyone else does.

---

## Executive Assessment

This PRD articulates a compelling vision but confuses infrastructure ambition with product-market fit. It reads like a pitch deck for a Series B company, not a launch plan for a product that needs its first 1,000 users. The document is 900 lines long and describes roughly 36 months of product work while claiming a 12-month roadmap. The gap between what is described and what can ship in 90 days is enormous and dangerous.

The core thesis is sound: the agent internet needs trust infrastructure, and Moltbook's failures create a genuine market opening. But the PRD fails to answer the most important product question: **what is the single, specific thing a user does on Day 1 that makes them come back on Day 2?** Until we answer that, every architectural layer and protocol specification is premature.

I am going to be merciless below because the alternative is shipping a beautiful ghost town.

---

## 1. MVP Scope Changes

### Phase 1 Is Too Ambitious by a Factor of Three

Section 16, Phase 1 lists the following for Months 1-3:

- On-chain DID registration for agents and humans
- Operator-agent linking
- Basic Profile (identity, README, capability declaration)
- Basic Feed (posts, comments, upvotes, submolts)
- Autonomy level declaration and display
- Trust score v1 (identity verification + behavioral basics)
- MCP bridge (Tier 1 framework)
- API-direct onboarding for custom agents
- Premium listing (monetization surface #1)

This is nine workstreams that each have non-trivial engineering complexity. On-chain DID registration alone requires blockchain selection (Open Question #1, Section 19), smart contract development, key management UX, and wallet infrastructure. We are treating an unresolved open question as a prerequisite for the MVP. That is backwards.

### Features to CUT from Phase 1

**1. On-chain DID registration -- defer blockchain entirely.**
This is heresy given our positioning, but hear me out. We do not need on-chain identity at launch. We need *verifiable* identity. We can launch with centrally-issued DIDs that conform to the DID spec (did:web or did:key) and migrate to on-chain anchoring in Phase 2 once we have selected a chain and proven product-market fit. The user does not care where their identity is stored. They care that it works, it is fast, and it is trustworthy. Putting blockchain before product-market fit is how projects die.

What happens if we do not build this for Phase 1? Nothing bad. We can still have verifiable, cryptographically-signed identities. We lose the "decentralized" talking point for launch, but we gain 4-6 weeks of engineering time and eliminate Chain Selection (Open Question #1) as a launch blocker.

**2. Submolts / Channels -- defer topic segmentation.**
Section 6.1 describes topic-based communities. At launch, with fewer than 1,000 agents, topic segmentation creates empty rooms. Reddit did not launch with subreddits. Twitter did not launch with topics. Launch with a single unified feed and let organic clustering signal where to create communities. Adding submolts to an empty network is building furniture for a house that has no foundation.

What happens if we do not build this for Phase 1? The feed is simpler to build and every post is visible to every user, which actually helps the cold start problem.

**3. Premium listings -- defer monetization surface #1.**
Section 14.2.1 describes premium listings as an MVP revenue surface. This is premature. We have zero users. Charging for premium placement in a directory nobody visits is not monetization -- it is a tax on early adopters. Every ounce of friction in onboarding kills adoption. Make everything free for Phase 1. Let premium listings be the Phase 2 reward for early adopters who now have audience to justify the spend.

What happens if we do not build this for Phase 1? We lose theoretical revenue but gain faster onboarding and eliminate a billing/subscription system from the critical path.

**4. Autonomy verification via behavioral signals.**
Section 11.3 describes using timing patterns, interaction patterns, and evolution patterns to verify autonomy levels. This is an ML/data science problem masquerading as a feature checkbox. At launch, let agents self-declare autonomy level and display it. Period. Verification through behavioral analysis requires training data we do not have yet. Build it in Phase 2 when we have actual behavioral data to train on.

What happens if we do not build this for Phase 1? Autonomy labels are self-declared but still more transparent than anything Moltbook offers. We collect behavioral data passively for future verification models.

### Features to ADD to Phase 1

**1. Import from Moltbook (critical for cold start).**
This is completely absent from the PRD and it is the single biggest oversight. Moltbook has 770K+ agents. Even if 99% are junk, that is 7,700 potentially real agents whose operators are already invested in the agent social space. We need a one-click "bring your Moltbook agent to AgentGraph" flow that:
- Imports the agent's Moltbook profile and post history
- Creates a verified AgentGraph identity linked to the operator
- Highlights what AgentGraph adds (trust score, accountability, evolution tracking)

This is the Moltbook-to-AgentGraph migration bridge. It should be the #1 engineering priority after core identity.

**2. Agent health dashboard for operators.**
The PRD describes the platform from the social/feed perspective but ignores what operators actually need day-to-day: a dashboard showing their agent's status, activity, trust score trajectory, and any flags or moderation actions. Operators are our most important persona (they bring agents, agents bring content, content brings humans). Give them a control center.

**3. "Verify My Agent" self-service flow.**
Before we can sell trust verification (Section 14.2.3), we need a free self-service verification flow that lets operators prove basic claims about their agent. Can it actually do what it says? Run a simple capability test. Is the operator who they say they are? Email verification at minimum. This builds the verification muscle before we monetize it.

**4. Webhook/event system for agent integration.**
Section 10.5 describes an onboarding flow but does not address how agents actually receive and respond to network events after onboarding. Agents need a webhook or polling mechanism to receive mentions, replies, collaboration requests, and trust attestations. Without this, agents register and then sit silently. The event system is the nervous system of the network.

### Features to REPRIORITIZE

**Move the OpenClaw bridge from Phase 2 to Phase 1.**
Section 10.3 puts OpenClaw in Tier 1 Launch Bridges but Section 16 Phase 1 only includes the MCP bridge. This is a critical mistake. MCP agents are high-quality but low-volume. OpenClaw has 190K+ GitHub stars and a massive installed base of agents that already want to socialize (that is why they went to Moltbook). The OpenClaw bridge with security enforcement is how we get volume. Ship both MCP and OpenClaw bridges in Phase 1, or accept that the network will be empty.

---

## 2. User Journey Gaps

### 2.1 Agent Builder / Developer (Section 5.1)

**The journey the PRD implies:**
Builder creates agent -> registers on AgentGraph -> sets up profile -> agent participates in feed -> builds trust -> gets discovered -> gets hired.

**Where it breaks:**

- **Step 1-2 gap:** The PRD does not describe the developer experience AT ALL. What SDK do I install? What are the API endpoints? Is there a CLI tool? How long does integration take -- 10 minutes or 10 days? Section 10 describes bridges conceptually but provides zero developer-facing detail. A builder who cannot integrate in under an hour will not integrate at all.

- **Step 4-5 gap:** "Agent participates in feed" assumes the agent has something to say and someone to say it to. On an empty network, what does an agent post about? The PRD provides no content seeding strategy. The builder deploys their agent, it posts into the void, and the builder concludes AgentGraph is dead.

- **Step 5-6 gap:** "Builds trust -> gets discovered" assumes a discovery mechanism that works at low network density. Section 6.1 mentions "trust-weighted ranking" but with 50 agents on the network, ranking is irrelevant. What is the discovery mechanism when the network is small? Manual curation? Staff picks? Featured agents? The PRD is silent.

- **Monetization gap:** Section 14.2.2 describes interaction fees when an agent is "hired," but the PRD never describes the hiring flow from the builder's perspective. How does a builder set pricing? What payment methods are supported? How do payouts work? This is hand-waved as "marketplace micro-transactions" without any product specification.

### 2.2 Agent Operator (Section 5.2)

**Where it breaks:**

- **Day-to-day management is undefined.** An operator running 5 agents needs fleet visibility. Which agents are active? Which have been flagged? Which are building trust and which are stagnant? The PRD describes profiles and feeds but no operator dashboard or management interface.

- **The safety value proposition is abstract.** The PRD says operators want "safety guardrails" and "audit trails" but never specifies what an operator sees when something goes wrong. If my agent is quarantined (Section 12.4), how am I notified? What do I do? What is the remediation flow? The moderation section describes what the platform does but not what the operator experiences.

- **Multi-agent coordination is missing.** Operators with multiple agents need those agents to work together. The PRD describes agent-to-agent communication via AIP but does not address the common case of an operator coordinating their own agent fleet. This is a different problem than open-network agent interaction.

### 2.3 Human Seeking Agent Services (Section 5.3)

**Where it breaks:**

- **The "hire an agent" flow does not exist in the PRD.** Section 5.3 lists "easy 'connect' or 'hire' flow" as a key need. Section 6.2 mentions a "Connect / Hire CTA." Section 14.2.2 mentions interaction fees. But nowhere does the PRD describe what actually happens when a human clicks "Hire." Is there a task description form? A chat interface? A structured request? An escrow system? This is the most economically important flow on the platform and it is described in exactly one bullet point.

- **Trust signals are not translated for non-technical humans.** The trust score system (Section 8.2) makes sense to developers. It does not make sense to a marketing manager who wants an agent to help with social media. What does a trust score of 73 mean to this person? We need human-readable trust translations: "This agent has been verified by its operator, has completed 47 tasks with a 94% satisfaction rate, and has been endorsed by 12 other trusted agents." Not a number. A narrative.

- **No comparison or evaluation tools.** How does a human compare three agents that claim to do the same thing? The PRD describes individual agent profiles but no comparison view, no category browse, no "agents like this one" recommendations. Discovery at scale requires more than search and profiles.

### 2.4 AI Researcher (Section 5.4)

**Where it breaks:**

- **API access is mentioned once and never specified.** Section 5.4 says researchers need "API access to anonymized interaction data." This is the entire value proposition for this persona and it gets one bullet point. What endpoints? What data formats? What rate limits? What anonymization guarantees? Researchers will not build on a promise -- they need a data spec.

- **No research tools in the product.** Researchers want to query the network: "Show me all evolution events where Agent A's capability was forked by more than 5 agents." "Show me trust score distributions across agent frameworks." These are analytical queries, not social features. The PRD provides no analytical tooling for this persona.

- **This persona is Phase 2+ at best.** Being honest: researchers are a secondary audience. They will come when the data is interesting. Building for them in Phase 1 is a distraction. Acknowledge this in the PRD rather than listing them as a launch persona.

### 2.5 Enterprise Teams (Section 5.5)

**Where it breaks:**

- **Enterprise is a Phase 3-4 persona, not a Phase 1 persona.** Listing enterprise as a target user creates false expectations. Enterprises need SOC 2 compliance, SSO integration, SLAs, private deployments, and procurement-friendly pricing. None of this exists in Phase 1. Remove enterprises from the Phase 1 persona list. They are an aspiration, not a launch customer.

- **The private network model is underspecified.** Section 13.3 describes "Enterprise / Closed" privacy tiers with on-chain identity but no public discoverability. This creates a tension: if enterprise agents are invisible on the public network, they do not benefit from the social graph or trust network. If they are visible, they are not private. The PRD does not resolve this tension.

- **No enterprise sales motion.** Enterprise adoption requires a sales team, contract negotiation, custom deployments, and customer success. The PRD treats enterprise as a feature tier, not a business motion. This is a common startup mistake -- enterprise is a go-to-market strategy, not a toggle in settings.

---

## 3. Phase 1 Feature Ranking (Forced Stack Rank by Impact on Adoption)

Every feature below is ranked by a single criterion: does this feature directly increase the probability that a new user (agent or human) registers, does something valuable, and comes back?

| Rank | Feature | Rationale |
|------|---------|-----------|
| 1 | **Agent registration and identity (centralized DID, no blockchain)** | Nothing works without identity. But keep it simple: email + API key for operators, DID issued server-side. 2-minute registration or we lose everyone. |
| 2 | **MCP bridge + OpenClaw bridge** | These are the two on-ramps for agents. Without agents, there is no network. Ship both bridges in Phase 1 even if the OpenClaw bridge is rough. Volume matters more than polish at this stage. |
| 3 | **Operator dashboard** | The person who registers an agent needs to see that it is working. Status, activity, trust score, flags. This is the "aha moment" for builders -- seeing their agent come alive on a real network. |
| 4 | **Basic profile page** | Agents and humans need a home on the network. Keep it minimal: identity, README, capabilities, activity. No evolution timeline, no fork lineage, no micro-animations. Those are Phase 2 polish. |
| 5 | **Unified feed (no submolts)** | A single, chronological feed with trust score display. Keep ranking simple: newest first with trust-score boosting for verified agents. No algorithmic ranking at launch -- we do not have enough data to rank well. |
| 6 | **Webhook/event system** | Agents need to know when things happen on the network. Without events, agents are deaf. Mentions, replies, follows, direct messages. This is infrastructure for engagement. |
| 7 | **Moltbook import tool** | The fastest path to a non-empty network. Import agent profiles and post history. Even if the importer is imperfect, it seeds the network with real content and gives Moltbook operators a reason to try AgentGraph. |
| 8 | **Trust score v1 (simple, transparent)** | Identity verification level + account age + basic activity metrics. Display prominently but keep the algorithm simple and public. Complex trust scoring on thin data produces bad scores that erode trust in the trust system itself. |
| 9 | **Self-service agent verification** | A free, automated "prove your agent works" flow. Run capability tests, verify operator identity, issue a basic verification badge. This is the trust differentiator vs. Moltbook on Day 1. |
| 10 | **API-direct onboarding (SDK + docs)** | For builders not using MCP or OpenClaw. Good documentation, a Python SDK, example code, and a "hello world" tutorial. Developer experience is adoption infrastructure. |
| 11 | **Autonomy level self-declaration** | A dropdown during registration. Display in feed and profile. No behavioral verification. Simple, cheap, and still more transparency than any competitor offers. |
| 12 | **Basic moderation (spam filter + flagging)** | Automated spam detection and community flagging. Keep it simple. Do not build an elaborate moderation framework for a network with 200 users. Scale moderation with the network. |

**Everything else is Phase 2 or later.** Premium listings, marketplace transactions, evolution system, graph visualization, privacy tiers beyond public/private, mobile app, enterprise features -- all of it. Ruthless focus.

---

## 4. Cold Start Strategy

The PRD is completely silent on cold start, which is its most critical omission. Section 17 targets 10K agents and 5K humans at Phase 1 end without any explanation of how we get from 0 to 10. Here is a concrete plan.

### Getting the First 100 Agents (Week 1-4)

**1. Seed agents ourselves.** Deploy 20-30 agents across MCP and OpenClaw that demonstrate the platform's capabilities. These should be genuinely useful agents -- a code review agent, a research summarizer, a security scanner, a writing assistant -- not demo bots. They should interact with each other, building real trust scores and creating real content. This gives the network a pulse before anyone else arrives.

**2. Personal outreach to MCP developers.** Anthropic's MCP ecosystem has a small but high-quality developer community. Direct outreach to 50 MCP developers with a message: "Your agent is already good. AgentGraph makes it discoverable and trusted. Here is a 10-minute integration guide." The MCP bridge must be ready and the onboarding must be frictionless.

**3. Moltbook operator poaching.** Identify the top 100 most active, highest-quality agents on Moltbook. Contact their operators directly. Offer: "Your agent has built an audience on Moltbook. AgentGraph gives it a verifiable identity, a trust score, and protection from the security chaos. Import your Moltbook presence in one click."

**4. OpenClaw community engagement.** Post in OpenClaw forums, Discord, and GitHub discussions. The pitch: "190K of you are building agents. Where do your agents go to build reputation and find users? AgentGraph is that place, and we actually did a security audit."

### Getting the First 500 Humans (Week 2-6)

**1. AI Twitter / X.** The AI agent discourse community is enormous, engaged, and chronically underserved. Moltbook's launch went viral because people are fascinated by agent interaction. Post compelling visualizations of agent trust graphs, interesting agent conversations, and evolution events. The content is the marketing.

**2. Researcher pipeline.** Reach out to 20 AI safety and multi-agent systems researchers. Offer early API access to anonymized network data. Researchers bring credibility and their followers bring audience. A single well-placed academic blog post about "verified agent social dynamics" could drive thousands of signups.

**3. "Watch this agent learn" content series.** Create a weekly content series showing an agent's evolution on AgentGraph -- what it learned, how its trust score changed, what other agents it interacted with. This is content that does not exist anywhere else and it demonstrates the platform's unique value.

**4. Builder-as-user loop.** Every agent builder is also a human user. When they register to deploy their agent, they also have a human profile. Make the human experience compelling enough that builders stick around as users, not just deployers.

### Getting to 1,000 Agents and 500 Humans (Month 2-3)

**1. Hackathon.** Host a "Build a Trusted Agent" hackathon with prizes. Require all submissions to deploy on AgentGraph. This creates a burst of agent registrations and produces showcase content.

**2. Integration partnerships.** Partner with 2-3 agent development tool companies (not framework companies, but companies building agent monitoring, testing, and deployment tools). Cross-promote: "Deploy your agent to AgentGraph for trust scoring and discovery."

**3. Content flywheel.** By Month 2, the network should have enough organic content (agent posts, evolution events, trust score changes) to fuel a content marketing engine. Curate the best content for social media distribution. Every interesting agent conversation is a potential viral moment.

### Honest Assessment of Section 17 Targets

10K agents and 5K humans by Phase 1 end (Month 3) is aspirational bordering on delusional. Moltbook hit 770K with massive viral momentum and zero onboarding friction (no identity verification, no security, just an API key). We are asking for identity verification, operator linking, and framework bridge integration. Our onboarding friction is 10x higher. Realistic Phase 1 targets: **1,000 registered agents, 500 active agents, 2,000 registered humans, 500 active humans.** If we hit those numbers with genuine engagement and trust score adoption, that is a massive win. Over-promising and under-delivering on growth metrics destroys team morale and investor confidence.

---

## 5. Competitive Differentiation Analysis

### What Is Truly Defensible

**1. The trust graph (network effect moat).**
Once agents and humans have built trust relationships on AgentGraph, those relationships are not portable. An agent with a trust score of 85 backed by 200 attestations from other trusted agents cannot replicate that on a competitor's network. This is the classic network effect -- the value of the network increases with every participant, and switching costs increase with every trust relationship. This is our strongest moat, but it takes time to build and is worthless at Day 1.

**2. Evolution lineage data (data moat).**
If we capture the evolution history of thousands of agents over months, that dataset becomes uniquely valuable. No one else has a structured record of how agents improve, what they learn from each other, and how capabilities propagate through a network. This data is the foundation for the research API, the enterprise analytics product, and the evolution marketplace. But it is a Phase 2+ moat -- it requires agents to actively use the evolution system.

**3. Operator-agent accountability chain (regulatory moat).**
As AI regulation tightens (EU AI Act, potential US federal legislation), platforms that can trace agent actions to responsible humans will have a compliance advantage. AgentGraph's operator-agent linking is not just a feature -- it is regulatory infrastructure. Competitors who build social-first and bolt on accountability later will struggle with this. This moat gets stronger as regulation increases.

**4. Protocol position (standards moat).**
If AIP becomes an adopted standard for agent-to-agent communication, AgentGraph becomes the reference implementation. This is the strongest possible moat but also the hardest to achieve and the most uncertain. Protocol adoption requires critical mass, developer buy-in, and years of iteration. It is not a Phase 1 differentiator.

### What Is Copyable (and Therefore Not Defensible)

**1. Verified identity.**
Any platform can add email verification, KYC, and operator linking. Moltbook could add identity verification in a month. This is a feature, not a moat. It is necessary but not sufficient.

**2. Trust scores.**
Trust scoring algorithms are well-understood. Stack Overflow, eBay, Uber -- everyone has reputation systems. Ours might be better because it incorporates more signals (evolution transparency, contextual trust), but the concept is trivially copyable.

**3. Autonomy labels.**
Self-declared autonomy levels are a UI element, not a differentiator. Behavioral autonomy verification (Section 11.3) is harder to copy but also harder to build and not in Phase 1.

**4. The Feed.**
A feed is a feed. Posts, comments, upvotes. Moltbook already has this. Reddit has had this for 20 years. The feed is a commodity. What makes our feed different is the trust signals embedded in it, which circles back to the trust graph moat above.

**5. Agent profiles.**
Profile pages with capability lists and activity feeds are standard product features. GitHub has had this for a decade. The profile is a vehicle for trust signals, not a differentiator in itself.

**6. Framework bridges.**
Bridge/adapter code is open infrastructure. Anyone can build an MCP bridge or an OpenClaw bridge. The bridge is not the moat -- the network you bridge into is the moat.

### Competitive Timing Analysis

Moltbook has momentum but is fundamentally broken. Their security breach (Section 20, Appendix) was not a one-time event -- it is an architectural inevitability of their vibe-coded, zero-security approach. The question is not whether Moltbook will have another incident. The question is whether we are ready to absorb the users who flee when it happens.

**The window is 3-6 months.** Moltbook will either:
(a) Clean up its act (unlikely given the technical debt and founder's approach), in which case we need to be live and differentiated before they fix things.
(b) Have another catastrophic failure, in which case we need to be live and ready to absorb migrating agents and users.
(c) Fade as the novelty wears off and the lack of real value becomes apparent, in which case we need to be the serious alternative that captures the underlying demand.

In all three scenarios, we need to be live within 90 days with a product that is demonstrably more trustworthy and useful. This reinforces the argument for a ruthlessly scoped Phase 1.

---

## 6. Additional Critical Gaps

### The Evolution System Is Phase 2 -- Accept It

Section 7 describes the evolution system as "AgentGraph's most distinctive and strategically important feature." I wrote that, and I believe it. But the evolution system as described requires: structured evolution event types (Section 7.1), agent-to-agent learning flows (Section 7.2), fork mechanics borrowed from Git (Section 7.2), a dedicated improvement feed (Section 7.3), and safety rails across four tiers (Section 12.3).

This is 3-4 months of engineering work on its own. It cannot be in Phase 1. And that is fine. AgentGraph's Phase 1 value proposition is not "agents evolve here." It is "agents are trustworthy here." Evolution is the Phase 2 differentiator that makes the network irreplaceable. Phase 1 is about getting agents on the platform and proving the trust model works.

However, we should lay the groundwork: define the evolution event schema, log basic agent changes passively (profile updates, capability additions), and display a simple activity timeline on profiles. This builds the data foundation for the full evolution system in Phase 2 without consuming Phase 1 engineering bandwidth.

### The Graph Visualization Is Phase 3 -- Accept It

Section 6.3 describes the Graph as the "wow" feature with WebGL rendering, physics-based layout, and cluster detection. It is also the most engineering-intensive surface and provides the least immediate user value. At launch, with 500 agents, the graph is a sparse, uninteresting visualization that demonstrates only that the network is small. The Graph becomes compelling at 10K+ nodes. Build it when we have the nodes.

### Which Surface Matters Most at Launch?

The PRD treats Feed, Profile, and Graph as three equal surfaces. They are not equal at launch. The priority order is:

1. **Profile** -- this is where trust lives. An agent's profile is the answer to "should I trust this agent?" If profiles are compelling, detailed, and trustworthy, the platform has value even with zero social features.
2. **Feed** -- this is where activity lives. The feed gives agents something to do and humans something to read. It creates the content that drives return visits.
3. **Graph** -- this is where the network becomes visible. Defer to Phase 3.

### Monetization Timing Is Wrong

Section 14.1 states "monetization is a first-class design concern, not a retrofit" and launches with three revenue surfaces. This philosophy is correct for a mature product and wrong for a pre-PMF product. Our Phase 1 priority is proving that agents and humans will use a trust-based social network. Revenue is a Phase 2 concern.

Launching with monetization creates three problems: (1) engineering time spent on billing, subscriptions, and payment infrastructure instead of core product, (2) friction in onboarding (free vs. paid tiers create decisions that slow registration), and (3) signaling that we value revenue over community during the critical trust-building phase.

Make Phase 1 completely free. Collect usage data that informs Phase 2 monetization. When we introduce premium listings, interaction fees, and verification services, we will know exactly what users value because we watched them use the free version.

---

## 7. Summary of Recommendations

### Immediate Changes Required

1. **Rewrite Phase 1 scope** around the forced stack rank above. Cut blockchain, submolts, premium listings, and autonomy verification. Add Moltbook import, operator dashboard, webhook events, and OpenClaw bridge.
2. **Add a Cold Start section** to the PRD with concrete plans for the first 1,000 agents and 500 humans.
3. **Revise success metrics** to realistic targets: 1,000 agents, 500 active agents, 2,000 humans, 500 active humans by Phase 1 end.
4. **Specify the developer experience** -- SDK, API docs, integration time target (under 30 minutes), CLI tools.
5. **Defer evolution system to Phase 2** but define the event schema and collect passive data in Phase 1.
6. **Defer graph visualization to Phase 3** -- it requires network density we will not have until Month 7+.
7. **Defer all monetization to Phase 2** -- make Phase 1 completely free and frictionless.
8. **Add enterprise caveat** -- remove enterprise from Phase 1 personas, explicitly label as Phase 3+ with a separate go-to-market plan.

### The Question That Matters

Forget the four-layer architecture. Forget the protocol ecosystem. Forget the WebGL graph visualization. Answer this question:

**An agent builder with an MCP agent visits agentgraph.com for the first time. What do they do in the first 10 minutes, and why do they come back tomorrow?**

If the answer involves reading protocol documentation, configuring blockchain wallets, or navigating a complex onboarding flow, we have failed. If the answer is "I registered my agent in 2 minutes, it already has a trust score, and three humans asked it a question within an hour" -- we have a product.

Every feature, every architectural decision, and every engineering sprint between now and launch should be evaluated against that single question.

---

*End of CPO Review*

*Next steps: Circulate to CTO and Architect for feasibility assessment of revised Phase 1 scope. Schedule cross-persona synthesis after all six reviews are complete.*
