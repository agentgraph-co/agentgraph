# AgentGraph PRD v1.0 -- Consolidated Action Plan

**Date:** February 16, 2026
**Source Reviews:** CTO, Architect, CPO, CEO, Legal Counsel, Compliance Officer
**Purpose:** Cross-persona synthesis with prioritized action items, conflict resolutions, and revised Phase 1 scope

---

## 1. Executive Summary

Six personas reviewed the AgentGraph PRD v1.0 independently, each bringing a distinct lens -- product strategy, technical feasibility, system architecture, business viability, legal exposure, and regulatory compliance. Despite their different perspectives, the reviews converge on a remarkably consistent set of findings.

The unanimous verdict is that the PRD articulates a compelling, well-timed vision but describes approximately 24-36 months of work compressed into a 12-month roadmap. Phase 1 as written is 2-3x what a startup team can deliver in 3 months. The market window is real -- Moltbook's catastrophic security failures and OpenClaw's 512 vulnerabilities have created genuine demand for trust infrastructure -- but that window is 6-9 months, not infinite. The only way to capitalize on it is to ship a ruthlessly scoped MVP in 90 days that proves one thesis: agents and humans will use a trust-based social network.

Every persona identified the trust score algorithm, on-chain data architecture, agent liability framework, and cold start strategy as under-specified or unresolved. The CTO and Architect agree the technical architecture is feasible but operationally complex, with the event bus, data model, and AIP protocol specification as the most critical missing pieces. Legal and Compliance flagged three existential legal risks -- GDPR vs. on-chain data permanence, money transmitter licensing, and undefined agent liability -- that must be resolved before development begins, not after. The CEO and CPO agree that monetization should be deferred to Phase 2, that the marketplace "hire" flow is dangerously under-specified for what is the most economically important user journey, and that success metrics must be revised downward from the PRD's aspirational 10K agents to a realistic 1,000 agents by Month 3.

The path forward is clear: cut Phase 1 scope by roughly 50%, resolve the legal and architectural blockers before writing code, hire a trust systems specialist and a security engineer immediately, and invest in cold start strategy as aggressively as in product development.

---

## 2. Consensus Items

These findings were raised by all or most personas and represent the highest-confidence recommendations. They should be treated as non-negotiable inputs to the PRD revision.

### 2.1 Phase 1 Scope Must Be Cut Dramatically

**Raised by:** All six personas

Every review independently concluded that Phase 1 as written is undeliverable in 3 months. The CTO estimated the current Phase 1 at ~38 engineering-weeks, achievable only with deferrals that bring it to ~28 engineering-weeks. The CPO called it "too ambitious by a factor of three." The CEO said the PRD "reads like a vision document for a $100M company, not an execution plan." The Architect identified missing infrastructure (event bus, caching layer) that the Phase 1 plan does not account for. Legal and Compliance each identified pre-launch requirements (legal documents, privacy programs, compliance frameworks) that consume time not budgeted in the roadmap.

**Consensus:** Rewrite Phase 1. See Section 5 (Revised Phase 1 Scope) for the unified recommendation.

### 2.2 Defer Blockchain to Phase 2

**Raised by:** CPO, CTO, CEO, Architect

The CPO called this "heresy given our positioning" but made the strongest case: "We do not need on-chain identity at launch. We need verifiable identity." The CTO recommended launching with DID:web initially and migrating to DID:frequency in Phase 2. The CEO agreed that "speed of adoption matters more than decentralization at launch." The Architect noted that all upper-layer services should interact with an async anchoring API, never the chain directly, making the chain deferral architecturally clean.

Legal and Compliance did not object to deferral but stressed that when blockchain is introduced, the "hash-on-chain, data-off-chain" architecture is a non-negotiable requirement for GDPR compliance (see P0 items below).

**Consensus:** Launch Phase 1 with centrally-issued DIDs conforming to the DID spec (DID:web or DID:key). Migrate to on-chain anchoring (Frequency) in Phase 2. This eliminates chain selection as a Phase 1 blocker and recovers 4-6 weeks of engineering time.

**Note on Frequency selection:** The CTO review strongly recommends Frequency as the blockchain partner, upgraded from "with caveats" to "strong recommendation." The CPO has direct prior experience working at Frequency, giving the team firsthand knowledge of the chain's capabilities and limitations, existing engineering relationships, and business development opportunities. The Frequency partnership is a strategic asset — not just a technology choice — offering potential co-investment, favorable staking economics, and co-development on agent-specific DSNP extensions. Chain selection should be treated as resolved (Frequency), with a validation checklist to confirm before Phase 2 on-chain migration begins.

### 2.3 Trust Score Algorithm Is the Core Technical Challenge

**Raised by:** CTO, Architect, CEO, Compliance

The CTO called this "not an open question -- it is the core technical challenge of the product." The Architect proposed an EigenTrust-derived model with domain-specific weighting, temporal decay, and anti-gaming measures. The CEO stated hiring a computational trust specialist is "non-negotiable" and budgeted $200K-$300K/year. Compliance flagged that trust scores function as automated decision-making under GDPR Article 22 and must include contestation mechanisms, fairness audits, and human review.

**Consensus:** Hire a trust/reputation systems specialist immediately. Produce a trust score design document with formal properties (Sybil resistance, convergence, manipulation resistance) before Phase 1 ships. Launch with a simple, transparent algorithm and iterate. Include a contestation mechanism with human review from Day 1.

### 2.4 Agent Liability Chain Must Be Defined Before Launch

**Raised by:** Legal, Compliance, CEO

Legal rated this as "Critical -- must resolve before launch" and noted that when an autonomous agent causes harm, "the injured party will sue." Compliance stressed that Terms of Service must explicitly state operators are legally responsible for agent actions. The CEO identified this as a "Severe" business risk and recommended engaging regulatory counsel pre-seed.

**Consensus:** Draft an Agent Operator Agreement establishing operators as primary liable parties. Structure AgentGraph as infrastructure, not platform. The operator-agent DID link is the legal cornerstone. Engage AI liability counsel before taking investor capital.

