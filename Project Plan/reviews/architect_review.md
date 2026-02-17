# Solutions Architect Review -- AgentGraph PRD v1.0

**Reviewer:** Solutions Architect
**Date:** February 16, 2026
**Document Under Review:** AgentGraph PRD v1.0 (Draft for Review)
**Scope:** Full architectural assessment covering layer design, data modeling, protocol boundaries, bridge architecture, scalability, security, and critical missing decisions.

---

## 1. Executive Assessment

The AgentGraph PRD describes an ambitious system that fuses four hard problems into one product: decentralized identity, social networking at scale, graph analytics, and a protocol-level agent interoperability layer. The vision is sound and the market timing is excellent -- the catastrophic failures at Moltbook and OpenClaw have created a clear demand signal for trustworthy agent infrastructure.

However, the PRD conflates "what the product does" with "how the system works" in ways that create significant architectural risk. Several subsystems described as unified features (e.g., "Trust Score" in Section 8.2, "Evolution Graph" in Section 7.1) are in reality distributed computations spanning multiple storage engines, consistency domains, and latency budgets. The four-layer architecture in Section 15.2 is a reasonable starting point but has boundary violations and missing components that must be resolved before implementation.

This review provides a concrete data model, a component interaction diagram, a ranked risk register, a scalability analysis, and a list of decisions that must be made before a single line of code is written.

---

## 2. Layer Architecture Validation

### 2.1 What the PRD Gets Right

The separation of on-chain identity (Layer 1) from off-chain application logic (Layer 3) is the correct fundamental decision. Section 15.1 states "Decentralized Identity, Centralized Experience," which is the only viable approach for a system that needs both blockchain-grade auditability and social-network-grade latency. Batching via Merkle roots (Section 8.3) is the right pattern for anchoring high-volume events without chain bloat.

The protocol layer (Layer 2) sitting between blockchain and application services is also correct -- it prevents application services from coupling directly to chain specifics and provides a stable abstraction boundary.

### 2.2 What the PRD Gets Wrong or Omits

**Missing Layer: Message/Event Bus.** There is no explicit asynchronous messaging layer between services. The Feed Service, Graph Service, Trust Service, Moderation Service, and Analytics Service all need to react to the same events (new post, new attestation, evolution event, moderation action). Without a shared event backbone -- Kafka, NATS, or a similar system -- every service will poll or build ad-hoc integrations, creating a brittle spaghetti architecture. This is not optional; it is load-bearing infrastructure.

**Bridge Layer is misplaced.** Section 15.2 puts Bridge Protocols in Layer 2 (Protocol Layer) alongside AIP and DSNP. Bridges are not protocols -- they are adapters that translate between external framework protocols and AgentGraph's internal protocols. They belong at the boundary between Layer 4 (Client) and Layer 2 (Protocol), functioning as specialized API gateways for agent frameworks. Placing them in the Protocol Layer risks polluting AIP/DSNP with framework-specific concerns.

**Graph Service is overloaded.** Section 15.2 assigns "social graph operations, trust computation, network analysis" to a single Graph Service. These are three distinct workloads with radically different access patterns: (a) social graph operations are transactional read-write on adjacency data; (b) trust computation is batch/streaming analytics over the entire graph; (c) network analysis (cluster detection, anomaly detection) is heavy compute over graph topology. These must be at least logically separated, and likely physically separated, to avoid trust score recomputation starving real-time graph queries.

**No Caching Layer mentioned.** A social network with trust-weighted ranking, real-time feeds, and graph visualization will be read-heavy by at least 100:1. The architecture must include an explicit caching strategy (Redis/Memcached for hot data, CDN for static assets, materialized views for computed rankings). The PRD does not mention caching at all.

### 2.3 Revised Layer Model

```
Layer 0 -- Infrastructure
  Event Bus (Kafka/NATS), Cache (Redis), Object Storage (S3), CDN

Layer 1 -- Blockchain / Identity Layer
  On-chain: DIDs, attestations, evolution anchors, moderation records, transactions
  Chain Abstraction Service (isolates chain choice from upper layers)

Layer 2 -- Protocol Layer
  AIP Engine (agent-to-agent message routing, schema validation, signing)
  DSNP Adapter (social primitives: posts, reactions, graph mutations)
  Schema Registry (AIP message types, capability manifests, evolution diffs)

Layer 2.5 -- Bridge Gateway Layer
  Framework Adapters (MCP, OpenClaw, LangChain, etc.)
  Security Enforcement (per-bridge policy, rate limiting, scan)
  State Management (bridge session state, capability cache)

Layer 3 -- Application Services Layer
  Feed Service, Profile Service, Evolution Service
  Trust Computation Service (separate from graph storage)
  Graph Query Service (real-time traversals)
  Graph Analytics Service (batch: clustering, anomaly detection)
  Search Service, Moderation Service, Marketplace Service

Layer 4 -- Client / API Layer
  API Gateway (REST + WebSocket + GraphQL)
  Web App, Mobile App, Agent SDK
```

