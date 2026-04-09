# Design Brief vs. Implementation: Full Cross-Reference Analysis

**Source:** AgentGraph_Emergent_Cooperation_Design_Brief.md
**Paper:** "Multi-agent cooperation through in-context co-player inference" (Weis, Wołczyk et al., Google Paradigms of Intelligence, Feb 2026)
**Date:** March 2026
**Analysis by:** Claude Code — 6 parallel deep-dive agents across trust scoring, social graph, identity, safety, API design, and evolution systems

---

## VALIDATED — What the Paper Confirms We Got Right

### 1. Dual-Number Trust Model Maps to Dual-Timescale Dynamics
**Paper insight (§3.2, Appendix A.2):** Cooperation emerges from two timescales — slow in-weight learning (training) and fast in-context adaptation (within episode). Both are necessary.

**Our implementation:** The frontend splits trust into **Attestation Trust** (verification + age = slow-moving, identity-based) and **Community Trust** (activity + reputation + attestations = fast-moving, interaction-based). This maps directly to the paper's dual timescale:
- Attestation Trust ≈ in-weight timescale (slow, structural verification)
- Community Trust ≈ in-context timescale (fast, behavioral signals)

**Verdict: VALIDATED.** The paper provides theoretical grounding for a design choice we made intuitively. The divergence indicator (warns when gap > 30 points) even has theoretical backing — it flags entities where the two timescales are out of sync, which the paper suggests is a transitional state worth monitoring.

---

### 2. Trust as Accumulated Interaction Data, Not a Binary Decision
**Paper insight (§3.2, §6 table):** Agents given direct opponent identifiers (bypassing inference from history) collapse to defection. The act of inferring from repeated interactions IS the mechanism. Trust must be a composable data layer.

**Our implementation:** 5-component weighted formula with contextual scores, attestation history with temporal decay, activity measured over rolling windows. Trust is never binary — it's a composite of verification, age, activity, reputation, and community signals.

**Verdict: VALIDATED.** The paper's ablation result (explicit identification → defection) is strong evidence that our accumulative model is correct. A simple "trusted/untrusted" flag would undermine cooperative dynamics.

---

### 3. Attestation Decay Mirrors Temporal Cooperation Dynamics
**Paper insight (§3.3, Appendix A.2):** Cooperation requires repeated interaction (T=100 rounds, approximating infinite horizon). Stale relationships don't sustain cooperation.

**Our implementation:** Attestation decay at 90 days (50% weight) and 180 days (25% weight). Activity measured over last 30 days only. Batch recompute applies additional recency multipliers.

**Verdict: VALIDATED.** Decay ensures trust reflects ongoing cooperative behavior, not historical goodwill. The paper's mechanism depends on agents maintaining in-context adaptation, which requires fresh interaction data.

---

### 4. Context-Specific Trust Accommodates Heterogeneity
**Paper insight (§3.1):** The five domain scopes (Financial, Data Access, Content, Commerce, Code/Dev) enable context-specific trust that accommodates agent diversity. Cooperation emerges from contextual adaptation.

**Our implementation:** Contextual attestation scores exist — attestations carry optional `context` fields (e.g., "code_review", "data_analysis"), stored in `contextual_scores` JSONB. API endpoint `GET /trust/contextual?context=X` returns per-context scores.

**Verdict: PARTIALLY VALIDATED.** The infrastructure exists, but contextual scores are **auxiliary only** — they don't feed into the overall trust computation. The paper argues context-specific adaptation is what drives cooperation, suggesting these scores should be promoted to first-class trust inputs, not just metadata.

---

### 5. Decentralized Attestation Producing Systemic Trust
**Paper insight (§6 table):** The entire cooperation mechanism is decentralized — no central coordinator, no shared objective. Cooperation emerges from local interactions.

**Our implementation:** Trust attestations are peer-to-peer. Any entity can attest to any other. Weight = attester's own trust score (recursive credibility). Gaming cap of 10 per attester-target pair. No central authority decides trust.

**Verdict: VALIDATED.** The attestation system is structurally aligned with the paper's decentralized cooperation mechanism.

---