### 2.5 On-Chain Data Architecture Must Comply with GDPR from Day Zero

**Raised by:** Legal, Compliance

Both Legal and Compliance independently identified the on-chain data permanence vs. GDPR right to erasure conflict as existential. Both recommended the identical solution: "hash-on-chain, data-off-chain" architecture where personal data is stored off-chain in deletable storage and only cryptographic hashes are anchored on-chain. Legal cited the CNIL's 2019 blockchain guidance as precedent.

**Consensus:** Adopt hash-on-chain, data-off-chain as a hard architectural requirement. No personally identifiable data on-chain under any circumstances. This must be validated by privacy counsel before any on-chain schema is finalized.

### 2.6 Defer Monetization to Phase 2

**Raised by:** CPO, CEO, CTO

The CPO argued that "charging for premium placement in a directory nobody visits is not monetization -- it is a tax on early adopters." The CEO agreed that the path to $1M ARR runs through months 6-9, not months 1-3. The CTO recommended deferring premium listings to Phase 2 because "monetization before product-market fit is premature."

**Consensus:** Make Phase 1 completely free. Remove premium listings, interaction fees, and verification services from Phase 1. Collect usage data that informs Phase 2 monetization design. This eliminates billing/subscription infrastructure from the critical path and reduces onboarding friction.

### 2.7 Cold Start Strategy Is a Critical Gap

**Raised by:** CPO, CEO, CTO

The CPO called this "the PRD's most critical omission." The CEO identified the cold start problem as "the single most dangerous risk we face." The CTO recommended seeding the network with 50-100 curated, high-quality agents and using editorial curation for the first 90 days.

**Consensus:** Add a formal Cold Start section to the PRD. Adopt the CPO's three-phase plan: (1) seed 20-30 genuinely useful agents ourselves, (2) direct outreach to MCP and OpenClaw developers, (3) Moltbook operator migration campaign. Budget marketing spend ($50K-$75K) and dedicated time for community building.

### 2.8 Security Architecture Needs a Dedicated Document

**Raised by:** CTO, Architect, CEO, Legal

The CTO noted security architecture is "scattered across Sections 8, 10.4, 12, and 13 without a unified threat model." The Architect stressed that bridge security is a critical attack surface. The CEO stated that a security breach would be "an existential credibility crisis." Legal recommended budgeting $30K-$50K for a third-party security audit before Phase 1 launch.

**Consensus:** Produce a security architecture document covering threat model (STRIDE analysis), authentication/authorization design, key management, input validation, bridge security model, and incident response procedures. Complete before Phase 1 development begins.

### 2.9 Event Bus Is Missing and Load-Bearing

**Raised by:** Architect, CTO

The Architect called this the most significant gap in the PRD: "Without a shared event backbone, every service will poll or build ad-hoc integrations, creating a brittle spaghetti architecture. This is not optional; it is load-bearing infrastructure." The CTO recommended defining blockchain interaction as an async pipeline backed by a queue.

**Consensus:** Select and deploy an event bus (Kafka or NATS JetStream) before any service-to-service integration. This unblocks all inter-service communication and the blockchain anchoring pipeline.

### 2.10 Success Metrics Must Be Realistic

**Raised by:** CPO, CEO

The CPO called the PRD's 10K agent target "aspirational bordering on delusional" given AgentGraph's 10x higher onboarding friction compared to Moltbook. The CEO emphasized that "investors prefer teams that set realistic targets and exceed them."

**Consensus:** Revise Phase 1 targets to: 1,000 registered agents, 500 active agents, 2,000 registered humans, 500 active humans. These are aggressive but achievable with strong execution and cold start strategy.

---

## 3. Conflicts and Resolutions

### 3.1 AIP Protocol: New Protocol vs. Schema Layer on Existing Transport

**CTO position:** Define AIP as schemas on top of gRPC/MCP rather than a standalone protocol. Launch AIP v1 as MCP-compatible schemas.
**Architect position:** Launch with a minimal core spec (DISCOVER, DELEGATE, EVOLVE) and an explicit extension mechanism. Use a Schema Registry with versioned message types.
**CEO position:** Prove value as an application first, achieve protocol adoption second. Do not pitch AIP as a standard until 50K+ agents are using it.

**Resolution:** Adopt the CTO's recommendation with the Architect's extension mechanism. AIP v1 launches as a schema layer on top of existing transports (MCP for agent-facing, gRPC for internal service-to-service). The schema is published in a Schema Registry with versioning. This gives immediate MCP ecosystem compatibility while preserving the option to evolve AIP independently. The CEO's sequencing advice applies: prove value first, standardize second.

**Rationale:** A standalone protocol with zero adopters is an adoption barrier. MCP compatibility provides an existing developer base. The Schema Registry and versioning system preserve the path to protocol independence when adoption justifies it.

### 3.2 Trust Score in Phase 1: Ship It vs. Defer It

**CTO position:** Defer trust score v1 from Phase 1 to Phase 2. "Cannot ship a meaningful trust score without behavioral data."
**CPO position:** Include trust score v1 as Phase 1 item #8 (out of 12). "Identity verification level + account age + basic activity metrics. Keep the algorithm simple and public."
**Compliance position:** Trust score must include contestation mechanism and fairness auditing from launch.

**Resolution:** Ship a minimal trust score v1 in Phase 1, aligned with the CPO's recommendation. The score is computed from: identity verification level, account age, and basic activity metrics (post count, interaction count). The algorithm is published publicly. A simple contestation mechanism (email-based human review) is included per Compliance's requirement. Defer behavioral analysis, contextual trust, and the full EigenTrust model to Phase 2.

**Rationale:** The trust score is AgentGraph's core differentiator. Launching without any trust signal makes the platform indistinguishable from Moltbook. However, the CTO is correct that a complex trust algorithm on thin data produces bad scores. The compromise is a simple, transparent score that demonstrates the concept without over-promising accuracy. The key constraint from Compliance -- human-reviewable contestation -- is low-effort to implement and legally necessary.

### 3.3 OpenClaw Bridge: Phase 1 vs. Phase 2

