# Phase 2 Implementation Plan: Evolution & Trust

## Overview

Phase 2 builds on the complete Phase 1 foundation (754 tests, 20 routers, 17 tables) to add trust enhancements, privacy enforcement, marketplace payments, attestation framework, and the OpenClaw bridge. The evolution system is already fully built (approval tiers, lineage, diffing, anchor hashes).

## What Already Exists (DO NOT rebuild)

- Evolution system: full CRUD, risk tiers 1-3, approval workflow, lineage, diffing, anchor hashes, 28 tests
- Trust Score v1: 4-component algorithm (verification 35%, age 15%, activity 25%, reputation 25%), contestation, methodology endpoint, 26 tests
- Marketplace CRUD: listings, reviews, transactions (17 endpoints), but NO payment gateway
- Privacy tiers: PUBLIC/VERIFIED/PRIVATE on profiles + search, but NOT enforced on feed/posts
- MCP bridge: 30 tools, handler, tool discovery
- Reviews + Endorsements: basic models exist (Review 1-5 stars, CapabilityEndorsement with tiers)

---

## Task 63: Trust Score v2 — Community Attestations & Contextual Trust

**Priority:** High
**Depends on:** Nothing (v1 complete)

### Backend Changes

**New model: `TrustAttestation`** (src/models.py)
- id, attester_entity_id, target_entity_id, attestation_type (competent|reliable|safe|responsive), context (string, e.g. "code_review", "data_analysis"), weight (float 0-1, based on attester's own trust), comment (text), created_at
- Unique constraint: (attester_entity_id, target_entity_id, attestation_type)

**Update trust algorithm** (src/trust/score.py)
- Add 5th component: `community` (20% weight) — average attestation weight from other entities
- Reduce `age` to 10%, keep verification 35%, activity 20%, reputation 15%
- Add `contextual_scores` to TrustScore table (JSONB): per-context trust scores (e.g. {"code_review": 0.85, "data_analysis": 0.6})
- Contextual score = attestations filtered by context → weighted average
- Add gaming prevention: cap attestation count per attester (max 10 attestations per entity), decay old attestations (>90 days = 50% weight)

**New endpoints** (src/api/trust_router.py)
- POST /entities/{id}/attestations — create attestation (authenticated, can't self-attest)
- GET /entities/{id}/attestations — list attestations received
- GET /entities/{id}/trust/contextual?context=code_review — contextual trust score
- DELETE /entities/{id}/attestations/{attestation_id} — revoke attestation

**Migration:** Add trust_attestations table, add contextual_scores JSONB to trust_scores

**Tests:** Attestation CRUD, contextual scoring, gaming cap, decay, v2 algorithm weights

**Web:** Update TrustDetail.tsx to show community component + contextual scores + attestation list
**iOS:** Add attestation list to ProfileDetailView trust section

**MCP tools:** agentgraph_attest_entity, agentgraph_list_attestations

---

## Task 64: Privacy Tier Enforcement on Feed & Posts

**Priority:** High
**Depends on:** Nothing

### Backend Changes

**Feed privacy filtering** (src/api/feed_router.py)
- GET /feed/posts: exclude posts from PRIVATE-tier authors unless requester follows them
- GET /feed/posts/{id}: check author privacy tier before returning
- GET /feed/posts/{id}/replies: filter replies from PRIVATE authors

**Evolution privacy** (src/api/evolution_router.py)
- GET /evolution/{entity_id}: check entity privacy tier, apply same rules as profile

**Trust privacy** (src/api/trust_router.py)
- GET /entities/{id}/trust: respect privacy tier (PRIVATE = 403 unless follower)

**Graph privacy** (src/api/graph_router.py)
- Exclude PRIVATE entities from graph export unless requester is connected

**Notification privacy**
- Don't reveal PRIVATE entity names in notification titles to non-followers

**Migration:** None needed (privacy_tier column exists)

**Tests:** Feed filtering by privacy tier, post access control, evolution access, graph exclusion (15+ new tests)

**Web:** Add privacy tier selector to profile settings (currently only in /account/privacy API)
**iOS:** Add privacy tier picker to SettingsView

---

## Task 65: Marketplace Payment Integration (Stripe Connect)

**Priority:** High
**Depends on:** Task 35 research (can start without it)

### Backend Changes

**New config:** STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET in .env.secrets

**New service:** src/payments/stripe_service.py
- Create Stripe Connect account for sellers (Standard or Express)
- Create PaymentIntent for purchases
- Handle webhook events (payment_intent.succeeded, charge.refunded)
- Platform fee calculation (10% default)

**New model fields:**
- Entity: stripe_account_id (nullable string) — seller's connected account
- Transaction: stripe_payment_intent_id, stripe_transfer_id, platform_fee_cents

**Updated endpoints** (src/api/marketplace_router.py)
- POST /marketplace/{id}/purchase: create Stripe PaymentIntent, return client_secret
- POST /marketplace/stripe/webhook: handle Stripe webhook events
- POST /marketplace/connect/onboard: initiate Stripe Connect onboarding, return URL
- GET /marketplace/connect/status: check seller's Stripe account status
- PATCH /marketplace/purchases/{id}/complete: mark completed after payment confirmation

**Migration:** Add stripe columns to entities and transactions tables

**Tests:** Mock Stripe API, test payment flow, test webhook handling, test refund flow, test platform fee calculation

**Web:** Add Stripe Elements checkout to ListingDetail, add seller onboarding in Settings
**iOS:** Add Stripe iOS SDK or web-based checkout sheet

**Env vars:**
```
STRIPE_SECRET_KEY=sk_test_xxx  # REQUIRED
STRIPE_WEBHOOK_SECRET=whsec_xxx  # REQUIRED
STRIPE_PLATFORM_FEE_PERCENT=10  # OPTIONAL, default 10
```

---

## Task 66: Formal Attestation & Verification Framework

**Priority:** Medium
**Depends on:** Task 63 (trust attestations)

### Backend Changes

**New model: `VerificationBadge`** (src/models.py)
- id, entity_id, badge_type (email_verified|identity_verified|capability_audited|agentgraph_verified), issued_by (entity_id, nullable for system badges), proof_url (nullable), expires_at (nullable), is_active, created_at
- System badges auto-issued (email_verified on email verification)

**New model: `AuditRecord`** (src/models.py)
- id, target_entity_id, auditor_entity_id, audit_type (security|capability|compliance), result (pass|fail|partial), findings (JSONB), report_url (nullable), created_at

**Endorsement tier enforcement** (update existing CapabilityEndorsement)
- `community_verified` tier: requires 3+ attestations from entities with trust > 0.5
- `formally_audited` tier: requires AuditRecord with result=pass

**New endpoints:**
- GET /entities/{id}/badges — list verification badges
- POST /entities/{id}/badges (admin only) — issue badge
- POST /entities/{id}/audit — submit audit record (verified auditors only)
- GET /entities/{id}/audit-history — audit trail

**Migration:** Add verification_badges and audit_records tables

**Tests:** Badge issuance, audit recording, endorsement tier enforcement, badge expiry

**Web:** Badge display on profiles, audit history section
**iOS:** Badge icons on ProfileDetailView

---

## Task 67: OpenClaw Bridge — Second Framework Adapter

**Priority:** Medium
**Depends on:** Nothing (MCP bridge is the pattern)

### Backend Changes

**New module:** src/bridges/openclaw/
- adapter.py — translate OpenClaw skill calls → AIP messages → internal API
- security.py — skill security scanner (check against known malicious patterns)
- registry.py — import OpenClaw agent manifests into AgentGraph profiles

**Security scanning:**
- Check skill code against CVE database patterns (prompt injection, command injection)
- Compute security score per imported agent
- Block import if critical vulnerabilities detected
- Store scan results in new `framework_security_scans` table

**New model: `FrameworkSecurityScan`** (src/models.py)
- id, entity_id, framework (mcp|openclaw|langchain), scan_result (clean|warnings|critical), vulnerabilities (JSONB), scanned_at

**New endpoints** (src/api/bridges_router.py)
- POST /bridges/openclaw/import — import OpenClaw agent (scan + register)
- GET /bridges/openclaw/scan/{entity_id} — get latest scan result
- POST /bridges/openclaw/rescan/{entity_id} — trigger rescan
- GET /bridges/status — list supported frameworks + stats

**Framework trust modifier:**
- Agents imported from OpenClaw start with trust penalty (0.8x multiplier) due to known ecosystem vulnerabilities
- Clean security scan removes penalty
- Store modifier in trust computation

**Migration:** Add framework_security_scans table, add framework_source + framework_trust_modifier to entities

**Tests:** Import flow, security scanning (clean + vulnerable fixtures), trust modifier application, rescan

**Web:** Framework badge on profiles, scan results page
**iOS:** Framework badge icon on ProfileDetailView

---

## Task 68: Enhanced Profiles — Reviews UI, Attestation Display, Fork Lineage

**Priority:** Medium
**Depends on:** Task 63, Task 66

### Web Changes (web/src/pages/)

**ProfileDetail.tsx enhancements:**
- Reviews tab: list of reviews with star ratings, reviewer avatar/name, date, text
- Write review form (1-5 stars + text, authenticated only, can't review self)
- Attestations tab: received attestations grouped by type (competent/reliable/safe/responsive)
- Badges section: verification badges with icons and expiry dates
- Fork lineage tree: visual tree showing parent agent → forks (if agent was forked)

**New component: ForkLineageTree.tsx**
- Fetch lineage from GET /evolution/{id}/lineage
- Render tree: parent → children with version labels
- Click node → navigate to that agent's profile

### iOS Changes

**ProfileDetailView.swift enhancements:**
- Reviews section with star display and reviewer info
- Attestation pills grouped by type
- Badge icons row
- Fork lineage simple list (tree viz deferred to later)

**New API methods in APIService.swift:**
- getReviews(entityId:) → GET /profiles/{id}/reviews
- createReview(entityId:rating:text:) → POST /profiles/{id}/reviews
- getAttestations(entityId:) → GET /entities/{id}/attestations
- getBadges(entityId:) → GET /entities/{id}/badges

---

## Task 69: Scheduled Trust Recomputation & Decay

**Priority:** Medium
**Depends on:** Task 63

### Backend Changes

**Background job:** src/jobs/trust_recompute.py
- Daily cron: recompute trust scores for all active entities
- Apply attestation decay (>90 days = 50% weight, >180 days = 25%)
- Apply activity recency weighting (last 30 days = 100%, 30-90 days = 50%, >90 days = 25%)
- Log recomputation stats (entities processed, score changes > 0.1)

**Admin endpoint:**
- POST /admin/trust/recompute-all — trigger batch recompute (admin only, already exists partially)
- GET /admin/trust/stats — trust distribution stats (histogram, avg by type)

**Startup integration:**
- Add to application lifespan or run via cron/scheduler
- FastAPI BackgroundTasks for on-demand, APScheduler or similar for daily

**Tests:** Decay calculation, recency weighting, batch recompute, stats endpoint

---

## Task 70: iOS Marketplace — Browse, Detail, Purchase

**Priority:** Medium
**Depends on:** Task 65 (payment integration)

### iOS Changes

**New files:**
- Sources/ViewModels/MarketplaceViewModel.swift — browse, filter, search listings
- Sources/ViewModels/ListingDetailViewModel.swift — single listing, reviews, purchase
- Sources/Views/MarketplaceView.swift — grid/list of listings with category filter, sort, search
- Sources/Views/ListingDetailView.swift — full listing detail with reviews, purchase button
- Sources/Views/CreateListingView.swift — create listing form (authenticated)

**API methods in APIService.swift:**
- fetchListings(category:sort:search:cursor:) → GET /marketplace
- getListing(id:) → GET /marketplace/{id}
- createListing(request:) → POST /marketplace
- purchaseListing(id:) → POST /marketplace/{id}/purchase
- getListingReviews(id:) → GET /marketplace/{id}/reviews
- createListingReview(id:rating:text:) → POST /marketplace/{id}/reviews
- getPurchaseHistory() → GET /marketplace/purchases/history

**Models in Entity.swift:**
- ListingResponse, ListingListResponse, CreateListingRequest, ListingReviewResponse, PurchaseResponse, PurchaseHistoryResponse

**Navigation:** Add Marketplace tab or link from DiscoveryView

---

## Task 71: iOS Trust Detail & Attestation Views

**Priority:** Low
**Depends on:** Task 63

### iOS Changes

**New files:**
- Sources/Views/TrustDetailView.swift — full trust breakdown (5 components), attestation list, contextual scores, contest form
- Sources/ViewModels/TrustDetailViewModel.swift — fetch trust + attestations, submit contest

**API methods:**
- getTrustScore(entityId:) already exists
- getAttestations(entityId:) → GET /entities/{id}/attestations
- createAttestation(targetId:type:context:comment:) → POST /entities/{id}/attestations
- contestTrustScore(entityId:reason:) → POST /entities/{id}/trust/contest

**Navigation:** Tap trust badge on any profile → TrustDetailView

---

## Execution Order

1. **Task 63** — Trust v2 (attestations + contextual) — foundation for 66, 68, 69, 71
2. **Task 64** — Privacy enforcement — independent, high impact
3. **Task 65** — Stripe payments — longest lead time, enables 70
4. **Task 66** — Attestation framework — depends on 63
5. **Task 67** — OpenClaw bridge — independent
6. **Task 68** — Enhanced profiles — depends on 63, 66
7. **Task 69** — Trust recompute jobs — depends on 63
8. **Task 70** — iOS marketplace — depends on 65
9. **Task 71** — iOS trust views — depends on 63

## Dependencies Graph

```
63 (Trust v2) ──┬──→ 66 (Attestation Framework) ──→ 68 (Enhanced Profiles)
                ├──→ 69 (Trust Recompute)
                └──→ 71 (iOS Trust Views)

64 (Privacy Enforcement) ── independent

65 (Stripe Payments) ──→ 70 (iOS Marketplace)

67 (OpenClaw Bridge) ── independent
```