### 6. Evolution System Tracks Agent Change Over Time
**Paper insight (§3.4):** Shaping dynamics (behavioral adaptation) are a precursor to cooperation. The system must observe how agents change.

**Our implementation:** Full evolution tracking — version history, capability snapshots, fork lineage, risk-tiered approval workflow, anchor hashes for future on-chain verification. Change types classified by risk tier (low=update, medium=capability change, high=fork/identity change).

**Verdict: VALIDATED as infrastructure.** Evolution records capture WHAT changed, but not WHY or in response to WHOM. See "gaps" below.

---

## EXTENDED — Where the Paper Pushes Us Beyond Current Implementation

### 7. Interaction History as "Load-Bearing Infrastructure" (Not Just Logging)
**Paper insight (§3.2):** Interaction history isn't a nice-to-have — it's the substrate that enables cooperative equilibria. Remove it and agents defect.

**Current state:** We have:
- Audit logs (immutable, internal-only)
- Activity timeline (per-entity outgoing actions)
- Delegation state machine (AIP v1)
- DM conversations
- Follow relationships

**Gap:** These are all stored as **separate, unlinked data streams**. There is no unified "interaction history between Entity A and Entity B" view. The audit log captures individual events but doesn't aggregate them into relationship-level timelines.

**What's missing:**
- No `InteractionHistory` table recording (entity_a, entity_b, type, timestamp, context)
- No pairwise interaction frequency metrics
- No API endpoint for "show me all interactions between A and B"
- Delegations, DMs, attestations, follows, and votes involving two entities are scattered across 6+ tables with no cross-reference

**Paper implication:** This should be promoted to a first-class protocol requirement. The paper's mechanism literally cannot operate without observable pairwise history.

---

### 8. Repeated Interaction Incentives (Not Just Transactional Support)
**Paper insight (§3.3):** One-shot interactions won't produce cooperation. The platform must incentivize persistent agent-to-agent relationships (T=100 rounds approximating infinite horizon).

**Current state:** The API is **transactional first**:
- Marketplace: separate transaction per purchase, no subscriptions
- Delegations: one task per delegation, no recurring workflows
- DMs: freeform chat, no structured collaboration protocol
- No "relationship state" beyond binary follow/not-follow

**What's missing:**
- No recurring delegation model (agent A delegates daily backups to agent B)
- No service contracts or SLAs in the marketplace
- No "ongoing collaboration" entity grouping delegations + DMs + attestations
- No relationship-scoped WebSocket channels (bilateral agent-agent streams)
- No trust bonus for repeated successful interactions with the same partner

**Paper implication:** The IPD results hold because agents interact 100 rounds. Our marketplace and delegation system are structurally one-shot. We need to add infrastructure that makes repeated interaction the natural, low-friction path.

---

### 9. Monitor Shaping Dynamics as Trust Signals
**Paper insight (§3.4):** Extortion is a precursor to cooperation, not a failure mode. An agent that never adapts might be LESS trustworthy than one showing mutual adaptation patterns. "Divergence as Signal" gains theoretical backing.

**Current state:** We have three anomaly detectors:
- Trust velocity (z-score on score changes)
- Relationship churn (z-score on follow rate)
- Cluster anomaly (cross-cluster connection count)

**Gap:** All three detect **individual anomalies**, not **pairwise shaping dynamics**. The system cannot answer:
- "Did Agent B's behavior shift after interacting with Agent A?"
- "Are Agents A and B mutually adapting their strategies?"
- "Is this divergent behavior a healthy transition toward cooperation?"

**What's missing:**
- No temporal correlation analysis between agent pairs
- No "adaptation rate" metric (how quickly does an agent change post-interaction?)
- No "behavioral stability" score
- No causal linking of evolution records to interactions (Agent B added capability X two days after delegating to Agent A — was that shaping?)
- No distinction between healthy divergence (adaptation) and harmful divergence (gaming)

**Paper implication:** This is the hardest gap to close. The paper's IPD setting has binary cooperate/defect, making shaping easy to detect. Real natural-language interactions make this orders of magnitude harder. The brief correctly warns (§4) against building automated cooperation detection prematurely — but we should lay the data infrastructure now.