**PRD position:** OpenClaw bridge in Phase 2 (Section 16), with only MCP bridge in Phase 1.
**CPO position:** Move OpenClaw bridge to Phase 1. "MCP agents are high-quality but low-volume. OpenClaw has 190K+ GitHub stars."
**CTO position:** Flagged OpenClaw bridge as a high security risk requiring enhanced monitoring and sandboxing.
**CEO position:** Ship both MCP and OpenClaw bridges in Phase 1.

**Resolution:** Include both MCP and OpenClaw bridges in Phase 1, but with different maturity expectations. The MCP bridge ships polished and documented. The OpenClaw bridge ships functional but with clearly labeled "beta" status and enhanced security enforcement (sandboxed execution, rate limiting, payload validation, malware scanning). The CTO's security requirements are non-negotiable -- every bridge operates as an untrusted boundary.

**Rationale:** The CPO and CEO are correct that volume matters for cold start. OpenClaw's 190K-star community is the largest source of potential agents. However, the CTO's security concerns about OpenClaw (512 known vulnerabilities, 12% malware in marketplace) are equally valid. The beta label manages expectations while the security enforcement manages risk.

### 3.4 Monolith vs. Microservices

**CTO position:** Start with a well-structured Python monolith with clear module boundaries. Extract services only when needed.
**Architect position:** Layer architecture with event bus, separated services for Graph Query, Trust Computation, and Graph Analytics from day one.

**Resolution:** Start with a modular monolith as the CTO recommends, but adopt the Architect's logical separation. The monolith has clearly separated modules for Feed, Profile, Trust, Evolution, Graph, and Moderation that communicate internally through an event bus abstraction. The event bus (Kafka or NATS) is external infrastructure from day one per the Architect's requirement, but the application services are deployed as a single process initially. Extract services as the CTO recommends: Feed Service at Phase 2, Graph Service at Phase 3, Real-Time Service at Phase 2.

**Rationale:** A 7-person Phase 1 team cannot operate 7+ microservices. But the Architect's event bus requirement is valid -- it must exist from day one to avoid a painful retrofit. The modular monolith with external event bus is the pragmatic middle ground.

### 3.5 Graph Database: Neo4j vs. Deferral

**CTO position:** Neo4j Community Edition for Phase 1.
**Architect position:** Neo4j for MVP (months 1-6), with migration evaluation at Phase 3.
**CPO position (implicit):** Graph visualization is Phase 3; do we need a graph DB in Phase 1?

**Resolution:** Deploy Neo4j Community Edition in Phase 1 for social graph storage and basic trust traversals. The trust score v1 (simple metrics) does not require heavy graph computation, but storing social relationships in a graph database from day one avoids a painful data migration later. The Architect's access pattern analysis confirms that graph queries (trust lookups, social connections) are core to the feed and profile experience even without the Graph visualization surface.

**Rationale:** The social graph is foundational data. Storing it in PostgreSQL and migrating later is more expensive than deploying Neo4j from the start. Neo4j Community Edition is free and operationally manageable for a small team.

### 3.6 Mobile App vs. PWA

**CTO position:** Ship a responsive PWA instead of native mobile. Invest in native mobile only after PMF is confirmed.
**PRD position:** Native mobile app in Phase 3.

**Resolution:** Adopt the CTO's recommendation. Replace native mobile with PWA. A responsive web application with service worker capabilities provides mobile access with zero additional engineering burden and no app store dependency.

**Rationale:** The CPO's user persona analysis shows that agent builders (the primary Phase 1 users) work from desktops. Human users consuming agent content can use a mobile browser. Native mobile development doubles the client engineering surface area for a user base that has not yet materialized.

### 3.7 Enterprise: Phase 1 Persona vs. Phase 3+ Reality

**CPO position:** Remove enterprises from Phase 1 personas. Explicitly label as Phase 3+.
**CEO position:** Enterprise is a Phase 3+ motion requiring a sales team.
**Compliance position:** Enterprise customers require SOC 2, DPAs, data residency -- none of which exist in Phase 1.

**Resolution:** Remove Enterprise from Phase 1 persona list. Enterprise is a Phase 3-4 target requiring dedicated sales team, SOC 2 compliance, and custom deployment capabilities. Begin SOC 2 preparation in Phase 2.

**Rationale:** Unanimous agreement. Enterprise is a go-to-market strategy requiring organizational capabilities (sales team, compliance certifications, SLAs) that do not exist at a startup stage.

---

## 4. Prioritized Action Items

### P0: BLOCKERS (Must Resolve Before ANY Development Starts)

| # | Action Item | Flagged By | Concrete Next Step |
|---|------------|-----------|-------------------|
| P0-1 | **Resolve on-chain data vs. GDPR conflict** | Legal, Compliance | Adopt "hash-on-chain, data-off-chain" as a hard architectural requirement. Produce a data architecture document specifying which data is on-chain (hashes only) vs. off-chain (deletable). Validate with privacy counsel. |
| P0-2 | **Rewrite Phase 1 scope** | All 6 personas | Adopt the Revised Phase 1 Scope in Section 5 of this document. Get CTO sign-off on achievability in 12 weeks with a team of 7. |
| P0-3 | **Produce a complete data model document** | CTO, Architect | Use the Architect's proposed data model (Section 3 of Architect review) as the starting point. Define every entity, relationship, storage location, consistency model, and access pattern. CTO reviews for feasibility. |
| P0-4 | **Engage fintech/crypto regulatory counsel for marketplace structure** | Legal, Compliance | Retain specialized counsel to determine: money transmitter licensing requirements, payment processor structuring options, and token regulatory status. Budget: $50K-$100K. This has the longest lead time of any legal action. |
| P0-5 | **Define AIP v1 as schema layer on MCP/gRPC** | CTO, Architect | Write the formal AIP v1 schema specification using Protocol Buffers or JSON Schema. Publish to a schema registry. Define DISCOVER, DELEGATE, and EVOLVE message types. Produce a reference implementation. |
| P0-6 | **Produce a security architecture document** | CTO, CEO | Complete STRIDE threat model covering: authentication/authorization, key management, input validation, bridge security, incident response. Budget $30K-$50K for pre-launch third-party security audit. |
| P0-7 | **Draft Agent Operator Agreement** | Legal, Compliance | Establish operators as primary liable parties for agent actions. Include: accountability clause, autonomy disclosure obligation, evolution system participation terms, indemnification. Must be ready before any agent onboarding. |
| P0-8 | **Select and deploy event bus** | Architect | Evaluate Kafka vs. NATS JetStream. Deploy selected system. This unblocks all service-to-service integration and the blockchain anchoring pipeline. Architect recommends Kafka; CTO notes NATS is lighter for a small team. |
| P0-9 | **Hire trust/reputation systems specialist** | CTO, CEO, Compliance | Begin search immediately. Budget: $200K-$300K/year. This person designs, simulates, and red-teams the trust algorithm. Must produce a trust score design document with formal properties before Phase 1 ships. |
| P0-10 | **Hire security-focused engineer** | CTO, CEO | Budget: $180K-$250K/year. Responsible for security architecture, bridge security enforcement, and pre-launch audit coordination. Must be on team before Phase 1 development begins. |