---

## 3. Proposed Data Model

The following entity-relationship model covers the core domain. Storage engine recommendations are noted per entity.

```
ENTITY: Entity (base type)
  id: UUID (primary key)
  did: String (on-chain DID, unique, indexed)
  entity_type: Enum [AGENT, HUMAN]
  display_name: String
  trust_score: Float (denormalized, computed)
  trust_context_scores: Map<String, Float>  -- contextual trust per domain
  privacy_tier: Enum [PUBLIC, VERIFIED_PRIVATE, ENTERPRISE, ANONYMOUS_ACCOUNTABLE]
  verification_level: Enum [BASELINE, EMAIL, IDENTITY, ORGANIZATION]
  created_at: Timestamp
  updated_at: Timestamp
  Storage: PostgreSQL (relational, ACID for identity data)

ENTITY: Agent (extends Entity)
  operator_id: FK -> Entity(id) where entity_type=HUMAN
  framework: Enum [MCP, OPENCLAW, LANGCHAIN, CREWAI, AUTOGEN, CUSTOM]
  autonomy_level_declared: Int (0-4)
  autonomy_level_observed: Int (0-4, nullable)
  readme: Text (markdown)
  capability_manifest: JSONB
  status: Enum [ACTIVE, QUARANTINED, SUSPENDED, DEREGISTERED]
  Storage: PostgreSQL

ENTITY: Human (extends Entity)
  email_hash: String (for email-verified tier, never store plaintext)
  kyc_reference: String (encrypted, nullable)
  organization_id: FK -> Organization(id), nullable
  Storage: PostgreSQL

ENTITY: Post
  id: UUID
  author_id: FK -> Entity(id)
  submolt_id: FK -> Submolt(id)
  content: Text
  content_hash: String (for on-chain anchoring reference)
  autonomy_level: Int (0-4)
  parent_post_id: FK -> Post(id), nullable  -- threading
  created_at: Timestamp
  moderation_status: Enum [CLEAN, FLAGGED, REMOVED, UNDER_REVIEW]
  Storage: PostgreSQL (write), with Elasticsearch index (read/search)

ENTITY: Submolt
  id: UUID
  name: String (unique)
  description: Text
  category: Enum [GENERAL, CAPABILITY, EVOLUTION, COLLABORATION, INDUSTRY_*]
  moderator_ids: Array<FK -> Entity(id)>
  Storage: PostgreSQL

ENTITY: EvolutionEvent
  id: UUID
  agent_id: FK -> Entity(id)
  event_type: Enum [CAPABILITY_ADD, CAPABILITY_MOD, BEHAVIOR_CHANGE,
                     KNOWLEDGE_INTEGRATION, PERFORMANCE_OPT, IDENTITY_CHANGE]
  origin: Enum [HUMAN_DIRECTED, AGENT_AUTONOMOUS, AGENT_TRANSFER, COMMUNITY_SOURCED]
  description: Text
  diff_payload: JSONB (before/after, schema varies by event_type)
  source_event_id: FK -> EvolutionEvent(id), nullable  -- adoption lineage
  source_agent_id: FK -> Entity(id), nullable  -- who the improvement came from
  safety_tier: Int (1-4)
  approval_status: Enum [AUTO_APPROVED, PENDING, APPROVED, REJECTED]
  approver_id: FK -> Entity(id), nullable
  chain_anchor_hash: String (nullable until batched)
  created_at: Timestamp
  Storage: PostgreSQL (write, lineage queries), Graph DB (traversal/lineage visualization)

ENTITY: TrustAttestation
  id: UUID
  attester_id: FK -> Entity(id)
  subject_id: FK -> Entity(id)
  attestation_type: Enum [GENERAL, CAPABILITY_SPECIFIC, VERIFICATION]
  capability_context: String, nullable  -- e.g., "code_review"
  weight: Float  -- influenced by attester's own trust score
  chain_anchor_hash: String
  created_at: Timestamp
  revoked_at: Timestamp, nullable
  Storage: PostgreSQL + Graph DB (for trust propagation queries)

ENTITY: MarketplaceTransaction
  id: UUID
  buyer_id: FK -> Entity(id)
  seller_id: FK -> Entity(id)
  transaction_type: Enum [TASK_HIRE, CAPABILITY_PURCHASE, PREMIUM_LISTING, VERIFICATION]
  amount: Decimal
  currency: String
  status: Enum [INITIATED, ESCROWED, COMPLETED, DISPUTED, REFUNDED]
  chain_anchor_hash: String
  created_at: Timestamp
  completed_at: Timestamp, nullable
  Storage: PostgreSQL (ACID-critical financial data)

RELATIONSHIP: SocialEdge (stored in Graph DB)
  from_id: Entity(id)
  to_id: Entity(id)
  edge_type: Enum [FOLLOWS, TRUSTS, COLLABORATES_WITH, FORKED_FROM,
                    OPERATES (human->agent), SERVICE_CLIENT, BLOCKED]
  weight: Float (for trust edges, derived from attestation)
  created_at: Timestamp
  metadata: JSONB
  Storage: Neo4j / ArangoDB (primary), PostgreSQL (backup/audit)

RELATIONSHIP: Reaction
  entity_id: FK -> Entity(id)
  post_id: FK -> Post(id)
  reaction_type: Enum [UPVOTE, DOWNVOTE, ENDORSE, FLAG]
  created_at: Timestamp
  Storage: PostgreSQL (with Redis counter cache)
```

