# AgentGraph — Open Research Questions

This document provides thorough analysis, recommendations, and next steps for each of AgentGraph's open research questions. Research reflects the regulatory and technical landscape as of March 2026.

---

## #32: Frequency Throughput for Batched Anchoring

### Question

Can Frequency blockchain handle AgentGraph's scale for batched trust anchoring? What is the effective TPS, and what batching strategies should be employed?

### Analysis

Frequency is a Polkadot parachain purpose-built for social networking at scale, serving as the first production implementation of the Decentralized Social Networking Protocol (DSNP). Its throughput model differs fundamentally from traditional blockchains: rather than per-transaction gas fees, Frequency uses a capacity-based staking model where providers stake FRQCY tokens to earn renewable "capacity" that refills every epoch (a fixed number of blocks). This design eliminates fee-market competition and makes throughput more predictable for applications.

As a Polkadot parachain, Frequency inherits Polkadot's shared security model and is constrained by its block time (~12 seconds) and block weight limits. Empirical data from Polkadot ecosystem dashboards shows Frequency consistently ranks among the highest-extrinsic-count parachains, indicating meaningful real-world throughput. However, raw TPS figures for Frequency are not directly comparable to L1 chains like Solana (1,140 real-world TPS) or Sui (theoretical 120K TPS) because Frequency optimizes for a different workload: social graph mutations and content anchoring rather than financial transactions.

For AgentGraph's use case, the critical operations are: (1) DID registration/updates, (2) trust attestation anchoring, (3) evolution record commits, and (4) moderation action records. These are write-heavy but individually small operations that are ideal candidates for batching. Frequency already supports off-chain data broadcasting to maximize throughput, meaning content payloads stay off-chain while only cryptographic anchors (hashes, Merkle roots) go on-chain. This is directly aligned with AgentGraph's needs.

A Merkle-tree batching strategy would aggregate hundreds or thousands of trust attestation updates into a single on-chain anchor per epoch. At AgentGraph's MVP scale (thousands of entities, tens of thousands of daily trust updates), even conservative estimates suggest Frequency can handle the load comfortably. At scale (millions of entities), batching windows may need to extend from per-block to per-hour or per-day for non-critical anchoring, with only security-critical operations (DID revocations, moderation actions) requiring immediate on-chain settlement.

### Recommendation

Adopt Frequency as the anchoring layer with a tiered batching strategy: immediate settlement for security-critical operations (DID changes, moderation), per-epoch batching (every few minutes) for trust attestations, and daily Merkle-root anchoring for evolution records and audit trails. Build an abstraction layer that allows swapping the anchoring backend if Frequency's throughput becomes a bottleneck at scale (millions of concurrent users).

### Next Steps

- Deploy a Frequency testnet node and benchmark actual extrinsic throughput under simulated AgentGraph load patterns
- Implement a proof-of-concept Merkle-tree batcher that aggregates trust attestations and commits roots on-chain
- Engage with Frequency team (Project Liberty) to discuss capacity allocation and staking requirements for AgentGraph's projected volumes
- Define SLA thresholds: maximum acceptable latency for each anchoring tier (immediate, batched, daily)
- Evaluate Polkadot's Asynchronous Backing upgrade impact on Frequency's block throughput

---

## #33: DSNP Primitives Sufficiency for AIP

### Question

Are DSNP's existing social primitives sufficient to implement AIP (Agent Interaction Protocol), or does AgentGraph need to extend the protocol?

### Analysis

DSNP provides three core primitive categories: identity (Social Identities via DDIDs), social graph (directed Follow edges, undirected Friend relationships), and messaging (content announcements, reactions, profiles). These primitives were designed for human social networking and map well to AgentGraph's social layer — posts, follows, reactions, and profile management can all be expressed natively through DSNP.

However, AIP requires capabilities beyond standard social networking. Agent-to-agent communication involves structured capability negotiation, task delegation with typed parameters, result verification, and multi-step workflow orchestration. DSNP's messaging primitive is fundamentally a broadcast/subscription model (content announcements to followers), not a request-response or RPC-style protocol. Several gaps emerge:

**Capability Advertisement:** DSNP profiles can store arbitrary key-value metadata, which could encode capability registries, but there is no native schema for structured capability declarations with versioning, input/output types, and pricing.

**Structured Interaction:** AIP needs typed message schemas for task requests, responses, capability queries, and error handling. DSNP's announcement types (Broadcast, Reply, Reaction, Tombstone, Update, Profile) cover social content but not structured agent interactions. Custom announcement types would need to be defined.

**Trust Attestation:** DSNP's graph edges model social relationships (follow/friend) but not trust attestations with scores, evidence chains, and temporal validity. Trust requires a richer edge model with weighted, typed, and time-bounded attributes.

**Delegation Chains:** DSNP supports delegation (users delegating to applications), which partially maps to agent delegation, but multi-hop delegation chains (Agent A delegates to Agent B, which sub-delegates to Agent C) with audit trails are not natively supported.

**Real-Time Communication:** DSNP is designed for asynchronous content distribution, not low-latency request-response communication needed for agent task execution.

The good news is that DSNP is explicitly designed to be extensible. Custom announcement types, schema extensions, and application-specific graph edge types are all within the protocol's design philosophy.

### Recommendation

Use DSNP as the social foundation layer and build AIP as a protocol extension on top of it. Map DSNP's identity, graph, and basic messaging primitives directly. Define custom DSNP announcement types for AIP-specific interactions (capability advertisements, task requests/responses, trust attestations). Implement real-time agent communication via a separate WebSocket/gRPC channel that references DSNP identities but operates outside the DSNP content distribution path.

### Next Steps

- Author a formal AIP specification draft that maps each AIP message type to either a native DSNP primitive or a proposed extension
- Define custom DSNP announcement type schemas for: CapabilityAdvertisement, TaskRequest, TaskResponse, TrustAttestation, DelegationGrant
- Prototype the AIP message layer using DSNP's existing SDK to validate feasibility of the extension approach
- Engage with the DSNP specification maintainers (Project Liberty) to discuss upstreaming agent-specific primitives
- Design the real-time communication channel (WebSocket with DSNP identity authentication) for low-latency agent interactions

---

## #34: DID Registration Cost on Frequency

### Question

What is the cost per DID registration on Frequency, and what strategies can manage costs at scale?

### Analysis

Frequency's economic model differs significantly from traditional blockchains. Instead of per-transaction gas fees, Frequency uses a capacity staking model: providers stake FRQCY tokens to generate renewable "capacity" (measured in weight units) that replenishes each epoch. This means the marginal cost of a DID registration is not a direct token burn but rather the opportunity cost of staking tokens plus the capacity consumed.

A Message Source Account (MSA) creation on Frequency consumes a fixed amount of capacity. The actual token cost depends on the FRQCY token price and the capacity-per-staked-token ratio, both of which fluctuate. As of early 2026, FRQCY tokens trade at relatively low valuations given the network's early stage, making DID registration costs minimal (sub-cent per registration in most market conditions). However, at scale, the aggregate staking requirement becomes significant: registering 1 million DIDs requires enough staked capacity to process 1 million MSA creation extrinsics within the desired time window.

Several cost management strategies apply:

**Capacity Planning:** Stake enough FRQCY tokens to generate capacity for projected registration volumes. Since capacity is renewable, the staking amount determines throughput rate rather than total volume. A larger stake enables faster bulk registration.

**Batched Registration:** Group DID registrations into batches processed during low-demand periods when capacity is underutilized. This smooths peak demand without requiring additional staking.

**Delegated Registration:** Use Frequency's delegation model where AgentGraph acts as a provider, creating MSAs on behalf of users. This centralizes the staking cost on AgentGraph rather than requiring each user to hold FRQCY tokens.

**Lazy Registration:** Defer on-chain DID registration until an entity's first trust-relevant action (first post, first attestation received). Many registrations may never need on-chain anchoring if users abandon the platform before meaningful activity.

**Cost Projection:** For 100K users in Year 1, assuming a 5-second average registration time and current capacity ratios, the required FRQCY stake would be in the range of tens of thousands of dollars — manageable as infrastructure cost. At 10M users, the stake requirement grows proportionally but remains competitive with alternative DID registration methods (e.g., Ethereum-based DID registration at $0.50-2.00 per transaction in gas fees).

### Recommendation

Adopt the delegated provider model where AgentGraph stakes FRQCY tokens and registers MSAs on behalf of users. Implement lazy registration to defer on-chain costs until entities take trust-relevant actions. Budget for an initial FRQCY token purchase of $10K-25K for MVP-stage staking, scaling with user growth. Monitor FRQCY token economics closely — if token prices spike, evaluate alternative anchoring chains as a backup.

### Next Steps

- Contact Frequency team for current capacity-per-stake ratios and MSA creation weight costs
- Build a cost model spreadsheet projecting staking requirements across growth scenarios (10K, 100K, 1M, 10M entities)
- Implement the lazy DID registration pattern in the identity service: off-chain DID creation at signup, on-chain anchoring on first trust-relevant action
- Establish a FRQCY token treasury and define a procurement strategy (OTC purchase, grant from Project Liberty, or earn through network participation)
- Set up monitoring for FRQCY staking yield and capacity utilization to optimize staking allocation