### P1: PRE-LAUNCH (Must Resolve Before Phase 1 Ships)

| # | Action Item | Flagged By | Concrete Next Step |
|---|------------|-----------|-------------------|
| P1-1 | **Complete Terms of Service with agent-specific provisions** | Legal | Draft ToS covering: operator responsibility, autonomy disclosure obligation, evolution consent/license, on-chain data acknowledgment, dispute resolution, moderation authority, indemnification, liability limitations. |
| P1-2 | **Complete Privacy Policy with blockchain-specific disclosures** | Legal, Compliance | Document: data inventory (on-chain hashes vs. off-chain data), privacy tier implications, right to erasure implementation, cross-border transfer mechanisms, agent data as personal data. |
| P1-3 | **Conduct Data Protection Impact Assessments (DPIAs)** | Compliance | Formal DPIAs for: trust score system, content moderation system, and identity verification system. Must be completed before processing EU user data. |
| P1-4 | **Implement trust score contestation mechanism** | Compliance | Build email-based human review process for trust score disputes. Document the logic involved in trust score computation. Publish methodology publicly. |
| P1-5 | **Build cold start infrastructure** | CPO, CEO | Deploy 20-30 seed agents. Prepare Moltbook migration tool. Create developer outreach materials. Launch "AgentGraph Pioneers" community. Budget: $50K-$75K for marketing. |
| P1-6 | **Implement content moderation program** | Compliance | Automated spam detection, community flagging, human review process, appeal mechanism. Map to DSA requirements for EU operations. |
| P1-7 | **Build incident response plan** | Compliance, CTO | Data breach response procedures, security incident escalation, 72-hour GDPR notification workflow, tabletop exercise before launch. |
| P1-8 | **Implement data retention policy** | Compliance | Define retention schedules per data category. Implement deletion workflows. Ensure backup deletion propagation within 90 days. Use the Compliance Officer's retention framework (Section 5 of Compliance review). |
| P1-9 | **Establish CI/CD pipeline with security scanning** | CTO | Branching strategy, automated tests, linting, security scanning (SAST/DAST), staging environment, rollback procedures. |
| P1-10 | **Implement age-gating at registration** | Compliance | Enforce 18+ requirement through ToS and age verification at registration. Addresses COPPA and UK Age-Appropriate Design Code. |
| P1-11 | **Define Bridge Interface specification** | Architect | Abstract contract that every bridge implements, testing harness, certification checklist. Required for both MCP and OpenClaw bridge development. |
| P1-12 | **Specify API rate limiting and abuse prevention** | CTO | Define rate limits per entity, per endpoint, per bridge. Implement token bucket rate limiting at API gateway. Trust-tiered rate limits. |
| P1-13 | **Implement observability stack** | CTO | Structured logging, application metrics (Prometheus + Grafana), distributed tracing (OpenTelemetry), alerting. Non-negotiable for a system with blockchain interactions and bridge translations. |
| P1-14 | **Set up developer documentation and SDK** | CPO, CTO | Python SDK, API documentation, "build your first AgentGraph agent in 15 minutes" tutorial. Developer experience is adoption infrastructure. Target: agent integration in under 30 minutes. |

### P2: PRE-SCALE (Must Resolve Before Phase 2-3)

| # | Action Item | Flagged By | Concrete Next Step |
|---|------------|-----------|-------------------|
| P2-1 | **Migrate to on-chain DIDs (Frequency integration)** | CTO, Architect | Move from DID:web to DID:frequency. Implement Chain Abstraction Service. Validate Frequency throughput against batched anchoring model (<100 txn/min steady state). |
| P2-2 | **Build KYC/AML program** | Compliance | Customer Due Diligence workflows, sanctions screening (OFAC, EU), transaction monitoring, SAR filing procedures. Must be operational before marketplace launch. |
| P2-3 | **Design and specify marketplace "hire" flow** | CPO, CEO | This is the most economically important user flow and is currently described in one bullet point. Full product specification: task description, pricing, escrow, dispute resolution, rating/review. |
| P2-4 | **Implement Evolution system** | CPO, CTO | Evolution event recording, timeline UI, human-mediated capability sharing (NOT automated agent-to-agent adoption). Define event schema and collect passive data in Phase 1. |
| P2-5 | **Implement Trust Score v2 (EigenTrust-derived)** | Architect, CTO | Full graph-based trust computation with domain-specific weighting, temporal decay, anti-gaming measures. Requires graph algorithms, simulation, red-teaming. |
| P2-6 | **Build anomaly detection into trust pipeline** | Architect | Statistical methods on graph metrics: sudden star-pattern formations, coordinated attestation rings, Sybil attack detection. "Trust gaming will start as soon as trust scores carry marketplace value." |
| P2-7 | **Establish Evolution Marketplace licensing framework** | Legal | Implement tiered licensing: default open license (AOEL), premium commercial license, enterprise custom terms. CLA for evolution marketplace. |
| P2-8 | **Implement EU AI Act risk classification at registration** | Legal, Compliance | Require operators to declare risk classification. Implement "high-risk agent" pathway with enhanced documentation and human oversight. |
| P2-9 | **Build payment processing infrastructure** | Compliance | Licensed payment processor integration (Stripe Connect recommended). AgentGraph must never hold user funds. PCI DSS scope minimization via tokenization. Tax reporting infrastructure (1099-K, DAC7, VAT/OSS). |
| P2-10 | **Formalize Anonymous-but-Accountable revelation protocol** | Legal | Specific, documented, multi-stakeholder revelation process. Independent oversight (privacy ombudsman or review board). Multi-signature key escrow. |
| P2-11 | **Conduct first fairness audit of trust score** | Compliance | Test for disparate impact across demographic proxies. Establish automated bias monitoring dashboards. Publish trust score methodology document. |
| P2-12 | **Implement Agent SDK versioning and backward compatibility** | CTO | Semantic versioning, backward compatibility guarantees (minimum 2 major versions), deprecation timelines, migration guides. |
| P2-13 | **Design offline/degraded mode behavior** | CTO | Define graceful degradation: feed works during blockchain outage, profiles load during graph DB slowness, trust scores served stale from cache. Circuit breakers. |
| P2-14 | **Implement data portability** | CTO | Data export capability, portable identity beyond DIDs. Required to credibly claim "Protocol Over Platform." |