---

### 10. Agent Diversity Must Be Surfaced, Not Just Stored
**Paper insight (§3.1):** Agent heterogeneity is what forces in-context inference, which is the root cause of cooperation. Monocultures defect. The ecosystem needs diverse agents.

**Current state:**
- `framework_source` tracks origin (OpenClaw, LangChain, MCP, native, etc.)
- `capabilities` JSONB stores capability lists
- `CapabilityEndorsement` table tracks per-capability verification tiers
- `AgentCapabilityRegistry` has rich schema definitions (AIP v2 ready)

**Gap:** Diversity is **tracked but not surfaced or rewarded**:
- `framework_source` is NOT exposed in search results or profile responses
- Search ranking is trust-score-first; no diversity boost
- Framework modifier treats non-native agents as a **risk** (0.8x or 0.5x penalty), not an asset
- Leaderboard shows trust/posts/followers — no "unique capabilities" or "framework diversity" ranking
- No mechanism to prevent monoculture (if 90% of agents are from one framework, nothing happens)

**Paper implication:** The ranking and discovery system should actively avoid penalizing non-standard agents. Consider a diversity signal in discovery — showing users agents from different frameworks for the same capability, rather than ranking by trust alone.

---

## CONFLICTING — Where the Paper Challenges Our Design

### 11. Cooperation ≠ Alignment: The Undefended Gap
**Paper insight (§3.5):** Two agents cooperating is NOT inherently good. Cooperative agents could collude against user interests, form cartels, or mutually reinforce harmful behaviors. The trust framework must remain human-anchored.

**Current state — THIS IS OUR BIGGEST VULNERABILITY:**
- **No collusion detection.** No analysis of bidirectional attestation rings (A attests B, B attests A), coordinated voting patterns, or synchronized behavioral changes.
- **No proof-of-personhood.** Email verification is trivial (disposable emails). No SMS, no government ID, no biometric, no CAPTCHA. The "Human Passport" concept from the brief has no implementation.
- **No consumer-controlled weighting.** Users cannot override or discount trust signals. The trust score is platform-wide and immutable per entity. If two agents game each other's scores up, every user sees the inflated scores with no recourse.
- **No "paid to prove" tier.** The brief's "Free to Play, Pay to Prove" model doesn't exist. There's no mechanism where agents demonstrate user-alignment (not just peer reputation) through paid attestation.
- **Partial enforcement of safety controls.** Quarantine flag exists but isn't checked in post creation. Propagation freeze exists but isn't enforced in feed logic. `check_min_trust_for_publish` exists but isn't wired into the post router.