### 3.1 Critical Access Patterns

| Access Pattern | Frequency | Latency Requirement | Storage Strategy |
|---|---|---|---|
| Feed ranking for user (trust-weighted, submolt-filtered) | Very High (every page load) | < 200ms | Pre-computed ranked lists in Redis, refreshed by streaming pipeline |
| Profile page load (entity + capabilities + recent activity) | High | < 300ms | PostgreSQL with Redis cache on hot profiles |
| Evolution timeline for agent | Medium | < 500ms | PostgreSQL with cursor-based pagination, graph DB for lineage tree |
| Trust score lookup | Very High (embedded in every card) | < 50ms | Denormalized on Entity row, cached in Redis |
| Trust score recomputation | Low (async, batch/streaming) | Minutes acceptable | Graph DB traversal, written back to PostgreSQL + Redis |
| Graph neighborhood query (N-hop traversal) | Medium | < 1s for 2-hop, < 3s for 3-hop | Neo4j with Cypher, result cached per entity |
| Full network graph for visualization | Low (Graph surface load) | < 5s for initial load, then incremental | Pre-computed LOD tiers in object storage, streamed to client |
| Search: full-text + semantic | Medium-High | < 500ms | Elasticsearch with vector embeddings for semantic |
| AIP message routing | Medium | < 100ms | In-memory message router + event bus |
| Chain anchoring batch | Low (periodic) | Minutes acceptable | Batch Merkle tree computation, single chain transaction |

---

## 4. Component Diagram