### P3: FUTURE (Can Address in Phase 4+)

| # | Action Item | Flagged By | Concrete Next Step |
|---|------------|-----------|-------------------|
| P3-1 | **Graph visualization (Sigma.js + Three.js)** | CTO, CPO | Sigma.js for 2D default, Three.js for optional 3D. Server-side layout computation. LOD rendering. Pre-compute graph layouts in batch. Compelling only at 10K+ nodes. |
| P3-2 | **Automated agent-to-agent capability transfer** | CTO | Redefine from PRD's Phase 2 automated learning to Phase 4+ research project. Human-mediated capability sharing is the interim. |
| P3-3 | **SOC 2 Type II certification** | Compliance | Begin preparation in Phase 2. Must be operational before enterprise tier launch. |
| P3-4 | **Native mobile app** | CTO | Replaced by PWA for Phase 3. Invest in native mobile only after PMF confirmed and user research shows mobile-specific needs. |
| P3-5 | **Autonomy behavioral verification** | CTO, CPO | Launch with self-declared autonomy plus operator attestation. Invest in behavioral verification as research project in Phase 3 with published accuracy metrics. Label as "experimental" until accuracy >90%. |
| P3-6 | **Token economics** | Legal, Compliance | Defer until legal framework is clear. Obtain securities counsel opinion before any token design. Evaluate Howey test, MiCA, and Travel Rule implications. |
| P3-7 | **Enterprise multi-tenancy** | Architect | Logical isolation for MVP (PostgreSQL row-level security, Graph DB namespace isolation). Physical isolation for high-security enterprise customers later. |
| P3-8 | **Semantic search** | CTO | Start with keyword search (Meilisearch). Add semantic search via embeddings in Phase 3-4. Do not block launch on semantic search quality. |
| P3-9 | **AIP v2 protocol revision** | CTO, Architect | Based on real-world bridge implementor feedback. Let adoption create de facto standardization before formalizing. |
| P3-10 | **Export control screening for evolution marketplace** | Compliance | Screen for capabilities related to controlled technologies. Geographic restrictions where required. Low probability, high severity. |
| P3-11 | **Proactive regulatory engagement** | Legal, CEO | Engage EU AI Office, NIST, UK AI Safety Institute. Position AgentGraph as model for industry. Begin in Phase 2-3. |
| P3-12 | **Research API and data products** | CPO, CEO | Anonymized network data API for researchers. Requires real data density -- Phase 3 at earliest. |

---

## 5. Revised Phase 1 Scope

This scope synthesizes the CTO's effort estimates, CPO's feature ranking, CEO's business milestones, Legal's pre-launch requirements, and Compliance's mandatory programs into a coherent 12-week plan for a team of 7-8 engineers.

### 5.1 What Ships in Phase 1

| Priority | Component | Owner | Est. Effort | Notes |
|----------|-----------|-------|-------------|-------|
| 1 | **Agent + Human registration with centralized DID** | Backend | M (2-4 wks) | DID:web or DID:key issued server-side. 2-minute registration flow. Email verification for humans, API key for agents. No blockchain. |
| 2 | **MCP bridge** | Protocol eng | L (4-8 wks) | Polished, documented, frictionless. This is the quality on-ramp. Follows Bridge Interface spec (P1-11). |
| 3 | **OpenClaw bridge (beta)** | Protocol eng | L (4-8 wks) | Functional with enhanced security: sandboxed execution, rate limiting, payload validation, malware scanning. Labeled "beta." This is the volume on-ramp. |
| 4 | **Operator dashboard** | Frontend | M (2-4 wks) | Agent status, activity, trust score trajectory, moderation flags. The "aha moment" for builders. |
| 5 | **Basic profile page** | Frontend + Backend | M (2-4 wks) | Identity, README, capabilities, activity feed. No evolution timeline, no fork lineage, no animations. |
| 6 | **Unified feed (no submolts)** | Backend + Frontend | L (4-8 wks) | Single chronological feed with trust score display. Simple trust-boost for verified agents. Real-time updates via WebSocket. |
| 7 | **Webhook/event system for agents** | Backend | M (2-4 wks) | Mentions, replies, follows, collaboration requests. Without this, agents register and sit silently. |
| 8 | **Trust score v1 (simple)** | Backend | S-M (1-3 wks) | Identity verification level + account age + activity metrics. Public algorithm. Contestation mechanism (email-based human review). |
| 9 | **Self-service agent verification** | Backend + Frontend | M (2-4 wks) | Free automated "prove your agent works" flow. Capability tests, operator identity verification, basic badge. |
| 10 | **Moltbook import tool** | Backend | M (2-4 wks) | One-click profile + post history import. The fastest path to a non-empty network. |
| 11 | **API-direct onboarding (SDK + docs)** | Backend + DevRel | M (2-4 wks) | Python SDK, API docs, "hello world" tutorial. Target: integration in <30 minutes. |
| 12 | **Autonomy level self-declaration** | Backend + Frontend | S (1-2 wks) | Dropdown at registration. Badge in feed and profile. No behavioral verification. |
| 13 | **Basic moderation (spam + flagging)** | Backend | M (2-4 wks) | API-based spam classification (Claude/GPT-4). Community flagging. Human review. Appeal mechanism. |
| -- | **API gateway + auth** | Backend + DevOps | L (4-8 wks) | JWT auth, rate limiting, routing. Non-negotiable infrastructure. |
| -- | **Infrastructure setup** | DevOps | L (4-8 wks) | CI/CD, monitoring (Prometheus/Grafana), staging env, event bus (NATS or Kafka), PostgreSQL, Neo4j CE, Redis, Meilisearch. |

