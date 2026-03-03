# Emergent Cooperation Trust Framework — Implementation Tasks

Based on cross-referencing the "Multi-agent cooperation through in-context co-player inference" paper (Google Paradigms of Intelligence, Feb 2026) against AgentGraph's current trust framework implementation.

Reference document: `docs/emergent-cooperation-cross-reference.md`

---

## BUILD NOW — Priority Tasks

### Task 1: Bidirectional Attestation Ring Detection (CRITICAL — Safety)

**Priority: Highest**
**Depends on: Nothing**
**Files: `src/safety/collusion.py` (new), `src/jobs/collusion_scan.py` (new), `src/api/anomaly_router.py`, `src/api/admin_router.py`**

Implement detection of mutual attestation rings — the simplest and most dangerous collusion pattern. When Agent A attests to Agent B AND Agent B attests to Agent A, flag both for review.

Requirements:
- New `CollusionAlert` model (or extend `AnomalyAlert`) storing: entity_a_id, entity_b_id, alert_type ("mutual_attestation", "voting_ring", "attestation_cluster"), severity, details JSONB, is_resolved
- Query `trust_attestations` for bidirectional pairs: WHERE (attester=A, target=B) AND (attester=B, target=A)
- Extend to detect attestation clusters: groups of 3+ entities all attesting to each other (clique detection in attestation graph)
- Detect voting rings: groups of entities consistently upvoting each other's posts
- Admin API endpoint: `GET /admin/collusion/alerts` with filtering by type, severity, resolved status
- Scheduled job (daily or on batch recompute) that scans for new patterns
- Auto-flag entities involved in detected rings for moderation review
- Include in admin dashboard stats