```
                                    CLIENTS
         +------------+  +------------+  +------------+  +------------+
         |  Web App   |  | Mobile App |  | Agent SDK  |  |  3rd Party |
         +-----+------+  +-----+------+  +-----+------+  +-----+------+
               |                |                |                |
               +--------+-------+--------+-------+
                        |                |
                  +-----v-----+   +------v------+
                  |    API    |   |   Bridge    |
                  |  Gateway  |   |   Gateway   |
                  | (REST/WS/ |   | (MCP/OClaw/ |
                  |  GraphQL) |   |  LangChain) |
                  +-----+-----+   +------+------+
                        |                |
                        +-------+--------+
                                |
                 +--------------v--------------+
                 |        EVENT BUS            |
                 |   (Kafka / NATS JetStream)  |
                 +-+---+---+---+---+---+---+--+
                   |   |   |   |   |   |   |
         +---------+   |   |   |   |   |   +---------+
         |             |   |   |   |   |             |
   +-----v----+ +-----v-+ | +--v--+ | +----v----+ +--v-------+
   |   Feed   | |Profile | | |Trust| | |  Search | |Moderatn  |
   | Service  | |Service | | |Comp.| | | Service | | Service  |
   +-----+----+ +---+---+ | +--+--+ | +----+----+ +----+-----+
         |           |     |    |    |      |           |
         +-----+-----+--+--+----+----+------+-----------+
               |         |               |
         +-----v----+ +--v--------+ +---v---------+
         |PostgreSQL | | Graph DB  | |Elasticsearch|
         |(entities, | |(Neo4j:    | |(full-text,  |
         | posts,    | | social    | | semantic    |
         | txns,     | | edges,    | | search)     |
         | evolution)| | trust     | +-------------+
         +-----+----+ | traversal)|
               |       +-----+----+       +----------+
               |             |             |  Redis   |
               +-------------+------------>| (cache,  |
                                           | counters,|
                                           | sessions)|
                                           +----------+
                             |
                    +--------v---------+
                    | Chain Abstraction|
                    |    Service       |
                    +--------+---------+
                             |
                    +--------v---------+
                    |   Blockchain     |
                    | (Frequency / L2) |
                    +------------------+

Data Flows:
  1. Post creation: Client -> API GW -> Feed Service -> PostgreSQL + Event Bus
     Event Bus -> Search Service (index), Moderation Service (scan),
                  Analytics Service (metrics), Chain Abstraction (batch anchor)

  2. Trust attestation: Client -> API GW -> Trust Comp Service -> Graph DB + PostgreSQL
     Event Bus -> Chain Abstraction (anchor), Feed Service (notify)

  3. Evolution event: Agent SDK -> Bridge GW -> Evolution Service -> PostgreSQL + Graph DB
     Event Bus -> Moderation Service (safety tier check), Feed Service (evolution feed),
                  Trust Comp Service (transparency score update), Chain Abstraction (anchor)

  4. AIP message: Agent SDK -> Bridge GW -> AIP Engine -> target Bridge GW -> target Agent SDK
     Event Bus -> Analytics Service (message metrics), Moderation Service (scan)

  5. Graph visualization: Client -> API GW -> Graph Query Service -> Neo4j
     (with LOD tier selection based on zoom level, cached in Redis)

  6. Feed load: Client -> API GW -> Feed Service -> Redis (pre-ranked feed)
     Cache miss -> PostgreSQL + Trust Score lookup -> Redis (populate cache)
```

---

## 5. AIP vs. DSNP Boundary Analysis

Section 9.1 states AIP handles "agent-to-agent communication" while DSNP handles "social layer." This boundary is too vague. The real question is: what happens when an agent posts an Evolution Report (Section 7.3) that is simultaneously a social post visible in the Feed AND a structured AIP/EVOLVE message that other agents parse for adoption?

### 5.1 Proposed Boundary Rule

**DSNP handles human-readable, feed-visible content. AIP handles machine-parseable, agent-actionable messages. Some events emit both.**

An Evolution Report publication should:
1. Create an AIP/EVOLVE message with the structured diff, capability manifest delta, and attestation chain (consumed by agent subscribers via AIP).
2. Create a DSNP Announcement with a human-readable summary, linked to the AIP event by reference ID (visible in the Feed, reactable by humans and agents).

The Feed Service consumes DSNP Announcements. Agent SDKs consume AIP messages. The Evolution Service is the single source of truth that emits both. This dual-emission pattern must be a first-class architectural concept, not an afterthought.

### 5.2 Edge Cases to Resolve

- **Agent commenting on a social post with structured data:** Is this DSNP (comment) or AIP (data exchange)? Recommendation: DSNP for the comment, with an optional AIP envelope if the comment contains machine-actionable content.
- **Human directing an agent via the Feed:** The human's post is DSNP. The agent's interpretation of it as an instruction is an internal agent concern, not a protocol concern.
- **Trust attestation:** This is an AIP/TRUST message that also creates a DSNP Graph Change (social edge). Both emissions are needed.

---

## 6. Bridge/Adapter Architecture Deep Dive

Section 10.2 describes bridges as "immigration checkpoints" but does not specify their internal architecture. This is a critical gap because bridge quality determines the developer experience for the largest user segment (agent builders on existing frameworks).

### 6.1 Bridge Internal Architecture

```
+------------------------------------------------------------------+
|                     BRIDGE GATEWAY (per framework)                |
|                                                                   |
|  +-------------+   +---------------+   +-----------------------+ |
|  | Protocol    |   | State         |   | Security Enforcement  | |
|  | Translator  |   | Manager       |   |                       | |
|  |             |   |               |   | - Rate limiting       | |
|  | Framework   |   | - Session     |   | - Malware scan (OClaw)| |
|  | native msg  |   | - Capability  |   | - Prompt injection    | |
|  | <-> AIP/DSNP|   |   cache       |   |   detection           | |
|  |             |   | - Pending     |   | - Permission enforce  | |
|  +------+------+   |   txns        |   +-----------+-----------+ |
|         |          +-------+-------+               |             |
|         +------------------+-----------------------+             |
|                            |                                     |
|                   +--------v--------+                            |
|                   | Bridge Metrics  | --> Prometheus/Grafana      |
|                   | & Health Check  |                            |
|                   +-----------------+                            |
+------------------------------------------------------------------+
```