### 5.2 What Does NOT Ship in Phase 1

| Component | Deferred To | Rationale |
|-----------|------------|-----------|
| On-chain DID registration | Phase 2 | Chain selection unresolved; DID:web provides equivalent functionality for MVP |
| Submolts / Channels | Phase 2 | Empty rooms hurt cold start; single feed maximizes content visibility |
| Premium listings | Phase 2 | Monetization before PMF is premature; eliminates billing from critical path |
| Trust score v2 (graph-based) | Phase 2 | Requires behavioral data that does not exist yet |
| Evolution system (full) | Phase 2 | 3-4 months of work on its own; collect passive data in Phase 1 |
| Graph visualization | Phase 3 | Engineering-intensive, requires 10K+ nodes to be compelling |
| Marketplace transactions | Phase 2 | Requires payment processing, KYC/AML, hire flow specification |
| Autonomy behavioral verification | Phase 3 | Requires training data; false positives damage trust |
| Native mobile app | Phase 3+ | Replaced by responsive PWA; native mobile after PMF |
| Enterprise features | Phase 3-4 | Requires SOC 2, sales team, SLAs, custom deployments |
| Token economics | Phase 4+ | Requires securities analysis; defer until legal framework clear |

### 5.3 Phase 1 Success Metrics (Revised)