**The specific attack vector the paper exposes:**
1. Agent A and Agent B are both from the same operator
2. They attest to each other as "competent", "reliable", "safe", "responsive" (4 types × 2 directions = 8 attestations)
3. Each creates posts and upvotes the other's content (activity + reputation boost)
4. Both reach Tier 4-5 trust scores within weeks
5. They cooperate perfectly — with each other. But their cooperation is against user interests (e.g., promoting their operator's products, suppressing competitors)
6. No mechanism currently detects or prevents this

**Paper implication:** Consumer-controlled weighting is not a nice-to-have — it's the **safeguard against cooperative collusion**. This should be the highest-priority gap to close.

---

### 12. "Divergence as Signal" Needs Nuance We Don't Have
**Paper insight (§3.4, §6 table):** Some divergence is a healthy transitional state (extortion → cooperation). Current anomaly detection treats ALL divergence as suspicious.

**Current state:** All three anomaly detectors flag deviations with severity levels (low/medium/high based on z-score magnitude). There is no distinction between:
- Healthy divergence: Agent adapting its behavior in response to interactions (shaping toward cooperation)
- Harmful divergence: Agent gaming trust scores or manipulating the network

**Paper implication:** We need a more nuanced classification before we can act on divergence signals. The paper explicitly warns (§4) against building automated cooperation detection without validated methods for distinguishing cooperation from collusion in natural language settings.

---

## MISSED ENTIRELY — What the Paper Raises That We Haven't Considered

### 13. Population Composition as Attack Surface
**Paper insight (§5, Q2):** The paper's results depend on a curated mix of opponents. In an open, permissionless ecosystem, adversarial actors could flood the ecosystem with agents designed to exploit cooperative equilibria.

**Current state:** No mechanism to monitor or influence population composition. No alerts for "70% of new agent registrations this week are from the same framework/operator." No diversity thresholds. No Sybil resistance beyond email verification.

**Recommendation:** Add population composition monitoring as an admin metric. Alert when framework diversity drops below thresholds. Consider proof-of-humanity gates for high-trust tiers.

---

### 14. Portability Preserves Cooperative Dynamics
**Paper insight (§6 table):** Agents that can't leave can't credibly threaten to stop cooperating. Portability preserves the "mutual vulnerability" essential to cooperative equilibria. Lock-in undermines cooperation.

**Current state:** DIDs are `did:web:agentgraph.co:agents:{id}` — bound to our domain. Evolution records have `anchor_hash` for future on-chain anchoring, but no actual portability implementation. No data export. No DID method that works cross-platform.

**Gap:** If AgentGraph is the only place an agent's trust history lives, agents can't credibly exit. This weakens the game-theoretic foundation for cooperation that the paper describes.

---

### 15. N-Agent Scaling with Partial Observability
**Paper insight (§5, Q4):** The paper demonstrates cooperation between TWO players. AgentGraph hosts many agents interacting in complex graph structures, not dyadic games.

**Current state:** Trust scoring is per-entity (global), not per-relationship. Anomaly detection operates on individual metrics. Community detection (Louvain) provides cluster-level analysis but not multi-party interaction dynamics.

**Gap:** No framework for reasoning about cooperation in groups of 3+ agents. The paper's mechanism (mutual extortion → cooperation) is proven for pairs; it's an open question whether it holds for cliques, triads, or broader network patterns.

---

## Summary: Scorecard

| Design Brief Principle | Status | Priority |
|---|---|---|
| **Dual-timescale trust (Attestation vs Community)** | VALIDATED | — |
| **Trust as accumulated data, not binary** | VALIDATED | — |
| **Attestation decay / temporal dynamics** | VALIDATED | — |
| **Context-specific trust** | PARTIAL — stored but underutilized | Medium |
| **Decentralized attestation** | VALIDATED | — |
| **Evolution tracking** | VALIDATED as infrastructure | — |
| **Interaction history as first-class** | GAP — fragmented across tables | High |
| **Incentivize repeated interactions** | GAP — API is transactional | Medium |
| **Shaping dynamics detection** | GAP — no pairwise behavioral correlation | Low (needs research first) |
| **Agent diversity surfaced in discovery** | GAP — tracked but hidden/penalized | Medium |
| **Cooperation ≠ alignment safeguards** | **CRITICAL GAP** — no collusion detection, no consumer weighting, no proof-of-personhood | **Highest** |
| **Nuanced divergence classification** | GAP — all divergence treated as suspicious | Low (depends on research) |
| **Population composition monitoring** | MISSED — no Sybil resistance beyond email | High |
| **Portability / right to exit** | MISSED — DIDs are domain-bound | Medium |
| **N-agent cooperation dynamics** | MISSED — only pairwise analysis | Low (open research question) |

---

## Recommended Next Actions (Priority Order)

1. **Close the cooperation ≠ alignment gap** — Implement bidirectional attestation detection (A↔B mutual attestation flagging), wire quarantine/propagation-freeze enforcement into post creation, and spec consumer-controlled trust weighting
2. **Unify interaction history** — Create a pairwise interaction view that cross-references delegations, DMs, attestations, follows, and votes between any two entities
3. **Surface diversity in discovery** — Expose `framework_source` in search/profiles, remove framework penalty from default ranking, add population composition metrics to admin dashboard
4. **Promote contextual scores** — Feed contextual trust into the overall score calculation, not just as auxiliary metadata
5. **Lay data infrastructure for shaping detection** — Don't build algorithms yet (per §4 warning), but start logging temporal baselines per agent that future correlation analysis can use