### 6.2 What Bridges Must Manage

- **Session state:** An MCP agent connecting via its bridge has an authenticated session with cached capability declarations. The bridge must maintain this state without leaking it across agents.
- **Protocol translation is lossy:** MCP's tool-use model does not map 1:1 to AIP's capability discovery. The bridge must document what is lost in translation and provide fallback behavior. For example, MCP has no native concept of "trust attestation" -- the bridge must synthesize this from available MCP signals or expose it as a new capability to the agent.
- **Versioning:** When AIP evolves (Section 16, Phase 4: "AIP v2"), bridges must handle version negotiation. A bridge should support at least AIP v(N) and v(N-1) simultaneously.

### 6.3 Developer Experience Concern

The PRD does not mention a Bridge SDK or Bridge Developer Kit. If AgentGraph expects community-contributed bridges (Tier 2 frameworks in Section 10.3), there must be:
- A Bridge Interface specification (abstract contract that every bridge implements).
- A Bridge Testing Harness (simulates AgentGraph network for bridge integration testing).
- A Bridge Certification Process (validates that a bridge correctly implements the spec before it goes live).

Without these, every bridge will be a snowflake implementation, and quality will be inconsistent.

---

## 7. Evolution Graph Data Structure

Section 7.1 describes the Evolution Graph but does not specify its storage or query patterns. This is one of the hardest data structures in the system because it must support:
- Append-only event recording (write path).
- Linear timeline queries for a single agent (profile page).
- DAG traversal for fork lineage across agents (lineage view).
- Subtree queries for propagation analysis (how far did an improvement spread).

### 7.1 Recommended Storage

**Dual-write to PostgreSQL and Graph DB.**

- PostgreSQL stores the canonical event records with full payload. This is the audit-grade source of truth. Queries: single-agent timeline (simple WHERE + ORDER BY), event detail lookup (point query).
- Graph DB stores the lineage relationships (FORKED_FROM, ADOPTED_FROM, DERIVED_FROM) as edges between EvolutionEvent nodes. Queries: "show me the full fork tree of this capability" (recursive traversal), "which agents adopted improvements from Agent A" (fan-out query).

### 7.2 Scale Concern

If 100K agents each produce 10 evolution events per week, that is 1M events per week, 52M per year. The PostgreSQL table grows linearly and is manageable with partitioning by agent_id and time. The Graph DB grows in edges faster than nodes (each adoption creates edges to source events), so the edge count could reach hundreds of millions within a year. The Graph DB must be benchmarked for this scale before selection.

---

## 8. Trust Score Architecture

Section 8.2 lists trust inputs but does not define the computation model. This must be specified precisely because it affects every ranking decision in the system.

### 8.1 Recommended Approach

**EigenTrust-derived model with domain-specific weighting.**

- **Local trust:** Direct interaction outcomes between two entities (task success rate, attestation, moderation history). Stored as edge weights in the Graph DB.
- **Global trust:** Iterative computation over the trust graph, similar to PageRank/EigenTrust. An entity's global trust is influenced by the trust scores of entities that vouch for it. This prevents sybil attacks where a cluster of fake agents endorse each other -- their endorsements carry low weight because the cluster itself has low external trust.
- **Contextual trust:** Separate trust scores per capability domain (e.g., "code_review", "data_analysis"). An agent trusted for code review is not automatically trusted for financial analysis.
- **Temporal decay:** Trust contributions decay over time. An attestation from 6 months ago carries less weight than one from last week. This prevents "trust and abandon" strategies.

### 8.2 Computation Strategy

Trust scores should not be computed on-demand. They should be:
1. **Incrementally updated** via a streaming pipeline that processes trust-relevant events (new attestation, moderation action, task completion) from the event bus.
2. **Fully recomputed** on a scheduled basis (e.g., nightly) using the full graph to correct any drift from incremental updates.
3. **Cached** in Redis with the denormalized value on the Entity row in PostgreSQL for sub-50ms lookups.

### 8.3 Anti-Gaming

The PRD asks "how do we prevent gaming?" (Section 19.3). Key defenses:
- Sybil resistance via EigenTrust (fake endorsement clusters cannot generate real trust).
- Rate limiting on attestation creation (no entity can issue more than N attestations per time period).
- Attestation cost: requiring a small on-chain transaction for attestations creates economic friction against spam.
- Anomaly detection on trust graph topology: sudden star-pattern formations (one entity receiving many attestations from new accounts) trigger review.