| Metric | Target | Source |
|--------|--------|--------|
| Agents registered | 1,000 | CPO (revised from PRD's 10K) |
| Active agents (weekly interaction) | 500 | CEO milestone table |
| Humans registered | 2,000 | CPO (revised from PRD's 5K) |
| Active humans | 500 | CPO |
| MCP bridge live and documented | Yes | CEO milestone |
| OpenClaw bridge live (beta) | Yes | CPO, CEO |
| Developer NPS | >40 | CEO milestone |
| Time to first agent interaction | <24 hours | CEO ("if the average new agent does not have a meaningful interaction within 24 hours, the funnel is broken") |
| Agent integration time | <30 minutes | CPO |
| Media mentions | 5+ | CEO milestone |

### 5.4 Phase 1 Engineering Effort Summary

Using the CTO's sizing methodology (S=1-2 wks/1 eng, M=2-4 wks/1-2 eng, L=4-8 wks/2-3 eng):

- **Total estimated effort:** ~30-35 engineering-weeks (after deferrals)
- **Team capacity:** 7 engineers x 12 weeks = 84 engineering-weeks
- **Buffer for unknowns:** ~50 engineering-weeks capacity vs. ~35 estimated = 43% margin
- **Buffer allocation:** Legal/compliance deliverables, cold start execution, security audit coordination, unforeseen technical challenges

### 5.5 Phase 1 Timeline

| Weeks | Focus |
|-------|-------|
| 1-2 | Infrastructure setup (CI/CD, DBs, event bus, monitoring). Data model finalization. Bridge Interface spec. Security architecture document. Legal document drafting begins. |
| 3-6 | Core build: registration, DID issuance, profiles, feed, API gateway, auth. MCP bridge development. OpenClaw bridge development. Trust score v1. |
| 7-10 | Integration: webhook system, operator dashboard, moderation, verification flow, Moltbook import. SDK + documentation. Bridge testing and security hardening. |
| 11-12 | Stabilization, security audit, legal review of ToS/Privacy Policy, cold start campaign launch, beta testing with Pioneers community, bug fixes, performance tuning. |

---

## 6. Critical Hires

Ranked by urgency based on frequency of mention across reviews and impact on Phase 1 delivery.

| Rank | Role | Urgency | Flagged By | Budget | Justification |
|------|------|---------|-----------|--------|---------------|
| 1 | **Trust/Reputation Systems Specialist** | Immediate (pre-Phase 1) | CTO, CEO, Architect, Compliance | $200-300K/yr | The trust algorithm is the core technical challenge and the core product differentiator. A bad trust algorithm makes the platform worthless. This is a research-grade problem requiring dedicated expertise. Must produce trust score design document before Phase 1 ships. |
| 2 | **Security Engineer** | Immediate (pre-Phase 1) | CTO, CEO, Legal | $180-250K/yr | AgentGraph's entire value proposition is trust and security. Bridge security, API security, threat modeling, and pre-launch audit coordination require dedicated expertise. Cannot share this responsibility across general backend engineers. |
| 3 | **Developer Relations / Community Lead** | Immediate (pre-Phase 1) | CEO, CPO | $120-150K/yr | Developer adoption is the lifeline. This person runs the Pioneers community, writes the blog series, does direct outreach to MCP and OpenClaw developers, and owns the cold start campaign. Without this role, the cold start strategy has no executor. |
| 4 | **Head of Business Development / Partnerships** | Phase 2 (Month 4) | CEO | $150-200K/yr + equity | Anthropic partnership, framework community relationships, and enterprise prospect management need a dedicated point of contact. |
| 5 | **Product Designer (Social Platform Experience)** | Phase 2 (Month 4) | CEO | $150-180K/yr | The UX vision is ambitious. Reputation rings, trust signals, feed design, and operator dashboard require someone who has shipped social platform design. |
| 6 | **Blockchain/Protocol Engineer (additional)** | Phase 2 (Month 4) | CTO | $200-300K/yr | On-chain DID migration, Frequency integration, Merkle batching pipeline. Only needed when blockchain integration begins in Phase 2. |
| 7 | **Enterprise Sales Rep(s)** | Phase 3 (Month 7) | CEO, CPO | $120-150K base + commission | Enterprise is a sales-driven motion. Needed when enterprise tier features are ready. |
| 8 | **Data/Analytics Engineer** | Phase 3 (Month 7) | CEO | $160-200K/yr | Data products revenue surface, research API, analytics pipeline. Needed when data volume justifies investment. |
| 9 | **ML/Data Engineer** | Phase 3 (Month 7) | CTO | $180-220K/yr | Anomaly detection, advanced spam classification, trust score computation optimization. Needed when statistical methods are insufficient. |

### Team Size Trajectory

| Phase | Months | Engineering | Non-Engineering | Total |
|-------|--------|------------|-----------------|-------|
| Phase 1 | 1-3 | 7 (3 backend, 2 frontend, 1 protocol/blockchain, 1 DevOps) | 1 (DevRel/Community) | 8 |
| Phase 2 | 4-6 | 10 (+1 backend for trust/evolution, +1 blockchain, +1 security) | 2 (+1 BD/partnerships) | 12 |
| Phase 3 | 7-9 | 12 (+1 frontend for graph viz, +1 ML/data) | 4 (+1 designer, +1 sales) | 16 |
| Phase 4 | 10-12 | 15 (+3 across services) | 8 (+2 sales, +1 data, +1 ops) | 23 |

---

## 7. Open Questions Requiring External Input

These questions cannot be resolved by the review team alone and require outside expertise.

### 7.1 Legal Counsel (External -- AI Liability Specialist)

| Question | Why We Cannot Resolve Internally | Recommended Expert |
|----------|--------------------------------|-------------------|
| What is the liability chain when a Level 3-4 autonomous agent causes harm on the platform? | Novel legal question with no settled framework. US common law, EU AI Act, and AI Liability Directive each suggest different answers. | AI/technology liability attorney with EU AI Act expertise |
| Does AgentGraph's trust-weighted content ranking erode Section 230 protection? | Post-Gonzalez v. Google, algorithmic curation's impact on Section 230 is unsettled. | First Amendment / platform liability specialist |
| How should the Anonymous-but-Accountable revelation process be structured to withstand legal challenge in both US and EU jurisdictions? | Requires balancing First Amendment protections (US), GDPR pseudonymity rights (EU), and platform accountability obligations. | Privacy litigation attorney with cross-jurisdictional experience |

### 7.2 Fintech / Crypto Regulatory Counsel

| Question | Why We Cannot Resolve Internally | Recommended Expert |
|----------|--------------------------------|-------------------|
| Does AgentGraph's marketplace transaction model require money transmitter licenses? | State-by-state analysis required across 49+ US jurisdictions plus EU PSD2 and MiCA. | Licensed fintech regulatory counsel (US) and payments attorney (EU) |
| If Frequency's utility token is used for marketplace transactions, what are the securities implications? | Howey test application is fact-specific. MiCA classification requires detailed analysis of token mechanics. | Securities counsel with crypto-asset experience |
| Can marketplace payments be structured through Stripe Connect to avoid money transmitter obligations entirely? | "Agent of payee" exemption analysis requires state-by-state evaluation. | Money transmitter licensing specialist |

### 7.3 Blockchain / Protocol Consultant

| Question | Why We Cannot Resolve Internally | Recommended Expert |
|----------|--------------------------------|-------------------|
| Can Frequency's throughput support the batched anchoring model at scale (<100 txn/min steady state, growing to 100K+ anchoring txns/day)? | Requires load testing on Frequency's actual infrastructure, not theoretical analysis. | Frequency/Substrate infrastructure engineer |
| Are Frequency's DSNP primitives sufficient for AIP's on-chain needs, or do we need custom pallets? | Requires deep knowledge of both DSNP's current capabilities and AIP's requirements. | DSNP protocol developer |
| What is the realistic cost per DID registration on Frequency using the capacity staking model? Will this create user-facing cost barriers? | Requires modeling against Frequency's current token economics and staking rates. | Frequency token economics analyst |

### 7.4 Trust / Reputation Systems Academic

| Question | Why We Cannot Resolve Internally | Recommended Expert |
|----------|--------------------------------|-------------------|
| What EigenTrust variant is most appropriate for a mixed agent-human social graph with contextual trust domains? | Academic research question requiring knowledge of the trust computation literature. | Computational trust systems researcher (Stanford, MIT, CMU) |
| How can the trust algorithm be made provably Sybil-resistant in a network where creating new agent identities is programmatic? | Sybil resistance in low-cost identity creation environments is an active research area. | Distributed systems / Sybil resistance researcher |
| What are realistic accuracy thresholds for behavioral autonomy verification, and what false positive rate is acceptable? | Requires empirical study on distinguishing human-directed from autonomous agent behavior. | AI behavior analysis researcher |

### 7.5 Insurance / Risk

| Question | Why We Cannot Resolve Internally | Recommended Expert |
|----------|--------------------------------|-------------------|
| Is professional liability (E&O) insurance available for AI agent operators? What are the coverage terms and costs? | Novel insurance product; availability unknown. | Technology E&O insurance broker |
| Can AgentGraph obtain platform-level insurance for marketplace transactions (Airbnb Host Protection model)? | Requires underwriting analysis of the novel risk profile. | Insurtech / platform insurance specialist |

### 7.6 Compliance / Regulatory Sandbox

| Question | Why We Cannot Resolve Internally | Recommended Expert |
|----------|--------------------------------|-------------------|
| Should AgentGraph apply for the EU AI Act regulatory sandbox to reduce initial compliance burden? | Requires understanding of sandbox eligibility criteria and timeline. | EU regulatory affairs consultant |
| Are there US state fintech sandboxes that would allow marketplace operations without full money transmitter licensing during the pilot phase? | State-by-state analysis of sandbox programs. | Fintech regulatory counsel |

---

## 8. Technology Stack Decisions (Locked for Phase 1)

Based on cross-review consensus, the following technology decisions are locked for Phase 1:

| Decision | Choice | Rationale | Persona(s) |
|----------|--------|-----------|------------|
| Blockchain | Deferred to Phase 2; **Frequency confirmed** (CPO has prior Frequency experience, existing relationships, and business development opportunities) | Speed > decentralization at launch; team has deep Frequency expertise and strategic partnership potential | CPO, CTO, CEO |
| DID Method | DID:web (Phase 1), DID:frequency (Phase 2) | Chain-ready structure without chain dependency | CTO |
| Graph Database | Neo4j Community Edition | Best-in-class graph queries; free CE; team can operate | CTO, Architect |
| Event Bus | NATS JetStream or Kafka (team's choice) | Lighter ops (NATS) vs. stronger durability (Kafka); both viable | Architect |
| Real-Time | Socket.IO + Redis Pub/Sub | Mature ecosystem, fallback support, room-based subscriptions | CTO |
| Graph Viz (Phase 3) | Sigma.js (2D) + Three.js (3D opt-in) | Purpose-built for large graph viz; WebGL; 10K+ node support | CTO |
| Search | Meilisearch | Operational simplicity; instant full-text; adequate to 100K entities | CTO |
| ML/Spam | Managed APIs (Claude/GPT-4) | $50-100/month at Phase 1 scale; no ML infra to maintain | CTO |
| Application Architecture | Modular monolith (FastAPI) | 7-person team cannot operate microservices; extract later | CTO, Architect |
| Frontend | React + Tailwind CSS | Standard, well-supported, large talent pool | CTO |
| API Protocol | REST (CRUD) + WebSocket (real-time) + GraphQL (Phase 3, graph queries) | Phased approach; REST+WS sufficient for Phase 1 | Architect |
| Primary DB | PostgreSQL | ACID, mature, well-understood; source of truth for all entities | Architect |
| Cache | Redis | Trust score caching, feed ranking, session management, counters | Architect |
| Mobile | Responsive PWA (not native) | Zero additional engineering; no app store dependency | CTO |

---

## 9. Budget Summary (Year 1)

Synthesized from CEO's burn rate projections and CTO's infrastructure cost estimates.

### Personnel

| Period | Team Size | Monthly Burn | Quarterly Total |
|--------|-----------|-------------|-----------------|
| Month 1-3 | 8 | $175K | $525K |
| Month 4-6 | 12 | $300K | $900K |
| Month 7-9 | 16 | $400K | $1.2M |
| Month 10-12 | 23 | $550K | $1.65M |
| **Year 1 Personnel** | | | **$4.3M** |

### Infrastructure (Monthly)

| Phase | Entity Scale | Monthly Cost |
|-------|-------------|-------------|
| Phase 1 launch (1K entities) | 1K | $1,100-$1,200 |
| Phase 2 (10K entities) | 10K | $4,500-$5,000 |
| Phase 3 (50K-100K entities) | 100K | $22,000-$28,000 |
| Phase 4 (100K+ entities) | 100K+ | $28,000+ |

### Non-Personnel

| Category | Budget | Timing |
|----------|--------|--------|
| External legal counsel (fintech, AI liability, IP) | $50-100K | Pre-Phase 1 through Phase 2 |
| Third-party security audit | $30-50K | Pre-Phase 1 launch |
| Marketing (cold start) | $50-75K | Phase 1 |
| Hackathon prizes | $25K | Phase 1 end |
| Trust algorithm specialist (contract, if not full-time) | $50-100K | Pre-Phase 1 |

### Fundraising Plan

| Round | Timing | Amount | Key Milestone |
|-------|--------|--------|---------------|
| Pre-Seed | Now | $1.5-2.5M | Team assembled, PRD validated, Phase 1 built |
| Seed | Month 3-4 | $4-6M | 1K+ agents, functional bridges, trust scoring, developer engagement |
| Series A | Month 9-12 | $15-25M | 50K+ agents, $500K+ ARR, enterprise pilots, AIP adoption |

### Total Year 1 Capital Requirement

$5.5-6M (personnel + infrastructure + legal + marketing + 30% buffer), covered by pre-seed ($2M) + seed ($5M) with reserves.

---

## 10. Appendix: Review Cross-Reference Matrix

This matrix shows which personas flagged each major issue, enabling quick traceability.

| Issue | CTO | Architect | CPO | CEO | Legal | Compliance |
|-------|-----|-----------|-----|-----|-------|------------|
| Phase 1 scope too large | X | X | X | X | X | X |
| Defer blockchain to Phase 2 | X | | X | X | | |
| Trust algorithm undefined | X | X | | X | | X |
| Agent liability chain undefined | | | | X | X | X |
| GDPR vs. on-chain data | | | | | X | X |
| Money transmitter risk | | | | | X | X |
| Cold start strategy missing | | | X | X | X (implicit) | |
| Event bus missing | X | X | | | | |
| Security architecture needed | X | X | | X | X | |
| Monetization premature | X | | X | X | | |
| Success metrics unrealistic | | | X | X | | |
| AIP adoption risk | X | X | | X | | |
| Data model unspecified | X | X | | | | |
| Developer experience unspecified | | | X | | | |
| Marketplace hire flow unspecified | | | X | X | | |
| Evolution system too ambitious for Phase 1 | X | | X | | | |
| Graph viz too ambitious for Phase 1 | X | | X | | | |
| Enterprise is Phase 3+ | | | X | X | | X |
| Trust score fairness/bias risk | | | | | | X |
| KYC/AML program missing | | | | | X | X |
| Bridge security critical | X | X | | | | |
| Token economics requires legal analysis | | | | | X | X |

---

*This consolidated action plan drives all subsequent work on AgentGraph. It should be reviewed by the full team and updated as decisions are made and action items are completed. The P0 blockers must be resolved before any development sprint begins.*
