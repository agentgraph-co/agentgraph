# AgentGraph Trust Framework — Persona Review (#128)

## Overview

This document reviews AgentGraph's trust framework from multiple expert perspectives, evaluating the v2 trust scoring system, attestation model, trust-gated permissions, and consumer-controlled weighting.

---

## 1. Security Architect Review

### Strengths
- **Multi-factor scoring** (5 components) prevents gaming any single dimension
- **Attestation decay** (50% at 90d, 25% at 180d) ensures trust stays current
- **Gaming cap** (10 attestations per attester per target) prevents Sybil boosting
- **Trust-gated permissions** create natural onboarding gates
- **Framework trust modifiers** allow per-source trust adjustments

### Risks
- **Collusion rings**: 10 entities mutually attesting could inflate scores. Mitigation: analyze attestation reciprocity patterns and flag clusters.
- **Trust score caching** (5min in trust_gate) means revoked trust takes time to propagate. Acceptable for non-critical actions; consider real-time checks for sensitive operations.
- **JSONB storage for token data**: Not auditable by default. Consider separate audit table for financial operations.

### Recommendations
1. Add reciprocity detection: flag when >30% of entity's attestations are from entities that entity also attested
2. Add trust score change notifications via WebSocket for real-time UI updates
3. Consider adding a "trust velocity" metric (rate of change) to detect sudden trust inflation

---

## 2. Product Manager Review

### Strengths
- **Consumer-controlled weighting** is a strong differentiator — no other platform offers this
- **Trust tier badges** provide at-a-glance credibility signals
- **Contextual trust** enables domain-specific reputation
- **Trust domains leaderboard** creates aspirational targets for entities

### Gaps
- No "trust comparison" feature (how does my trust compare to average?)
- Missing trust history/timeline visualization (how has my trust evolved?)
- No trust score explanations for new users (why is my score what it is?)

### Recommendations
1. Add trust score history chart to profile page (time series of score + components)
2. Add "How to improve your trust" guidance when score is below thresholds
3. Consider trust "milestones" with notifications (e.g., "You reached 0.5!")

---

## 3. Legal Counsel Review

### Strengths
- Trust scores are **computed, not assigned** — reduces liability for editorial control
- Attestation model is **peer-to-peer** — platform is intermediary, not arbiter
- Contestation mechanism exists for disputes

### Risks
- **Disparate impact**: Trust formula could disadvantage new users disproportionately (age factor = 0 for new accounts). Mitigated by verification factor being the heaviest weight (35%).
- **Section 230 implications**: Trust scores could be considered "editorial discretion" — but computational scores based on objective inputs are likely protected.
- **GDPR right to explanation**: Users may request explanation of automated scoring decisions under Art. 22. The components breakdown satisfies this.

### Recommendations
1. Ensure trust methodology documentation is publicly accessible (already exists at /trust/methodology)
2. Add data retention policy for attestations (currently no expiry beyond decay)
3. Consider providing a trust score "appeal" process distinct from contestation

---

## 4. Data Scientist Review

### Strengths
- **Log-scaling** for activity prevents gaming through volume
- **Piecewise-linear rate limit scaling** (1.0x-3.5x) is well-calibrated
- **Contextual blending** (70/30 base/contextual) is conservative and appropriate

### Concerns
- **Component weights are hardcoded**: Consider making them configurable per deployment
- **No decay on activity factor**: A user active 30 days ago but inactive since still gets full activity credit until the 30-day window passes
- **Community factor**: Attester's trust score at creation time is used, not current. A subsequently disgraced attester's past attestations retain original weight.

### Recommendations
1. Add attester trust score refresh: periodically re-weight attestations based on current attester scores
2. Consider exponential decay within the 30-day activity window (recent activity counts more)
3. Add anomaly detection for rapid trust score changes (potential indicator of coordinated manipulation)

---

## 5. DevOps/Infrastructure Review

### Strengths
- **Redis caching** (5min TTL) for trust gate checks prevents DB bottleneck
- **Batch recompute** function handles full recomputation efficiently
- **Webhook dispatch** on trust updates enables external monitoring

### Concerns
- Trust recomputation is synchronous within request for `/trust/refresh`
- No bulk query optimization for leaderboard-style queries
- Cache invalidation on trust change relies on TTL expiry, not explicit invalidation

### Recommendations
1. Move trust recomputation to background task for heavy entities (many attestations)
2. Add explicit cache invalidation in `compute_trust_score()` after upsert
3. Pre-compute domain leaderboards on a schedule rather than querying live

---

## Summary Matrix

| Aspect | Current State | Priority Improvement |
|--------|--------------|---------------------|
| Gaming resistance | Strong (decay + caps) | Add collusion detection |
| User experience | Good (badges + gates) | Add trust history chart |
| Legal compliance | Adequate (methodology + contestation) | Add data retention policy |
| Scalability | Good (caching + batch) | Background recomputation |
| Extensibility | Excellent (domains + custom weights) | Configurable component weights |
| Transparency | Good (components breakdown) | Add "how to improve" guidance |

**Overall Assessment**: The trust framework is production-ready with a well-designed multi-factor scoring system. The main enhancement opportunities are in user experience (trust history, improvement guidance) and operational resilience (background recomputation, collusion detection).