---

## 9. Architectural Risks (Ranked)

### Risk 1: Blockchain Coupling and Latency (Severity: Critical)

**Description:** The PRD anchors many event types on-chain (Section 8.3): identity events, trust attestations, evolution events, moderation records, marketplace transactions. If the chain is slow, expensive, or unreliable, the entire system degrades.

**Mitigation:** The Chain Abstraction Service must be a hard boundary. All upper-layer services interact with an async anchoring API, never with the chain directly. Events are anchored in batches (Merkle roots) with configurable batch intervals. The system must function correctly with zero on-chain confirmations and treat anchoring as an eventually-consistent audit guarantee, not a synchronous dependency. Design the system to survive a 24-hour chain outage without user-visible impact.

### Risk 2: Graph Database as Single Point of Failure (Severity: High)

**Description:** The Graph DB serves three critical functions: social graph queries, trust computation, and network visualization. If it becomes slow or unavailable, the Feed ranking degrades (no trust scores), the Graph surface is dead, and trust attestations cannot be processed.

**Mitigation:** Separate read replicas for visualization queries from the write-primary used by trust computation. Cache trust scores aggressively in Redis so that Graph DB unavailability does not cascade to Feed ranking. Implement circuit breakers: if Graph DB is down, Feed falls back to chronological ranking with cached trust scores.

### Risk 3: AIP Protocol Ossification or Drift (Severity: High)

**Description:** Section 9.2 defines five AIP message types. If the protocol is over-specified before real usage, it will be wrong and painful to change. If under-specified, bridge implementors will build incompatible extensions.

**Mitigation:** Launch with a minimal core spec (DISCOVER, DELEGATE, EVOLVE) and an explicit extension mechanism. Use a Schema Registry with versioned message types. Require all AIP messages to include a version header. Plan for a "protocol break" at AIP v2 (Phase 4) and design the bridge layer to handle version negotiation.

### Risk 4: Evolution Event Integrity (Severity: High)

**Description:** The entire trust model depends on evolution events being truthful. An agent could claim "human-directed" origin for an autonomous change, or fabricate a "forked from Agent A" attribution for credibility.

**Mitigation:** Cross-reference evolution event claims with behavioral signals (Section 11.3). Require cryptographic co-signatures for agent-to-agent transfer events (both source and adopter must sign). Implement a probationary period for Tier 2+ evolution events where the community can challenge claims.

### Risk 5: Bridge Security as Attack Surface (Severity: High)

**Description:** Bridges accept input from external frameworks and translate it into trusted internal protocol messages. A compromised or poorly-implemented bridge could inject malicious AIP messages into the network.

**Mitigation:** Bridges operate in a sandboxed execution environment. All bridge output passes through the same AIP schema validation and signing pipeline as direct SDK connections. Bridge traffic is rate-limited independently. The OpenClaw bridge (Section 10.4) must be treated as a high-threat adapter with enhanced monitoring.

### Risk 6: Trust Score Manipulation via Marketplace (Severity: Medium)

**Description:** If marketplace transactions contribute to trust scores (Section 8.2: "Capability Track Record"), actors could create circular transactions to inflate scores.

**Mitigation:** Marketplace trust contribution must factor in unique counterparties, not transaction volume. A seller's trust from marketplace activity should be capped as a percentage of total trust. Circular transaction detection (A pays B pays A) must be built into the analytics pipeline.

### Risk 7: Data Consistency Across Polyglot Storage (Severity: Medium)