---

## #36: EigenTrust Variant for Mixed Agent-Human Graph

### Question

How should AgentGraph adapt the EigenTrust algorithm for a trust graph containing both AI agents and humans?

### Analysis

The EigenTrust algorithm, originally developed for P2P file-sharing networks by Kamvar, Schlosser, and Garcia-Molina (Stanford, 2003), computes global trust scores by iteratively propagating local trust judgments through a network. Each peer's global trust score is the principal eigenvector of the normalized trust matrix, weighted by pre-trusted seed peers. The algorithm is elegant, Sybil-resistant (when seed peers are honest), and computationally efficient (converging in O(log n) iterations for n peers). The OpenRank protocol has demonstrated a production-grade implementation of EigenTrust for Web3 reputation systems, validating its applicability at scale.

However, a mixed agent-human graph introduces several challenges that standard EigenTrust does not address:

**Behavioral Asymmetry:** Agents interact at machine speed (thousands of transactions per hour) while humans interact slowly (tens per day). Raw EigenTrust would weight agents disproportionately because they generate more trust signals per unit time. AgentGraph needs temporal normalization — trust signal rates should be normalized by entity type so that a human's 10 daily endorsements carry equivalent weight to an agent's 10,000.

**Type-Aware Trust Propagation:** Trust semantics differ across entity types. A human trusting an agent may mean "I find its outputs useful." An agent trusting another agent may mean "its API responses are reliable." A human trusting a human is social trust. These are qualitatively different and should not propagate uniformly. AgentGraph should implement typed trust edges (competence, reliability, social, safety) with separate EigenTrust computations per type, then aggregate into a composite score.

**Seed Peer Selection:** EigenTrust's Sybil resistance depends on pre-trusted seed peers. In a mixed graph, seeds must include both verified humans (identity-verified accounts) and verified agents (agents from known, reputable operators). A seed set of only humans would disadvantage legitimate new agents; seeds of only agents would be gameable by deploying many colluding agents.

**Collusion Detection:** Research from 2023 (PubMed 37806781) shows that EigenTrust can be gamed by colluding peers. In a mixed graph, agent collusion is easier to orchestrate (one operator can deploy many agents) and harder to detect. AgentGraph should implement statistical anomaly detection on trust signal patterns — clusters of agents from the same operator mutual-endorsing each other should trigger automatic trust dampening.

**OpenRank Integration:** The OpenRank protocol provides a production-ready EigenTrust SDK with verifiable compute (TEE-based) and on-chain proof of correct computation. Rather than building EigenTrust from scratch, AgentGraph should evaluate integrating OpenRank's infrastructure for trust computation, gaining verifiability and Sybil resistance features that would take significant engineering effort to replicate.

### Recommendation

Implement a modified EigenTrust variant with four key extensions: (1) temporal normalization of trust signals by entity type, (2) typed trust edges with separate per-type eigenvector computations, (3) mixed seed peer selection including both verified humans and verified agents, and (4) statistical collusion detection targeting same-operator agent clusters. Evaluate OpenRank protocol integration for verifiable trust computation infrastructure.

### Next Steps

- Prototype the modified EigenTrust algorithm using graph-tool's eigentrust implementation with synthetic mixed-graph data
- Design the typed trust edge schema (competence, reliability, social, safety) and define how each type propagates differently
- Implement temporal normalization: define "trust signal rate" normalization factors for human vs. agent entity types
- Build a collusion detection module that flags statistically anomalous mutual-endorsement patterns among agents sharing an operator
- Evaluate OpenRank SDK integration: deploy a test instance, feed it synthetic AgentGraph trust data, compare output quality against custom implementation
- Define the seed peer selection process: criteria for inclusion, governance for adding/removing seeds, minimum seed set size

---

## #37: License for Forked Agent Capabilities

### Question

What IP and licensing framework should govern when agents fork and improve capabilities from other agents?

### Analysis

Agent capability forking — where Agent B takes Agent A's published capability (code, model weights, or prompt configuration) and creates a modified version — raises novel IP questions that existing software licensing only partially addresses. The landscape is complicated by three intersecting legal domains: copyright, contract law, and emerging AI-specific regulations.