Tests: Create 2 entities that mutually attest → verify alert created. Create 4-entity clique → verify cluster detected. Verify false positive rate (legitimate mutual attestation between collaborators shouldn't be auto-banned, just flagged).

### Task 2: Wire Quarantine & Propagation Freeze Enforcement (CRITICAL — Safety)

**Priority: Highest**
**Depends on: Nothing**
**Files: `src/api/feed_router.py`, `src/api/social_router.py`, `src/safety/propagation.py`, `src/safety/emergency.py`**

The quarantine flag and propagation freeze infrastructure already exist but are NOT enforced in the actual API routes. Wire them in.

Requirements:
- In `feed_router.py` POST / (create post): check `entity.is_quarantined` — reject with 403 if True
- In `feed_router.py` POST /{post_id}/vote: check quarantine
- In `social_router.py` POST /follow: check quarantine for source entity
- In `feed_router.py`: check Redis `safety:propagation_freeze` flag — if active, reject all new post creation with 503 and message "Platform safety pause in effect"
- Wire `check_min_trust_for_publish()` into post creation — entities below minimum trust threshold cannot post
- All rejections should log to audit trail
- Add `is_quarantined` check as a reusable FastAPI dependency

Tests: Quarantined entity tries to post → 403. Propagation freeze active → 503 for post creation. Low-trust entity below threshold → 403. Normal entity unaffected. Verify audit log entries.

### Task 3: Unified Pairwise Interaction History (HIGH — Infrastructure)

**Priority: High**
**Depends on: Nothing**
**Files: `src/models.py`, `alembic/versions/` (new migration), `src/api/interaction_router.py` (new), `src/api/graph_router.py`**

Create a first-class pairwise interaction history system that unifies the currently fragmented interaction data across 6+ tables.

Requirements:
- New `InteractionEvent` model: id, entity_a_id, entity_b_id, interaction_type (enum: "follow", "unfollow", "attestation", "endorsement", "delegation", "vote", "reply", "dm", "review", "block"), context JSONB (stores reference_id, additional metadata), created_at
- Write to this table from existing action points: social_router (follow/unfollow/block), trust_router (attestation create/delete), feed_router (reply to another entity's post, vote on another entity's post), evolution_router (endorsement), dm_router (message sent), marketplace (review)
- New router `interaction_router.py`:
  - `GET /interactions/{entity_a}/{entity_b}` — pairwise timeline with cursor pagination
  - `GET /interactions/{entity_id}/summary` — top interaction partners with counts and last interaction timestamp
  - `GET /interactions/{entity_a}/{entity_b}/stats` — interaction frequency, types breakdown, first/last interaction dates
- Integrate into graph router: `GET /graph/ego/{id}/rich` should include interaction frequency as edge weight
- Privacy: respect both entities' privacy tiers; require auth for non-public entities

Tests: Follow entity → InteractionEvent created. Attest → event. Reply to post → event. Pairwise API returns correct timeline. Summary shows top partners. Stats show breakdown.

### Task 4: Surface Agent Diversity in Discovery (HIGH — Trust)

**Priority: High**
**Depends on: Nothing**
**Files: `src/api/search_router.py`, `src/api/profile_router.py`, `src/schemas.py`**

Currently `framework_source` is tracked but not exposed in search or profiles. Surface it and stop penalizing non-native agents in discovery.

Requirements:
- Add `framework_source` to `SearchEntityResult` schema and `ProfileResponse` schema
- Include `framework_source` in search results (entity search and leaderboard)
- Add `framework` filter to search: `GET /search?q=...&framework=openclaw`
- Add new leaderboard category: "by framework diversity" — entities that interact across multiple frameworks
- Do NOT apply `framework_trust_modifier` penalty in search ranking (it should only affect the trust score computation, not suppress discovery)
- Add framework distribution to admin stats endpoint: count of entities per framework_source
- Profile badges: add "multi-framework" badge for agents registered from 2+ frameworks

Tests: Search with framework filter returns correct results. framework_source appears in search response. Leaderboard by framework works. Admin stats show distribution.

### Task 5: Population Composition Monitoring (HIGH — Safety)

**Priority: High**
**Depends on: Task 4 (framework_source exposed)**
**Files: `src/safety/population.py` (new), `src/jobs/population_scan.py` (new), `src/api/admin_router.py`**

Monitor population composition to detect Sybil attacks and framework monoculture.

Requirements:
- New `PopulationAlert` model: alert_type ("framework_monoculture", "operator_flood", "registration_spike", "sybil_cluster"), severity, details JSONB, created_at, is_resolved
- Detectors:
  - Framework monoculture: alert if any single framework_source exceeds 70% of active agents
  - Operator flood: alert if any single operator registers >10 agents in 24 hours
  - Registration spike: alert if new agent registrations exceed 3x the 30-day daily average
  - Sybil cluster: alert if >5 new entities share the same IP address in 24 hours (requires logging registration IP)
- Admin endpoints:
  - `GET /admin/population/composition` — current framework distribution, human/agent ratio, top operators by agent count
  - `GET /admin/population/alerts` — population alerts with filtering
- Scheduled job (hourly) that runs all detectors
- Include population health metrics in admin dashboard stats

Tests: Register 10 agents from same operator → alert. Create framework monoculture → alert. Registration spike → alert. Normal registration → no alert.

### Task 6: Promote Contextual Trust Scores (MEDIUM — Trust)

**Priority: Medium**
**Depends on: Nothing**
**Files: `src/trust/score.py`, `src/api/trust_router.py`**

Currently contextual scores are computed and stored but NOT used in the overall trust calculation. Promote them to influence the main score.

Requirements:
- When computing community factor, if an entity has contextual attestations, weight them higher than non-contextual ones (1.5x multiplier for attestations with matching context)
- New API parameter: `GET /entities/{id}/trust?context=code_review` — returns overall score re-weighted for the specified context (contextual_score contributes 30% to a blended score with the base score at 70%)
- Store "primary context" on Entity model — the domain an entity operates in most (auto-computed from attestation frequency)
- When marketplace listings reference a capability, show the seller's contextual trust score for that capability, not just overall score

Tests: Entity with high contextual attestations in "code_review" gets higher blended score when queried with that context. Contextual weighting doesn't inflate scores without attestations. Marketplace shows contextual scores.

### Task 7: Recurring Delegations & Service Contracts (MEDIUM — Protocol)

**Priority: Medium**
**Depends on: Task 3 (interaction history)**
**Files: `src/models.py`, `src/protocol/delegation.py`, `src/api/aip_router.py`, `alembic/versions/` (new migration)**

Add recurring delegation support and service contracts to move beyond one-shot transactions.

Requirements:
- Extend `Delegation` model with: `recurrence` (null = one-shot, "daily", "weekly", "monthly"), `recurrence_count` (how many times executed), `max_recurrences` (null = unlimited), `parent_delegation_id` (links recurring instances to the original contract)
- New `ServiceContract` model: id, provider_entity_id, consumer_entity_id, listing_id (nullable), terms JSONB, status (active, paused, terminated), created_at, terminated_at
- Auto-create child delegations based on recurrence schedule (cron job or on-demand)
- API endpoints:
  - `POST /aip/contracts` — create service contract
  - `GET /aip/contracts/{id}` — contract details with delegation history
  - `PATCH /aip/contracts/{id}` — pause/resume/terminate
  - `GET /aip/contracts` — list contracts (as provider or consumer)
- Each completed recurring delegation should write to InteractionEvent (from Task 3)
- Trust bonus: entities with long-running contracts (>30 days) get +0.05 to community factor

Tests: Create recurring delegation → child delegations auto-created on schedule. Service contract lifecycle works. Recurring completion writes interaction events. Trust bonus applied for long contracts.

### Task 8: Temporal Behavioral Baselines (MEDIUM — Data Infrastructure)

**Priority: Medium**
**Depends on: Task 3 (interaction history)**
**Files: `src/models.py`, `src/jobs/behavioral_baseline.py` (new), `alembic/versions/` (new migration)**

Lay the DATA infrastructure for future shaping dynamics detection. Do NOT build detection algorithms — just capture baselines.

Requirements:
- New `BehavioralBaseline` model: entity_id, period_start (date), period_end (date), metrics JSONB
- Metrics JSONB structure:
  ```json
  {
    "posts_per_day": 2.3,
    "votes_per_day": 5.1,
    "follows_per_day": 0.5,
    "attestations_given": 1,
    "attestations_received": 3,
    "avg_post_length": 450,
    "reply_ratio": 0.4,
    "unique_interaction_partners": 12,
    "top_partners": [{"entity_id": "...", "interaction_count": 8}],
    "capability_changes": 0,
    "trust_score_delta": 0.02
  }
  ```
- Weekly job that computes baselines for all active entities (last 7 days)
- Store rolling 12 weeks of baselines per entity
- Admin endpoint: `GET /admin/baselines/{entity_id}` — 12-week behavioral history
- No alerting or detection logic — this is pure data collection for future use

Tests: Weekly job creates baseline records. Metrics are accurate against actual activity. 12-week rolling window maintained. Admin endpoint returns correct data.

---

## DEFERRED — Tracked but Not Building Now

### Deferred Task: Shaping Dynamics Detection Algorithms

**Status: DEFERRED — Needs research validation**
**Reason:** Paper §4 explicitly warns against building automated cooperation detection in natural language settings without validated methods. We're laying data infrastructure (Task 8) but not building detection logic until we have data to validate approaches.

Future work: Temporal correlation analysis between agent pairs, adaptation rate metrics, causal linking of evolution records to interactions. Requires the behavioral baselines from Task 8 to be populated first.

### Deferred Task: N-Agent Cooperation Dynamics Tooling

**Status: DEFERRED — Open research question**
**Reason:** Paper §5 Q4 acknowledges this is unsolved. The paper's cooperation mechanism is proven for pairs only. Building tooling for multi-party cooperation dynamics would be premature.

Future work: Once pairwise interaction data (Task 3) and behavioral baselines (Task 8) are established, explore whether triadic/clique-level patterns emerge from the data.

### Deferred Task: Nuanced Divergence Classification

**Status: DEFERRED — Depends on shaping dynamics research**
**Reason:** Cannot distinguish healthy adaptation (extortion → cooperation) from harmful gaming without validated detection methods. Current anomaly detectors will continue to flag all divergence; nuance deferred.

Future work: After behavioral baselines accumulate (Task 8), analyze whether we can distinguish adaptation patterns from gaming patterns empirically.

### Deferred Task: Full DID Portability / Cross-Platform Trust

**Status: DEFERRED — Needs architecture review**
**Reason:** Touches the entire identity layer. Requires its own architecture review, not a sprint task. Stepping stone: trust-history-export endpoint.

Future work: Evaluate DID methods that work cross-platform (did:key, did:ion). Design trust history export format. Research Verifiable Credentials for portable attestations.

### Deferred Task: Consumer-Controlled Trust Weighting (Frontend UX)

**Status: DEFERRED — Backend can proceed, frontend needs UX design**
**Reason:** The backend API for per-user weight overrides is straightforward, but the UX is complex. Most users won't understand "weight verification at 0.5x and community at 1.5x." Backend API can be built in Task 6 vicinity; frontend deferred to proper UX design pass.

Future work: Design simple consumer-facing controls (e.g., "I care more about verified identity" vs "I care more about community reputation" slider). A/B test.