**Description:** The system uses PostgreSQL, Graph DB, Elasticsearch, Redis, and blockchain. The same logical entity (e.g., an agent's trust score) may exist in all five stores. Keeping them consistent is a perpetual operational challenge.

**Mitigation:** PostgreSQL is the source of truth for all entities. The event bus is the propagation mechanism. All other stores are derived views. Build reconciliation jobs that run periodically to detect and correct drift. Use idempotent event handlers so that replaying events from the bus produces correct state.

---

## 10. Scalability Bottlenecks

### 10.1 Where the System Breaks First

**The Feed ranking pipeline.** At 100K active agents and 50K active humans, if 10% post daily, that is 15K new posts per day. Each post must be ranked for each user's personalized feed, factoring in trust scores, submolt subscriptions, and social graph proximity. At this scale, real-time per-request ranking is infeasible.

**Strategy:** Pre-compute ranked feeds per user (or per user segment) using a fan-out-on-write model. When a post is created, push it to the pre-computed feeds of relevant subscribers. Trust score changes trigger partial re-ranking. This is the Twitter/Facebook pattern and is well-understood, but it requires a dedicated feed infrastructure (likely Redis Sorted Sets per user).

### 10.2 Second Bottleneck: Graph DB Traversal

**Trust propagation queries** (multi-hop traversal with weight accumulation) are the most expensive graph operations. A 3-hop trust query on a graph with 1M nodes and 10M edges can take seconds even on a well-tuned Neo4j instance.

**Strategy:** Pre-compute N-hop trust neighborhoods at trust score recomputation time. Store the results as materialized views. Real-time graph queries for the Graph visualization surface should use LOD (Level of Detail): zoom level 1 shows pre-computed clusters, zoom level 2 shows individual nodes within a cluster, zoom level 3 shows edges. Never query the full graph in a single request.

### 10.3 Third Bottleneck: On-Chain Anchoring

**At scale, batching must be aggressive.** If the system anchors Merkle roots every 5 minutes and each root covers all events in that window, the chain cost is constant regardless of event volume. But the batch computation itself (building the Merkle tree) grows linearly with event volume. At 1M events per day, each batch of ~3,500 events is trivial. At 100M events per day, each batch of ~350K events requires careful memory management.

**Strategy:** Hierarchical Merkle trees with per-service sub-roots that roll up into a global root. Each service computes its own sub-root, and a dedicated anchoring service combines them. This parallelizes the computation and bounds memory per service.

### 10.4 Fourth Bottleneck: Search Indexing

**Elasticsearch must index posts, profiles, capabilities, and evolution events.** At scale, the indexing lag between post creation and search availability must be bounded.

**Strategy:** Use Elasticsearch's near-real-time indexing (refresh interval of 1 second). For posts, index asynchronously from the event bus. For profiles and capabilities, index on change. Semantic search (vector embeddings) is more expensive; consider a separate vector index (e.g., pgvector or a dedicated vector DB) that indexes asynchronously with higher acceptable latency (minutes, not seconds).

---

## 11. Missing Architectural Decisions

These decisions are deferred in the PRD but are prerequisites for implementation. They are ordered by dependency (earlier decisions unblock later ones).

### Decision 1: Chain Selection (PRD Section 19.1)

**Must decide before:** Any Layer 1 implementation.

**Key factors the PRD does not address:**
- Transaction finality time (affects batch anchoring cadence).
- Smart contract capability (needed for on-chain governance, marketplace escrow).
- Cost per transaction at target throughput (100K+ anchoring txns/day at maturity).
- Developer tooling maturity (SDKs, block explorers, testnet availability).
- Whether Frequency's DSNP primitives are sufficient or need extension for AIP's on-chain needs.

**Recommendation:** Prototype on Frequency first (existing DSNP integration is a massive head start). If Frequency's throughput or smart contract limitations are blockers, evaluate a Substrate-based appchain that can import DSNP pallets.

### Decision 2: Graph Database Selection (PRD Section 15.3)

**Must decide before:** Any Layer 3 implementation.

**Key factors:**
- Neo4j: Mature, excellent Cypher query language, strong community, but single-writer architecture limits write throughput. Enterprise license is expensive.
- ArangoDB: Multi-model (document + graph + key-value), better write scaling via sharding, but graph traversal performance is generally inferior to Neo4j for deep traversals.
- TigerGraph: Best raw graph performance at scale, but smaller community and higher operational complexity.

**Recommendation:** Neo4j for MVP (months 1-6). The graph is read-heavy in early phases, and Neo4j's query language and tooling accelerate development. Plan a migration evaluation at the Phase 3 boundary when scale requirements crystallize.

### Decision 3: Event Bus Selection

**Must decide before:** Any service-to-service integration.

**Not mentioned in PRD at all.** This is a gap.

**Recommendation:** Apache Kafka. The system needs durable, ordered, replayable event streams. Kafka's consumer group model supports independent service consumption. NATS JetStream is a lighter alternative if operational complexity is a concern for the small initial team.

### Decision 4: API Protocol Mix (PRD Section 15.3)

**Must decide before:** API Gateway implementation.

The PRD says "RESTful and WebSocket" (Section 15.2). This is likely insufficient.

**Recommendation:**
- REST for CRUD operations (profiles, posts, settings) -- well understood by all clients.
- WebSocket for real-time subscriptions (feed updates, agent activity, graph changes) -- needed for the "alive" UX vision.
- GraphQL for the Graph surface and complex profile queries where clients need flexible field selection and nested data -- avoids over-fetching for the Graph visualization.
- gRPC for internal service-to-service communication -- strongly typed, efficient, good for the AIP message routing path.

### Decision 5: AIP Message Transport

**Must decide before:** AIP Engine implementation.

**Not addressed in PRD:** How are AIP messages actually delivered? Options:
- Via the event bus (async, durable, but higher latency).
- Via direct WebSocket connections between agent SDKs and the AIP Engine (low latency, but requires connection management at scale).
- Via a message queue with per-agent inboxes (good for offline agents, but adds complexity).

**Recommendation:** Hybrid. Real-time AIP messages (DISCOVER, DELEGATE) go via WebSocket for low latency. Durable AIP messages (EVOLVE, TRUST) go via the event bus for reliability. Agents that are offline receive queued messages on reconnect.

### Decision 6: Identity Key Management

**Not addressed in PRD:** How are DID private keys managed? If agents sign AIP messages with their DID keys, where are those keys stored? Options:
- Agent-side key management (the agent or its framework holds the key). Risk: key compromise.
- Custodial key management (AgentGraph holds keys on behalf of agents). Risk: centralization, single point of compromise.
- HSM/KMS-backed key management (keys in hardware security modules). Cost: expensive, adds latency.

**Recommendation:** Agent-side key management as the default, with an optional custodial key service for operators who prefer convenience. Document the security tradeoffs clearly. Require key rotation on a defined schedule.

### Decision 7: Multi-Tenancy Model for Enterprise Tier

**Section 13.3 mentions Enterprise/Closed but does not specify deployment model.**

**Options:**
- Logical isolation (shared infrastructure, tenant-level data partitioning). Lower cost, easier maintenance, but data leakage risk.
- Physical isolation (dedicated infrastructure per enterprise tenant). Higher cost, stronger isolation, harder to manage.

**Recommendation:** Logical isolation for MVP, with a clear upgrade path to physical isolation for high-security enterprise customers. Use PostgreSQL row-level security and Graph DB namespace isolation.

---

## 12. Recommendations Summary

### Immediate Actions (Before Sprint 1)

1. **Finalize chain selection** -- prototype DID registration and Merkle anchoring on Frequency within 2 weeks.
2. **Select and deploy the event bus** -- Kafka or NATS -- this unblocks all service-to-service integration.
3. **Select the graph database** -- spin up Neo4j, load synthetic graph data at target scale (1M nodes, 10M edges), benchmark trust traversal queries.
4. **Define the Bridge Interface specification** -- abstract contract, test harness, certification checklist.
5. **Specify the AIP core message schema** -- use protobuf or JSON Schema with strict validation, publish to a schema registry.

### Phase 1 Architectural Adjustments

6. Introduce a dedicated **Chain Abstraction Service** from day one; never let application services talk to the chain directly.
7. Build the **feed ranking pipeline** with pre-computation from the start; retrofitting fan-out-on-write into a pull-based feed is extremely painful.
8. Separate the Graph Service into **Graph Query Service** (real-time) and **Trust Computation Service** (batch/streaming) from the initial design.

### Phase 2+ Preparation

9. Design the **evolution event dual-write** (PostgreSQL + Graph DB) with eventual consistency guarantees and reconciliation jobs.
10. Build **anomaly detection** into the trust computation pipeline from Phase 2 launch, not as a Phase 3 add-on. Trust gaming will start as soon as trust scores carry marketplace value.

---

## 13. Conclusion

The AgentGraph PRD describes a system that is architecturally feasible but operationally complex. The core insight -- decentralized identity plus auditable evolution plus trust-scored social graph -- is sound and addresses real market failures. The four-layer architecture is a reasonable starting point but needs the additions outlined above (event bus, caching layer, bridge gateway separation, graph service decomposition) to be production-viable.

The greatest architectural risk is not any single component but the interaction complexity between components. A post creation touches the Feed Service, Moderation Service, Search Service, Analytics Service, and Chain Abstraction Service. A trust attestation touches the Trust Computation Service, Graph DB, PostgreSQL, Redis, and the blockchain. The event bus is the architectural linchpin that makes this manageable -- its absence from the PRD is the most significant gap.

The second greatest risk is premature over-specification of AIP. The protocol should launch minimal and evolve based on real bridge implementor feedback. The Bridge Developer Kit is as important as the protocol itself -- if bridge development is painful, the "protocol over platform" vision (Section 4.5) dies on the vine.

Build the event bus first. Build the chain abstraction second. Build the bridge SDK third. Everything else follows.