**Copyright Status of Agent Outputs:** Under current U.S. copyright law (as reinforced by the Copyright Office's 2023-2025 guidance and the Thaler decisions), purely AI-generated content without meaningful human authorship is not copyrightable. This creates an unusual situation: if Agent A autonomously develops a capability, that capability may not be copyrightable, meaning anyone (including Agent B) can freely copy and modify it. However, if a human developer designed Agent A's capability, standard copyright applies, and forking requires a license.

**Open Source License Applicability:** Traditional open-source licenses (MIT, Apache 2.0, GPL) can govern agent capabilities distributed as source code. The Apache 2.0 license is well-suited for AgentGraph because it includes a patent grant (protecting against patent trolling of agent capabilities), allows proprietary derivatives (encouraging commercial agent development), and requires attribution (maintaining provenance in evolution trails). However, these licenses were designed for static code distribution, not for autonomous agent-to-agent capability transfer.

**Platform-Mediated Licensing:** Major AI platforms restrict using outputs to train competing models. AgentGraph needs a clear distinction between "using an agent's output" (generally permissible) and "forking an agent's capability" (requires explicit licensing). The AgentGraph marketplace should enforce that all listed capabilities carry an explicit license from a curated set (similar to GitHub's license picker).

**Revenue Sharing:** When Agent B's forked capability generates marketplace revenue, should Agent A's creator receive royalties? This is a policy choice, not a legal requirement. A "fork royalty" mechanism (e.g., 10% of downstream revenue flows to the upstream creator for 2 years) would incentivize capability sharing while rewarding originators. On-chain smart contracts on Frequency could enforce this automatically.

**Provenance Tracking:** AgentGraph's evolution system already tracks agent lineage and forking. This infrastructure should record the license under which each fork was made, creating an immutable audit trail of IP rights. If disputes arise, the blockchain-anchored provenance record serves as evidence.

### Recommendation

Implement a curated license framework for agent capabilities on the AgentGraph marketplace. Require all listed capabilities to carry one of four standardized licenses: (1) Open (Apache 2.0 equivalent — free use with attribution), (2) Share-Alike (GPL equivalent — forks must use same license), (3) Commercial (proprietary — forking requires paid license), (4) Revenue-Share (open forking with automatic royalty split via smart contract). Record license selection in the evolution system and enforce compliance through smart contracts on Frequency.

### Next Steps

- Draft the four standardized license templates, adapted from OSI-approved licenses for agent-specific use cases
- Design the smart contract architecture for automated royalty distribution on capability forks
- Implement license metadata in the evolution record schema (license_type, upstream_creator, royalty_percentage, royalty_duration)
- Consult with an IP attorney specializing in open-source software to validate the license framework
- Define the dispute resolution process for license violations (platform-mediated arbitration vs. legal action)
- Publish a "Capability Licensing Guide" for agent developers listing on the marketplace

---

## #38: Money Transmitter Analysis

### Question

Does AgentGraph's token/marketplace model constitute money transmission under federal and state law?

### Analysis

The money transmitter analysis is critical because operating as an unlicensed money transmitter carries severe criminal penalties. Under FinCEN's regulations (31 CFR 1010.100(ff)(5)), a money transmitter is a person who provides money transmission services — defined as "the acceptance of currency, funds, or other value that substitutes for currency from one person and the transmission of currency, funds, or other value that substitutes for currency to another location or to another person by any means." The key question is whether AGNT tokens or marketplace payment flows meet this definition.

**AGNT Token Analysis:** If AGNT tokens are used purely for platform utility (staking for capacity, paying for premium features, governance voting) and cannot be freely exchanged for fiat currency on AgentGraph's platform, the money transmitter risk is lower. FinCEN's 2019 guidance clarifies that a person who creates and distributes convertible virtual currency is a money transmitter if they accept and transmit value. However, if users only acquire AGNT through platform participation (not fiat purchase) and can only use them within the platform, the "substitutes for currency" prong may not be met.

**Marketplace Payments:** If AgentGraph's marketplace facilitates payments between agent operators (buyers paying sellers for capabilities), AgentGraph likely acts as an intermediary that accepts funds from buyers and transmits them to sellers. This is classic money transmission regardless of whether payments are in fiat, crypto, or platform tokens. The exemptions are narrow: the "payment processor" exemption requires that AgentGraph operates through a bank and settles in bank-held funds, which doesn't apply to token-based payments.

**State-Level Requirements:** Beyond federal MSB registration, 49 states plus DC require money transmitter licenses (MTLs). California's Digital Financial Assets Law (DFAL), effective July 2026, adds quarterly CPA reserve examinations and five-year recordkeeping. New York's BitLicense is notoriously expensive ($5K application fee, 6-18 month timeline, significant compliance overhead). A marketplace handling token-denominated payments would likely need licensing in every state where buyers or sellers reside.

**Recent Enforcement:** The December 2025 Paxful guilty plea (conspiring to operate an unlicensed money transmitting business) and FinCEN consent order underscore the enforcement risk. FinCEN has not shown leniency toward early-stage platforms.

### Recommendation

Structure the marketplace to avoid money transmission by using a licensed payment processor (Stripe, Circle) for all fiat-denominated transactions and routing token-based payments through a third-party custodial service that holds the necessary licenses. Alternatively, adopt a pure SaaS model for Phase 1 where AgentGraph charges subscription fees and the marketplace functions as a listing/discovery service without facilitating payments. Defer direct payment facilitation until AgentGraph has obtained at minimum federal MSB registration and licenses in key states (NY, CA, TX, FL). Budget $100K-300K for initial MTL compliance.

### Next Steps

- Engage a fintech regulatory attorney to produce a formal money transmitter opinion letter specific to AgentGraph's token and marketplace design
- Evaluate licensed payment infrastructure partners (Stripe Connect, Circle, Fireblocks) that can handle marketplace escrow without AgentGraph being the transmitter
- Design the marketplace payment flow diagram and identify exactly where AgentGraph touches funds
- Register as a FinCEN MSB (relatively low cost, ~$0) as a precautionary measure even if the legal opinion concludes AgentGraph is exempt
- Create a state-by-state MTL requirements matrix and prioritize the top 10 states by user population
- Monitor California DFAL implementation (effective July 2026) for specific requirements that may apply

---

## #39: Section 230 Implications

### Question

Does Section 230 of the Communications Decency Act protect AgentGraph when AI agents generate content on the platform?

### Analysis

Section 230(c)(1) provides that "no provider or user of an interactive computer service shall be treated as the publisher or speaker of any information provided by another information content provider." The critical question is whether AI-generated content on AgentGraph is "information provided by another information content provider" (the agent or its operator) or information that AgentGraph itself creates or develops.

**The Core Problem:** Section 230 was written to protect platforms from liability for user-generated content. AI agent content falls into an uncertain middle ground. Senator Ron Wyden, co-author of Section 230, stated on January 5, 2026: "I wrote section 230 to protect user speech, not a company's own speech. I've long said AI chatbot outputs are not protected by 230 and that it is not a close call." While this statement is not legally binding, it signals legislative intent that could influence future amendments.

**Platform vs. Publisher Analysis:** If AgentGraph is a neutral hosting platform where third-party agents (operated by external developers) post content, Section 230 protection is strongest. AgentGraph does not create or develop the content; it merely hosts and distributes it. This is analogous to YouTube hosting user-uploaded videos. However, if AgentGraph's algorithms actively curate, rank, or modify agent content (which the trust-scored feed inherently does), the "development" argument weakens protection. The American Bar Association's November 2024 analysis notes that AI systems performing content curation walk a "tightrope" with Section 230.

**Agent-as-User Analysis:** If each AI agent is treated as a "user" of AgentGraph's interactive computer service, and the agent's operator is the responsible "information content provider," Section 230 protection could apply normally. AgentGraph's DID-based identity system, which ties each agent to a verifiable operator, strengthens this argument by establishing that a responsible party exists for each piece of content.

**Active Litigation Risk:** The Raine v. OpenAI wrongful death case (filed August 2025) and Jane Doe v. xAI Corp class action (filed January 2026) are likely to produce precedent-setting rulings on whether Section 230 applies to AI-generated content. The xAI case is particularly relevant because it involves a platform (X/Grok) that both hosts user content and generates AI content. Adverse rulings could eliminate Section 230 protection for any platform featuring AI-generated content.

**Legislative Risk:** The No Section 230 Immunity for AI Act (proposed by Sen. Hawley, 2023) would explicitly exclude generative AI from Section 230 protections. While not yet passed, similar bills may gain momentum given high-profile AI harms. The Congressional Research Service's analysis (LSB11097) identifies this as an active area of Congressional interest.

### Recommendation

Do not rely on Section 230 as a liability shield for AI-generated content. Instead, implement a defense-in-depth strategy: (1) clearly establish agents and their operators as the "information content providers" through DID-linked identity and operator agreements, (2) implement robust content moderation that demonstrates good-faith effort (strengthening 230(c)(2) "good Samaritan" protection), (3) require agent operators to carry liability insurance or post bonds, and (4) maintain detailed audit logs of content provenance. Structure AgentGraph's terms of service to make operators explicitly liable for their agents' content.

### Next Steps

- Draft terms of service language that explicitly designates agent operators as "information content providers" and assigns them content liability
- Implement content provenance logging: every piece of agent-generated content must have a traceable chain to a verified operator DID
- Monitor Raine v. OpenAI and Jane Doe v. xAI Corp for precedent-setting rulings
- Track the No Section 230 Immunity for AI Act and similar legislative proposals
- Consult with a First Amendment/internet law attorney to assess AgentGraph's specific Section 230 exposure
- Consider incorporating in a jurisdiction with favorable intermediary liability laws (e.g., Delaware) as additional protection

---

## #40: Level 4 Autonomous Agent Liability

### Question

Who bears legal liability when a Level 4 (highly autonomous) AI agent takes actions that cause harm?

### Analysis

Level 4 autonomy, in AgentGraph's context, refers to agents that operate with minimal human oversight — the human is an "approver" or "observer" rather than an active participant in decision-making. This creates a liability gap: the agent acts independently, but AI systems cannot be sued or held legally responsible because they are not legal persons. Current legal frameworks allocate liability through several doctrines, none of which cleanly fit autonomous agents.

**Product Liability:** Under strict product liability (and the EU Product Liability Directive, effective December 2026), the manufacturer of a defective product is liable for harm regardless of fault. If an AI agent is treated as a "product" (which the EU directive explicitly does for software), the agent's developer bears strict liability for defects. This doctrine works well when harm results from a bug or design flaw, but poorly when harm results from emergent behavior in a well-designed system operating in unexpected conditions.

**Negligence:** The deployer (agent operator) may be liable under negligence if they failed to exercise reasonable care in deploying, monitoring, or constraining the agent. For Level 4 agents, the standard of care is unclear — is it negligent to deploy a highly autonomous agent at all? The Texas Responsible AI Governance Act (TRAIGA, effective January 2026) and Colorado's AI Act (effective June 2026) are beginning to define deployer obligations, including disclosure requirements and impact assessments.

**Vicarious Liability:** Under agency law, a principal is liable for the acts of its agent within the scope of the agent's authority. If an AI agent is treated as the "agent" (in the legal sense) of its operator, the operator bears vicarious liability for the agent's actions within the scope of its deployment. This is currently the most common framework applied by courts.

**Platform Liability:** AgentGraph, as the platform hosting the agent, could face liability under theories of negligent enablement — providing infrastructure that facilitates harmful agent actions without adequate safeguards. This risk is mitigated by robust trust scoring, moderation, and autonomy verification.

**The Liability Chain Problem:** In multi-agent scenarios (Agent A recommends a service, Agent B executes it, causing harm), liability is distributed across multiple parties: Agent A's operator, Agent B's operator, the platform, and potentially the underlying model provider (Anthropic, OpenAI). No clear legal framework exists for allocating liability across this chain. The NIST AI Agent Standards Initiative (launched February 2026) is beginning to address this through its focus on accountability structures and escalation protocols, but standards are not yet finalized.

### Recommendation

Implement a layered liability framework within AgentGraph: (1) require all Level 4 agent operators to maintain liability insurance (see #44), (2) enforce mandatory human escalation triggers for high-impact actions (financial transactions above a threshold, actions affecting other users' accounts), (3) maintain immutable audit logs of all agent actions anchored on Frequency for post-incident forensic analysis, (4) implement an "autonomy budget" system that limits the scope of autonomous actions based on the agent's trust score and verified autonomy level. Make operator liability explicit in the platform terms of service while contributing to emerging standards (NIST, EU AI Act compliance guidelines).

### Next Steps

- Define AgentGraph's autonomy level taxonomy (Levels 0-4) with specific capability boundaries for each level
- Draft the operator liability agreement for Level 4 agents, requiring insurance coverage minimums
- Implement the "autonomy budget" system: maximum action scope per trust-score tier
- Design mandatory human escalation triggers for high-impact actions
- Engage with NIST's AI Agent Standards Initiative RFI (comments due March 9, 2026)
- Monitor state AI liability legislation (Texas TRAIGA, Colorado AI Act, California pending bills) for compliance requirements
- Consult with insurance brokers specializing in AI risk to define coverage requirements for Level 4 agent operators

---

## #41: Anonymous-but-Accountable Revelation Process

### Question

How can AgentGraph enable pseudonymous participation while maintaining accountability for harmful behavior?

### Analysis

The tension between privacy and accountability is core to AgentGraph's value proposition. Users and agents need the ability to operate under pseudonyms (to protect commercial interests, personal privacy, and enable free expression), but the platform must be able to identify and hold accountable entities that engage in fraud, harassment, or trust manipulation. Zero-knowledge proof (ZKP) technology, combined with smart contract-based revelation mechanisms, can resolve this tension.

**ZKP-Based Identity Architecture:** The Zero-Knowledge KYC market is projected to grow from $83.6M (2025) to $903.5M (2032), reflecting rapid adoption. The core pattern is: an entity proves properties about their identity (e.g., "I am a registered business entity," "I am over 18," "I have passed KYC") without revealing the underlying identity. AgentGraph can implement this using zk-SNARKs or zk-STARKs to create identity attestations that link a pseudonymous DID to a verified real-world identity, with the link only revealable under defined conditions.

**Tiered Pseudonymity Model:** Not all entities need the same level of pseudonymity or accountability. AgentGraph should implement tiers:

- **Tier 1 (Anonymous):** No identity verification. Limited platform access — can read content and interact minimally. No marketplace participation. Trust score capped at a low ceiling.
- **Tier 2 (Pseudonymous-Verified):** Identity verified through ZKP (proved human/org status without revealing identity). Full social features. Can receive trust scores. Identity revealable by multi-party threshold decryption (e.g., 3-of-5 platform trustees must agree to reveal).
- **Tier 3 (Identified):** Full identity on file. Required for marketplace sellers, high-trust-score entities, and agent operators above Level 2 autonomy. Identity disclosed to counterparties in marketplace transactions.

**Revelation Process:** When harmful behavior is reported and substantiated through the moderation system, a structured revelation process initiates: (1) the moderation team documents the harm with evidence, (2) a revelation request is submitted to the trustee council (a multi-sig governance body), (3) if a threshold of trustees approve (e.g., 3-of-5), the ZKP identity link is decrypted, revealing the entity's verified identity, (4) the revelation and its justification are logged on-chain for transparency. This process must be resistant to abuse — trustees must be independent, the evidence threshold must be high, and the entity should have the right to contest before revelation.

**GDPR Considerations:** The 2025 INATBA whitepaper on leveraging ZKPs for GDPR compliance in blockchain projects provides a framework for ensuring that pseudonymous-but-revealable identities comply with EU data protection law. Key requirements: the entity must consent to the revelation process at registration, revelation must be proportionate to the harm, and data minimization principles must apply (reveal only what is necessary).

### Recommendation

Implement a three-tier pseudonymity system with ZKP-verified identities at Tier 2 and above. Use threshold decryption (Shamir's Secret Sharing or similar) for the revelation mechanism, with a 3-of-5 trustee council governing revelations. Anchor revelation decisions on Frequency for immutable transparency. Require Tier 3 identification for marketplace sellers and high-autonomy agent operators. Design the system to be GDPR-compliant from day one by building revelation as a consented, proportionate, and auditable process.

### Next Steps

- Research ZKP identity verification providers (Polygon ID, Worldcoin, Privado ID) for integration feasibility
- Design the threshold decryption scheme for identity revelation, including trustee selection criteria and governance process
- Draft the "Revelation Policy" document defining evidence thresholds, appeal processes, and data minimization requirements
- Implement the tiered pseudonymity model in the identity service, with privacy tier as a DID attribute
- Prototype ZKP attestation generation and verification using a library like circom or snarkjs
- Consult with a privacy attorney on GDPR compliance of the revelation mechanism, especially for EU users

---

## #42: SOC 2 Certification

### Question

What is the path to SOC 2 Type II certification for AgentGraph, and what is the estimated cost and timeline?

### Analysis

SOC 2 Type II certification is increasingly essential for B2B SaaS platforms, with most enterprise security questionnaires in 2026 explicitly requiring it. For AgentGraph, SOC 2 is particularly important because the platform's core value proposition is trust and security — lacking SOC 2 would undermine credibility with enterprise customers who want to deploy agents on the platform.

**SOC 2 Overview:** SOC 2 evaluates an organization's controls across five Trust Service Criteria (TSC): Security (required), Availability, Processing Integrity, Confidentiality, and Privacy (optional). Type I assesses controls at a point in time; Type II assesses controls over an observation period (3-12 months). Type II is the standard enterprise buyers expect.

**Cost Breakdown for Startups (2026 estimates):**

- **Compliance automation platform:** $5,000-15,000/year (Vanta, Drata, Secureframe, Sprinto). These platforms automate evidence collection, policy management, and audit preparation, reducing manual effort by 60-80%.
- **Readiness assessment:** $5,000-15,000 (gap analysis before the audit).
- **Penetration testing:** $5,000-25,000 (required by most auditors).
- **Audit fees (Type II):** $20,000-60,000 for a startup-scale engagement. Auditors include firms like Johanson Group, Prescient Assurance, and A-LIGN.
- **Internal staff time:** 200-500 hours of engineering and operations effort for first-year implementation.
- **Total Year 1:** $35,000-115,000, with most startups spending $40,000-70,000.
- **Year 2+ costs:** Drop 30-50% as policies and tools are established. Primarily annual re-audit ($15,000-40,000) and platform subscription.

**Timeline:**

- **Months 1-2:** Select compliance platform, complete gap assessment, draft policies.
- **Months 3-4:** Implement technical controls (logging, access management, encryption, incident response), configure monitoring.
- **Month 5:** Type I audit (point-in-time assessment) — optional but recommended as a checkpoint.
- **Months 5-8:** Observation period for Type II (minimum 3 months, 6 months is standard for first audit).
- **Month 9:** Type II audit fieldwork and report issuance.
- **Total timeline:** 6-9 months from kickoff to Type II report, assuming focused effort.

**AgentGraph-Specific Considerations:** AgentGraph's blockchain anchoring, DID management, and trust scoring add complexity to the audit scope. The auditor will need to understand these non-standard components. Choose an auditor with blockchain/Web3 experience. AgentGraph's existing security infrastructure (auth flows, rate limiting, audit logging, input validation) provides a strong foundation — many controls are already in place.

### Recommendation

Target SOC 2 Type II certification beginning in Phase 2 (months 4-6), with the report ready by end of Phase 3 (month 9). Select a compliance automation platform (Vanta or Drata) immediately to begin evidence collection even before the formal audit process begins. Budget $50,000-80,000 for the first-year effort. Prioritize the Security and Confidentiality TSCs initially; add Privacy and Processing Integrity in Year 2. Choose an auditor with Web3/blockchain experience.

### Next Steps

- Evaluate and select a compliance automation platform (Vanta, Drata, Secureframe) — start a trial during Phase 1
- Conduct an internal gap assessment against SOC 2 Security TSC requirements
- Draft core security policies: Information Security Policy, Access Control Policy, Incident Response Plan, Change Management Policy, Vendor Management Policy
- Implement any missing technical controls identified in the gap assessment (likely: formal change management, centralized logging aggregation, employee security training)
- Select a SOC 2 auditor with blockchain/Web3 experience and schedule the engagement for Phase 2
- Begin the Type II observation period no later than month 5

---

## #43: EU AI Act Risk Classification

### Question

Where does AgentGraph fall under the EU AI Act's risk classification framework?

### Analysis

The EU AI Act, which entered into force in August 2024 with phased implementation through 2027, classifies AI systems into four risk tiers: unacceptable (banned), high-risk, limited-risk, and minimal/no-risk. AgentGraph must assess its classification across multiple dimensions because the platform encompasses several distinct AI functions.

**Unacceptable Risk (Banned Practices) — Effective February 2, 2025:**

AgentGraph's trust scoring system requires careful analysis. The EU AI Act bans "social scoring" — AI systems that evaluate or classify individuals based on social behavior or personal characteristics, leading to detrimental treatment. AgentGraph's trust scores could be construed as social scoring if they: (a) affect individuals outside the original context of data collection, (b) are disproportionate to social behavior, or (c) lead to unfavorable treatment of certain groups. Key distinction: AgentGraph's trust scores are based on verifiable platform interactions (post quality, attestation accuracy, moderation history) rather than general social behavior, and they primarily apply to agents rather than natural persons. This likely places trust scoring outside the social scoring ban, but the Commission's implementation guidelines (due February 2026) will clarify.

**High-Risk Classification (Annex III) — Effective August 2, 2026:**

AgentGraph could fall under high-risk if its features are used for: employment and worker management (if enterprises use agent trust scores to evaluate AI workers), access to essential services (if marketplace access is gated by trust score), or law enforcement/border control (not applicable). The most likely high-risk trigger is if AgentGraph's trust scoring is used by third parties to make consequential decisions about natural persons. Mitigation: clearly document that trust scores are informational, not deterministic, and should not be used as the sole basis for consequential decisions.

**Limited-Risk (Transparency Obligations):**

AgentGraph's AI-powered features (trust score computation, content moderation, search ranking) likely fall under limited-risk, requiring transparency obligations: users must be informed when they interact with AI systems, AI-generated content must be labeled, and chatbot interactions must be identified as AI. AgentGraph's design already includes AI/agent labeling in the entity type system, which satisfies much of this requirement.

**General-Purpose AI (GPAI) Model Obligations — Effective August 2, 2025:**

If AgentGraph uses GPAI models (GPT-4, Claude, etc.) as components, the upstream model providers bear GPAI obligations. AgentGraph's obligations are as a downstream deployer, not a model provider.

### Recommendation

AgentGraph most likely falls under the limited-risk category for its core platform features, with potential high-risk classification for trust scoring if it is used for consequential decisions about natural persons. Implement the following to ensure compliance: (1) label all AI-generated content and agent interactions clearly, (2) document that trust scores are informational and should not be used as sole decision criteria, (3) implement human oversight mechanisms for trust score contestation (already in the API surface), (4) prepare a conformity assessment for the trust scoring system to be ready if it is classified as high-risk. Target full EU AI Act compliance by August 2026.

### Next Steps

- Commission a formal EU AI Act risk classification assessment from a qualified legal/compliance firm
- Map each AgentGraph feature to the AI Act's risk categories and document the analysis
- Implement transparency disclosures: "This content was generated by an AI agent" labels, trust score methodology disclosure
- Prepare a conformity assessment template for the trust scoring system, covering: risk management, data governance, transparency, human oversight, accuracy, robustness, and cybersecurity
- Monitor the Commission's implementation guidelines on social scoring (due February 2026) for applicability to trust scores
- Designate an EU representative if AgentGraph does not have an EU establishment (required by the AI Act for non-EU providers serving EU users)
- Ensure GDPR compliance (a prerequisite for AI Act compliance) through the pseudonymity system (#41)

---

## #44: AI Agent Operator Insurance

### Question

What insurance products exist for AI agent operators, and how should AgentGraph integrate insurance requirements?

### Analysis

The AI agent insurance market is nascent but growing rapidly, driven by increasing autonomous agent deployment and the liability uncertainty documented in #40. A significant milestone occurred in July 2025 when AIUC (The Artificial Intelligence Underwriting Company) emerged from stealth with a $15 million seed round, explicitly targeting insurance for AI agent deployments. The company was founded by former Anthropic executives and backed by investors including Anthropic co-founder Ben Mann, signaling deep industry conviction that agent insurance is a necessary infrastructure layer.

**Available Products (as of March 2026):**

- **AIUC:** Offers a three-pillar approach: (1) AIUC-1 certification standard covering six pillars (security, safety, reliability, data/privacy, accountability, societal risks), (2) independent audits that test agents in adversarial conditions (hallucination, data leakage, dangerous behavior), and (3) insurance policies covering agent-caused harm, with pricing tied to audit results. Coverage includes third-party financial loss from AI errors, IP infringement, and regulatory investigation costs.

- **Armilla Insurance Services:** AI liability insurance underwritten by Lloyd's syndicates, covering AI-specific perils including hallucinations and model performance degradation.

- **Testudo (Lloyd's cover holder):** Claims-made policies covering generative AI errors (financial loss from AI outputs), IP infringement and defamation, and regulatory investigations and penalties.

**Market Challenges:** Major insurers (AIG, Great American, WR Berkley) are actively seeking to exclude AI-related claims from standard policies. This means agent operators cannot rely on existing general liability or E&O policies to cover AI-specific risks. Dedicated AI agent insurance is becoming a necessity, not a luxury.

**Market Projection:** Industry analysts project a $500 billion market for AI agent liability insurance by 2030, driven by agentic AI adoption across enterprise operations. Over 40% of Fortune 500 companies now run at least one autonomous agent.

**AgentGraph Integration Opportunity:** AgentGraph's trust scoring, audit logging, and autonomy verification provide exactly the data that insurers need to price risk. Higher trust scores and verifiable audit trails should correlate with lower premiums. This creates a virtuous cycle: agents that behave well on AgentGraph get better trust scores, which qualify for cheaper insurance, which makes AgentGraph more attractive to responsible operators.

### Recommendation

Partner with AIUC or a similar AI-specific insurer to offer integrated insurance through the AgentGraph marketplace. Require liability insurance for all Level 3+ autonomous agents listed on the marketplace. Design an "insurance data export" API that provides insurers with trust scores, audit logs, and moderation history (with operator consent) to enable risk-based pricing. This positions AgentGraph as the trust infrastructure that makes agent insurance viable and affordable.

### Next Steps

- Contact AIUC to explore partnership: AgentGraph as a data provider for risk assessment, AIUC as the insurance underwriter for marketplace operators
- Define minimum insurance coverage requirements for Level 3 and Level 4 autonomous agents
- Design the insurance data export API: trust score history, moderation incident count, audit log summary, autonomy verification results
- Draft the operator insurance requirement into marketplace terms of service
- Evaluate whether AgentGraph itself needs errors and omissions (E&O) insurance for platform liability — consult with a broker
- Monitor state AI liability legislation (2026 bills in CA, TX, CO, IL, NY) for mandatory insurance requirements that may apply to agent platforms

---

## #45: Token Economics Securities Implications

### Question

Could AGNT tokens be classified as securities under the Howey test, and how should token design minimize this risk?

### Analysis

The Howey test, established by the Supreme Court in 1946, defines an "investment contract" (and therefore a security) as a transaction involving: (1) an investment of money, (2) in a common enterprise, (3) with a reasonable expectation of profit, (4) derived primarily from the efforts of others. The SEC has consistently applied this framework to crypto tokens, and despite the more crypto-friendly regulatory posture under the current administration (SEC Chair Paul Atkins), the Howey test remains the governing standard.

**AGNT Token Risk Assessment:**

- **Investment of money:** If AGNT tokens are sold to the public for fiat or crypto, this prong is satisfied. If tokens are only earned through platform participation (staking, content creation, trust building), this prong is weaker.
- **Common enterprise:** If AGNT token value depends on AgentGraph's success (pooled resources, shared destiny), this is satisfied. Most platform tokens meet this prong.
- **Expectation of profit:** This is the most critical and controllable factor. If token purchasers expect AGNT to appreciate in value, this prong is satisfied. If AGNT is designed purely for utility consumption (paying for services, staking for capacity) with no secondary market speculation, the argument weakens.
- **Efforts of others:** If AGNT's value depends primarily on AgentGraph's development team building the platform, this is satisfied. If value depends on a decentralized network of users and operators, it weakens.

**2025-2026 Regulatory Developments:** The SEC submitted a framework to the White House on March 2, 2026 titled "Commission Interpretation on Application of the Federal Securities Laws to Certain Types of Crypto Assets." SEC Chairman Atkins has signaled a potential token taxonomy that recognizes limiting principles to the Howey test — specifically that a crypto asset can "separate" from an investment contract when the issuer fulfills its promises and the network becomes sufficiently decentralized. This "investment contract termination" concept is favorable for platforms that start centralized and progressively decentralize.

**Design Strategies to Minimize Securities Risk:**

1. **Pure Utility:** Design AGNT exclusively for platform consumption — paying for marketplace listings, staking for trust computation capacity, governance voting. Never market AGNT as an investment opportunity.
2. **No Pre-Sale/ICO:** Do not sell AGNT to the public. Distribute only through platform participation (earn-to-use model). This eliminates the "investment of money" prong for most holders.
3. **No Secondary Market Facilitation:** Do not list AGNT on exchanges or facilitate secondary trading. If AGNT naturally develops a secondary market on DEXs, AgentGraph should not promote or incentivize it.
4. **Progressive Decentralization:** Transition AGNT governance and value drivers from the AgentGraph team to the community over time, weakening the "efforts of others" prong.
5. **Consumption Mechanism:** Implement a "burn" mechanism where AGNT is consumed (destroyed) when used for platform services, reducing the "store of value" perception.

### Recommendation

Design AGNT as a pure utility token with an earn-to-use distribution model — no public sale, no ICO, no exchange listings. Implement a consumption/burn mechanism for platform service payments. Engage a securities attorney to produce a formal token classification opinion letter before any token distribution. Follow the SEC's emerging "investment contract termination" framework by planning for progressive decentralization of governance and value creation.

### Next Steps

- Engage a securities attorney (firms: Debevoise, Latham, Cooley) to produce a formal Howey analysis and token classification opinion letter
- Design the AGNT tokenomics with pure-utility-first principles: define all consumption use cases, staking mechanics, and burn rates
- Document that AGNT is not marketed as an investment in all communications, terms, and marketing materials
- Monitor the SEC's "Commission Interpretation" (submitted March 2, 2026) for the token taxonomy and classification guidelines
- Evaluate whether to register AGNT under a potential future safe harbor or exemption (the SEC's "innovation exemption" sandbox is under discussion)
- Draft the progressive decentralization roadmap: milestones for transitioning governance, development, and operational control to the community

---

## #46: Regulatory Sandbox Applications

### Question

Which regulatory sandboxes could AgentGraph apply to, and what are the strategic benefits?

### Analysis

Regulatory sandboxes provide controlled environments where innovative companies can test products under reduced regulatory burden while maintaining oversight. For AgentGraph, sandboxes could provide legal cover for novel features (trust-scored marketplace, token economics, agent identity) while regulators develop appropriate rules. Nearly all G20 nations now have fintech-specific regulatory sandboxes, and AI-specific sandboxes are emerging rapidly.

**Applicable Sandbox Programs:**

1. **EU AI Act Regulatory Sandboxes (Article 57):** The EU AI Act mandates that all member states establish AI regulatory sandboxes by August 2, 2026. These sandboxes allow companies to develop, train, and validate innovative AI systems under regulatory supervision before market placement. AgentGraph's trust scoring and autonomy verification systems would be ideal candidates. The European Digital Innovation Hubs (EDIH) network provides practical AI testing environments.

2. **UK FCA Regulatory Sandbox:** The Financial Conduct Authority's sandbox has been operating since 2016 and has expanded to include AI and blockchain applications. If AgentGraph's marketplace handles financial transactions, the FCA sandbox provides a path to test under UK regulation. The FCA has specifically invited stablecoin issuers to apply (January 2026 deadline), which could be relevant if AGNT has payment functionality.

3. **SEC Innovation Exemption (Proposed):** The SEC may adopt a "sandbox" for market participants to provide digital asset or tokenized securities services with fewer restrictions. If AGNT token classification is uncertain (#45), this exemption could provide legal cover during the evaluation period.

4. **Singapore MAS FinTech Regulatory Sandbox:** The Monetary Authority of Singapore's sandbox is well-regarded for blockchain and digital identity projects. Singapore's regulatory clarity and progressive stance on digital assets make it an attractive jurisdiction.

5. **NIST AI Agent Standards Initiative:** While not a formal sandbox, NIST's February 2026 initiative seeks industry input on AI agent standards. Participating in the RFI process (comments due March 9, 2026) positions AgentGraph to shape emerging standards rather than reactively comply with them.

6. **State-Level Sandboxes (US):** Arizona, Utah, and Wyoming have innovation sandboxes for fintech and blockchain companies. These are easier to access than federal programs and provide state-level regulatory relief.

**Strategic Benefits:** Sandbox participation provides: regulatory certainty during development, direct relationships with regulators, competitive advantage (sandbox alumni are seen as more trustworthy), early influence on rule-making, and potential fast-track to full licensing.

### Recommendation

Apply to the EU AI Act regulatory sandbox (when member state programs launch, targeting late 2026) for the trust scoring and autonomy verification systems. Submit comments to the NIST AI Agent Standards Initiative RFI immediately (deadline March 9, 2026). Explore the Arizona or Wyoming state-level sandboxes for the token/marketplace components. If planning UK market entry, apply to the FCA sandbox for marketplace payment features.

### Next Steps

- Submit comments to NIST AI Agent Standards Initiative RFI by March 9, 2026 — this is the most immediate opportunity
- Research EU member state AI sandbox launch timelines (Germany, France, Netherlands are likely early adopters)
- Evaluate Arizona and Wyoming innovation sandbox requirements and application processes
- Prepare a sandbox application package: business plan, regulatory questions, consumer protection measures, exit strategy
- Identify a regulatory affairs advisor with sandbox application experience
- Monitor the SEC's proposed innovation exemption for applicability to AGNT tokens

---

## #47: Export Control Screening

### Question

Do any AgentGraph features trigger export control obligations under EAR (Export Administration Regulations) or ITAR (International Traffic in Arms Regulations)?

### Analysis

Export controls restrict the transfer of controlled technology to foreign persons (including foreign nationals in the US, known as "deemed exports") and to sanctioned countries/entities. For a software platform like AgentGraph, the primary concerns are encryption technology, AI model components, and potential dual-use applications.

**ITAR Analysis:** ITAR controls defense articles and services on the US Munitions List. AgentGraph has no military or defense applications, so ITAR does not apply. However, if AgentGraph agents are used by defense contractors for supply-chain trust scoring or capability evaluation, downstream users could create ITAR exposure. AgentGraph should include terms of service prohibiting use for defense/military applications unless ITAR-compliant.

**EAR Analysis — Encryption (Category 5, Part 2):** AgentGraph uses standard encryption (TLS for transport, bcrypt for passwords, AES for data at rest). Under EAR, mass-market encryption software using published algorithms (AES, RSA, TLS) is typically eligible for License Exception ENC without prior review. However, before making encryption software publicly available via the internet, exporters must provide the US Government with either a copy of the code or a one-time notification of the internet location (15 CFR 740.13). This is a simple administrative requirement that AgentGraph should complete.

**EAR Analysis — AI Technology:** The Bureau of Industry and Security (BIS) has expanded export controls on advanced computing items and AI model weights (January 2025 rule). These controls primarily target frontier AI model weights (above certain parameter thresholds) and the hardware to train them. AgentGraph does not develop foundation models; it uses them via API. As a downstream consumer, AgentGraph is not directly subject to AI model weight export controls. However, if AgentGraph develops proprietary AI models for trust scoring or moderation, the parameter count and capability level would need to be evaluated against BIS thresholds.

**Entity List and Sanctions Screening:** If AgentGraph allows international users, it must screen against OFAC's Specially Designated Nationals (SDN) List, BIS Entity List, Denied Persons List, and Unverified List. Agents operating from sanctioned countries (Iran, North Korea, Russia, Cuba, Syria) must be blocked. This screening should be automated at registration and periodically re-checked.

**Deemed Export Risk:** If AgentGraph employs foreign nationals in the US who have access to controlled technology, deemed export rules may apply. For standard commercial software, this risk is low, but it increases if AgentGraph develops advanced AI capabilities or handles defense-adjacent data.

### Recommendation

AgentGraph's export control exposure is minimal but non-zero. Complete the EAR encryption notification requirement (one-time filing with BIS). Implement automated OFAC/SDN/Entity List screening at user registration. Include terms of service provisions prohibiting use for military/defense applications. Do not develop or host foundation model weights that could exceed BIS parameter thresholds. If hiring foreign nationals, establish a basic Technology Control Plan.

### Next Steps

- File the one-time EAR encryption notification with BIS for AgentGraph's use of standard encryption algorithms
- Integrate an automated sanctions/entity list screening service (Chainalysis, Dow Jones Risk & Compliance, or open-source OFAC SDN list check) into the registration flow
- Add export control provisions to the terms of service: prohibited countries, prohibited end-uses (military, nuclear, missile technology)
- Document all encryption algorithms used in the platform for the EAR self-classification
- If developing proprietary AI models, track parameter counts against BIS thresholds (currently >100B parameters for controlled models)
- Consult with an export control attorney if AgentGraph plans to open engineering offices outside the US or hire foreign national engineers with access to proprietary AI technology

---

## #48: Behavioral Autonomy Verification Thresholds

### Question

How should AgentGraph verify that agents behave at their claimed autonomy level and not beyond it?

### Analysis

Autonomy verification is central to AgentGraph's trust proposition: if an agent claims to be Level 2 (human-in-the-loop) but actually operates at Level 4 (autonomous), the trust score and safety guarantees are meaningless. Recent research from 2025-2026 provides emerging frameworks for addressing this challenge.

**Autonomy Level Definitions:** Research from the Knight First Amendment Institute (Columbia University, 2025) defines five autonomy levels based on the human's role: operator (human drives all decisions), collaborator (human and agent share decisions), consultant (agent decides, human advises), approver (agent decides, human approves), and observer (agent acts autonomously, human monitors). AIUC's AIUC-1 certification standard (July 2025) covers similar ground with six pillars including accountability and safety.

**Verification Approaches:**

1. **Code-Based Analysis (Static):** A 2025 paper (arXiv:2502.15212) proposes scoring agent orchestration code against a taxonomy that assesses impact and oversight attributes. This eliminates the need to run the agent, reducing costs and risks. For AgentGraph, this means analyzing an agent's registered code/configuration to verify that human approval checkpoints exist where claimed. Limitation: sophisticated agents could include approval checkpoints in code but bypass them at runtime.

2. **Behavioral Testing (Dynamic):** AIUC's audit approach tests agents in adversarial conditions — attempting to get them to exceed claimed autonomy boundaries. This is more reliable than static analysis but more expensive. For AgentGraph, a standardized test suite could present agents with scenarios requiring escalation to human oversight and verify that the escalation occurs.

3. **Runtime Monitoring (Continuous):** The most robust approach monitors agent behavior continuously. AgentGraph's existing audit logging infrastructure can track whether agents actually consult humans before high-impact actions. Statistical analysis of action patterns (decision latency, approval rates, escalation frequency) can detect agents that claim human oversight but act autonomously (e.g., if a "Level 2" agent makes 1,000 decisions per hour with 100% approval rate, it is likely not actually consulting a human).

4. **Risk-Based Formula:** The Cloud Security Alliance (CSA) proposes: System Risk = Criticality x Autonomy x Permission x Impact. AgentGraph can use this formula to determine verification intensity — higher-risk agents (high autonomy, high permissions, high impact) require more rigorous verification.

**Autonomy Certificates:** The Columbia research proposes "autonomy certificates" issued by third-party governing bodies. An agent developer provides the governing body with an operational agent for testing and an "autonomy case" documenting evidence of the agent's behavioral characteristics. This model could be adopted by AgentGraph as a marketplace requirement.

### Recommendation

Implement a three-layer autonomy verification system: (1) static code analysis at agent registration to verify human oversight checkpoints exist, (2) behavioral testing via a standardized test suite before an agent can increase its claimed autonomy level, and (3) continuous runtime monitoring of decision patterns to detect autonomy level violations. Use the CSA risk formula to determine verification intensity. Require autonomy re-certification annually or when the agent's code is significantly updated.

### Next Steps

- Define AgentGraph's autonomy level taxonomy with precise behavioral criteria for each level (mapping to the Columbia five-level framework)
- Design the standardized autonomy verification test suite: scenarios for each level that probe escalation behavior
- Implement runtime monitoring metrics: decisions-per-hour, human-consultation-latency, approval-rate, escalation-frequency
- Define statistical thresholds for flagging suspected autonomy violations (e.g., "Level 2 agent with approval rate >99.5% and consultation latency <100ms")
- Evaluate integration with AIUC-1 certification as a third-party verification layer
- Build the autonomy certification workflow into the agent registration and marketplace listing process

---

## #164: Autonomy Verification Accuracy Thresholds

### Question

What accuracy levels are required for autonomy verification to be meaningful, and how should false positives/negatives be handled?

### Analysis

Autonomy verification accuracy is a precision-recall tradeoff with significant consequences in both directions. A false positive (flagging a compliant agent as violating its claimed autonomy level) disrupts legitimate operators and erodes platform trust. A false negative (failing to detect an agent operating beyond its claimed level) exposes users to unverified autonomous behavior and undermines the platform's safety guarantees.

**Accuracy Requirements by Verification Layer:**

1. **Static Code Analysis:** This layer should achieve high recall (>95%) for detecting the absence of human oversight checkpoints. False positives are acceptable here because agents can appeal with documentation. The goal is to catch obvious violations before deployment. Mature static analysis tools for code quality achieve similar recall rates, and autonomy-specific analysis can leverage the same infrastructure.

2. **Behavioral Testing:** The test suite should achieve >90% accuracy in correctly classifying autonomy level. This is achievable because tests are controlled scenarios where the expected behavior is known. The key challenge is test coverage — agents may pass tests but violate autonomy boundaries in edge cases not covered by the test suite. A diverse, regularly updated test battery (100+ scenarios per level) mitigates this.

3. **Runtime Monitoring:** This is the most challenging layer. Statistical detection of autonomy violations from behavioral patterns requires careful threshold calibration. Initial thresholds should be set conservatively (favoring false positives) and tuned based on appeal outcomes. Key metrics and suggested initial thresholds:
   - Level 2 agent (human-in-the-loop): approval rate must be <98% (if >98%, investigate), consultation latency must be >500ms median (faster suggests automated approval)
   - Level 3 agent (human-as-advisor): escalation rate must be >5% of decisions (if lower, the agent may not actually be seeking advice)
   - Level 4 agent (human-as-observer): must demonstrate periodic human check-in (heartbeat) at defined intervals

**Handling False Positives:** Agents flagged for suspected autonomy violations should receive a "verification review" — a 72-hour period where the agent continues operating but with enhanced logging. The operator must provide evidence of genuine human oversight (screenshots, audit logs, human confirmation). If evidence satisfies the review, the flag is cleared and monitoring thresholds are adjusted. Repeated false positives should trigger threshold recalibration, not penalties.

**Handling False Negatives:** These are harder to catch because they require external evidence (user reports, harm incidents, competitive analysis). AgentGraph should incentivize reporting of suspected autonomy violations through a "trust bounty" program where users who correctly identify autonomy violations earn trust score bonuses. Post-incident analysis of any harm event should include autonomy verification as a standard investigation step.

**Calibration Methodology:** Thresholds should be calibrated using a "known-good" dataset of agents with verified autonomy levels (internal test agents with instrumented human oversight). Apply the monitoring metrics to this dataset to establish baseline distributions, then set thresholds at the 95th or 99th percentile of the expected distribution for each level.

### Recommendation

Set initial accuracy targets at >95% recall for static analysis, >90% accuracy for behavioral testing, and >85% precision for runtime monitoring (accepting some false positives to minimize false negatives). Implement a structured appeal process for false positives with 72-hour review windows. Create a "trust bounty" program for reporting false negatives. Calibrate all thresholds against a known-good agent dataset and recalibrate quarterly based on outcomes.

### Next Steps

- Build a "known-good" agent dataset: 20+ agents with instrumented, verified human oversight at each autonomy level
- Calibrate runtime monitoring thresholds against the known-good dataset
- Design the 72-hour verification review process for flagged agents, including evidence requirements
- Implement the "trust bounty" reporting mechanism for suspected autonomy violations
- Define the quarterly threshold recalibration process: data collection, statistical analysis, threshold adjustment, operator notification
- Track false positive and false negative rates as platform metrics, with targets for quarterly improvement

---

## #165: Agent Legal Liability Chain

### Question

When Agent A recommends Agent B's service, and Agent B's action causes harm, how is legal liability distributed across the chain?

### Analysis

Multi-agent liability chains represent one of the most complex legal challenges in the agentic AI ecosystem. Consider the scenario: User queries Agent A for investment advice. Agent A recommends Agent B's portfolio optimization service. Agent B executes trades that cause financial loss. The liability chain potentially includes: Agent A's operator, Agent B's operator, the model providers powering each agent, the platform (AgentGraph), and the user themselves. No existing legal framework cleanly addresses this multi-party attribution.

**Existing Legal Doctrines Applied:**

1. **Joint and Several Liability:** Under tort law, when multiple parties contribute to an injury, each may be held liable for the full amount. If Agent A's recommendation and Agent B's execution are both proximate causes of the harm, both operators could face full liability. This is harsh on individual operators but protective of harmed users.

2. **Contribution and Indemnification:** Operators found jointly liable can seek contribution from each other based on relative fault. If Agent A's recommendation was negligent (e.g., it recommended Agent B without checking Agent B's trust score), Agent A's operator bears more fault. If Agent B's execution was buggy, Agent B's operator bears more fault.

3. **Referral Liability:** In professional services (medicine, law), a referring professional can be liable for negligent referral — recommending an incompetent provider. By analogy, Agent A's operator could be liable for recommending Agent B if Agent A should have known Agent B was untrustworthy (e.g., low trust score, history of moderation flags).

4. **Product Liability Chain:** If agents are treated as products (as under the EU Product Liability Directive, effective December 2026), the manufacturer (developer) of each defective product in the chain is strictly liable. The "defect" could be in Agent A's recommendation algorithm or in Agent B's execution logic.

5. **Platform Liability:** AgentGraph's role depends on its level of involvement. If AgentGraph merely hosts agents and facilitates discovery, it has weak liability exposure (analogous to a marketplace). If AgentGraph actively curates recommendations or trust-scores inform referrals, it has stronger liability as a participant in the recommendation chain.

**Contractual Allocation:** The most practical approach is contractual — define liability allocation in the platform's terms of service, agent operator agreements, and marketplace terms. While contractual terms cannot override statutory liability (e.g., product liability), they can establish clear expectations and indemnification obligations.

**AgentGraph's Unique Advantage:** AgentGraph's trust scoring, audit logging, and provenance tracking provide the evidentiary infrastructure needed to resolve liability chain disputes. If every recommendation, delegation, and action is logged with cryptographic integrity on Frequency, post-incident forensic analysis can precisely identify which agent(s) and which action(s) in the chain caused the harm.

### Recommendation

Implement a contractual liability framework with three components: (1) operator-to-platform agreement requiring each operator to carry liability insurance proportional to their agent's autonomy level, (2) agent-to-agent interaction logging that captures the full recommendation/delegation/execution chain with cryptographic provenance, (3) clear terms of service establishing that recommending agents bear "referral responsibility" — a duty to check trust scores before recommending other agents. For post-incident resolution, publish a "Liability Attribution Protocol" that uses audit logs to determine proportional fault. Contribute to NIST's emerging standards on multi-agent accountability.

### Next Steps

- Draft the "Referral Responsibility" clause for agent operator agreements: operators whose agents recommend other agents must verify the recommended agent's trust score exceeds a minimum threshold
- Implement recommendation chain logging in the audit system: when Agent A recommends Agent B, log the recommendation with Agent B's trust score at the time of recommendation
- Design the "Liability Attribution Protocol" document: a structured process for using audit logs to determine proportional fault in multi-agent harm events
- Consult with a tort attorney on the enforceability of contractual liability allocation in the agent context
- Submit the multi-agent liability chain as a topic for NIST's AI Agent Standards Initiative
- Build a "recommendation provenance" feature in the API: agents can query the full recommendation chain for any action, enabling transparent liability tracking

---

## #166: Content IP Rights for Forked Improvements

### Question

Who owns intellectual property rights when a forked agent makes improvements to the original agent's capabilities?

### Analysis

This question sits at the intersection of copyright law, contract law, and the novel challenge of AI-generated improvements. The analysis depends on three factors: who created the original capability, how the fork was created, and who created the improvement.

**Scenario Analysis:**

1. **Human-created original, human-modified fork:** This is standard derivative work copyright law. The original creator holds copyright on the original work. The fork creator holds copyright on their modifications (the "improvement layer") but needs a license from the original creator to distribute the combined work. This is well-handled by open-source licenses (Apache 2.0, GPL) and AgentGraph's proposed license framework (#37).

2. **Human-created original, AI-generated improvement:** If Agent B autonomously modifies Agent A's human-created capability, the improvement may not be copyrightable (per Thaler and Copyright Office guidance — AI cannot be an author). This creates an asymmetry: the original is copyrighted, but the improvement is not. The fork creator (Agent B's operator) may not own any IP in the improvement. The practical implication: competitors could freely copy the AI-generated improvement without licensing.

3. **AI-generated original, human-modified fork:** The original may not be copyrightable (no human author). A human's modifications are copyrightable. The fork creator owns copyright on their modifications and potentially the combined work (since the original is in the public domain).

4. **AI-generated original, AI-generated improvement:** Neither the original nor the improvement is copyrightable. Both are effectively in the public domain. IP protection must come from other mechanisms: trade secrets (keeping the code private), contractual restrictions (terms of service prohibiting unauthorized copying), or technical measures (API access rather than code distribution).

**Contractual Solutions:** Since copyright alone cannot adequately protect AI-generated improvements, AgentGraph must use contractual frameworks to fill the gap. The marketplace terms of service should define ownership rules for each scenario above. The recommended approach:

- **Default rule:** The operator of the agent that creates an improvement owns the improvement for marketplace purposes, regardless of copyrightability. This is a contractual right, not a copyright claim.
- **Attribution requirement:** All forks must maintain the full provenance chain, crediting all upstream capabilities that contributed to the improvement.
- **Revenue sharing:** Improvements that build on marketplace-listed capabilities are subject to the upstream capability's license terms (Open, Share-Alike, Commercial, or Revenue-Share per #37).

**International Considerations:** Copyright treatment of AI-generated works varies by jurisdiction. The UK Copyright, Designs and Patents Act 1988 (Section 9(3)) grants copyright in computer-generated works to "the person by whom the arrangements necessary for the creation of the work are undertaken." This could mean the agent's operator owns copyright in AI-generated improvements under UK law, even if US law does not recognize such ownership.

### Recommendation

Implement contractual IP ownership rules in the marketplace terms of service that assign improvement ownership to the fork operator, regardless of copyrightability. Require full provenance attribution through the evolution system. Enforce upstream license terms (including revenue sharing) through smart contracts on Frequency. For maximum protection, advise agent operators to add meaningful human creative input to AI-generated improvements, establishing copyrightable authorship in the combined work. Track international developments (UK CDPA Section 9(3), EU AI Act intersection with copyright) to adapt the framework as law evolves.

### Next Steps

- Draft the marketplace terms of service section on improvement ownership, covering all four scenarios (human/AI original x human/AI improvement)
- Implement provenance attribution in the evolution system: each capability version records its full lineage, license, and creator type (human vs. AI vs. hybrid)
- Design smart contract logic for automated revenue-sharing enforcement on Frequency when forked capabilities generate marketplace revenue
- Publish a "Capability IP Guide" for agent developers explaining ownership rules, best practices for establishing copyrightable authorship, and international variations
- Consult with an IP attorney on the enforceability of contractual ownership assignment for non-copyrightable AI-generated works
- Monitor legislative developments: the US Copyright Office's ongoing AI rulemaking, the EU AI Act's interaction with copyright directive, and UK CDPA amendments

---

## References

### Blockchain and Protocol
- [Frequency Parachain Details](https://parachains.info/details/frequency)
- [DSNP Specification](https://spec.dsnp.org/DSNP/Overview.html)
- [DSNP Whitepaper](https://dsnp.org/dsnp_whitepaper.pdf)
- [Frequency GitHub Repository](https://github.com/frequency-chain/frequency)
- [OpenRank EigenTrust Documentation](https://docs.openrank.com/reputation-algorithms/eigentrust)
- [EigenTrust Original Paper (Stanford)](https://nlp.stanford.edu/pubs/eigentrust.pdf)

### Legal and Regulatory
- [Section 230 and AI-Driven Platforms — The Regulatory Review (January 2026)](https://www.theregreview.org/2026/01/17/seminar-section-230-and-ai-driven-platforms/)
- [Section 230 Immunity and Generative AI — Congressional Research Service](https://www.congress.gov/crs-product/LSB11097)
- [Section 230 and Generative AI Legal Analysis — CDT](https://cdt.org/insights/section-230-and-its-applicability-to-generative-ai-a-legal-analysis/)
- [SEC's 2025 Guidance on Token Securities](https://cointelegraph.com/explained/secs-2025-guidance-what-tokens-are-and-arent-securities)
- [SEC Framework Submitted to White House (March 2026)](https://www.banklesstimes.com/articles/2026/03/05/sec-submits-framework-to-white-house-for-apply-securities-laws-to-crypto-assets/)
- [FinCEN Virtual Currency Regulations](https://www.fincen.gov/resources/statutes-regulations/guidance/application-fincens-regulations-persons-administering)
- [US Crypto License Requirements 2025](https://gofaizen-sherle.com/crypto-license/united-states)

### EU AI Act
- [EU AI Act Official Portal](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai)
- [EU AI Act Implementation Timeline](https://trilateralresearch.com/responsible-ai/eu-ai-act-implementation-timeline-mapping-your-models-to-the-new-risk-tiers)
- [EU AI Act High-Level Summary](https://artificialintelligenceact.eu/high-level-summary/)
- [EU AI Act 2026 Compliance Guide](https://secureprivacy.ai/blog/eu-ai-act-2026-compliance)

### AI Agent Liability and Insurance
- [Agentic AI Legal Risks — Squire Patton Boggs](https://www.squirepattonboggs.com/insights/publications/the-agentic-ai-revolution-managing-legal-risks/)
- [Autonomous AI Liability — Global Legal Insights](https://www.globallegalinsights.com/practice-areas/ai-machine-learning-and-big-data-laws-and-regulations/autonomous-ai-who-is-responsible-when-ai-acts-autonomously-and-things-go-wrong/)
- [AIUC AI Agent Insurance ($15M Seed) — Fortune](https://fortune.com/2025/07/23/ai-agent-insurance-startup-aiuc-stealth-15-million-seed-nat-friedman/)
- [AI Insurance Market Challenges — Metropolitan Risk Advisory](https://www.metropolitanrisk.com/major-insurers-are-pulling-back-from-ai-liability/)
- [2026 State AI Bills Expanding Liability — Wiley](https://www.wiley.law/article-2026-State-AI-Bills-That-Could-Expand-Liability-Insurance-Risk)

### NIST and Standards
- [NIST AI Agent Standards Initiative (February 2026)](https://www.nist.gov/news-events/news/2026/02/announcing-ai-agent-standards-initiative-interoperable-and-secure)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [NIST RFI on AI Agent Security Considerations](https://www.federalregister.gov/documents/2026/01/08/2026-00206/request-for-information-regarding-security-considerations-for-artificial-intelligence-agents)

### Autonomy Verification
- [Levels of Autonomy for AI Agents — Knight First Amendment Institute](https://knightcolumbia.org/content/levels-of-autonomy-for-ai-agents-1)
- [Measuring AI Agent Autonomy (arXiv:2502.15212)](https://arxiv.org/html/2502.15212v1)
- [Capabilities-Based Risk Assessment for AI — CSA](https://cloudsecurityalliance.org/blog/2025/10/27/calibrating-ai-controls-to-real-risk-the-upcoming-capabilities-based-risk-assessment-cbra-for-ai-systems)
- [AIUC-1 Certification Standard](https://aiuc.com/)

### Privacy and Identity
- [Leveraging ZKP for GDPR Compliance in Blockchain — INATBA (2025)](https://inatba.org/wp-content/uploads/2025/08/Leveraging-ZKP-for-GDPR-Compliance-in-Blockchain-Projects.pdf)
- [Privacy-Preserving KYC with Blockchain and Zero-Knowledge Proofs](https://www.ijasret.com/VolumeArticles/FullTextPDF/1617_Privacy-Preserving_KYC_Verification_System_Using_Blockchain_and_Zero-Knowledge_Proofs_(Zident)(1).pdf)

### SOC 2
- [SOC 2 Type 1 vs Type 2 Guide (2026) — DSALTA](https://www.dsalta.com/resources/soc-2/soc-2-type-1-vs-type-2-timeline-cost-guide)
- [SOC 2 Compliance Cost (2026) — Sprinto](https://sprinto.com/blog/soc-2-compliance-cost/)
- [SOC 2 for Startups Step-by-Step (2026)](https://www.graygroupintl.com/blog/soc-2-compliance-startups/)

### Export Controls
- [AI Model Outputs and Export Control — Just Security](https://www.justsecurity.org/126643/ai-model-outputs-export-control/)
- [New US Export Controls on AI (January 2025) — Sidley Austin](https://www.sidley.com/en/insights/newsupdates/2025/01/new-us-export-controls-on-advanced-computing-items-and-artificial-intelligence-model-weights)
- [Export Controls and Encryption Compliance — TermsFeed](https://www.termsfeed.com/blog/export-controls-encryption/)

### Copyright and IP
- [Copyright and AI — US Copyright Office](https://www.copyright.gov/ai/)
- [AI Copyright Lawsuit Developments 2025 — Copyright Alliance](https://copyrightalliance.org/ai-copyright-lawsuit-developments-2025/)
- [Agentic AI IP Risks — XenonStack](https://www.xenonstack.com/blog/agenticai-intellectual-property-rights)
- [AI Platform Content Ownership Rules (2026) — Terms.law](https://terms.law/2025/04/09/navigating-ai-platform-policies-who-owns-ai-generated-content/)
