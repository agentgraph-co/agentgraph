# Deep Dive Audit — Prioritized Findings

These are actionable findings from a 7-agent deep dive audit of the AgentGraph codebase. Tasks should be created in priority order. All tasks are code changes — no research or legal tasks.

---

## Task 1: Fix Light Mode Visual Issues (User-Reported)
Priority: HIGH
The hero face silhouette is completely invisible in light mode. Decorative animations (ParticleField, MyceliumLines, GradientBreath in Motion.tsx) use hardcoded dark-mode-optimized colors that vanish on light backgrounds. The light mode background (#f8fafc) is pure white with no warmth/depth. The Graph.tsx edge legend uses hardcoded Catppuccin dark-mode hex colors instead of importing from graphTheme.ts. TrustDetail.tsx hardcodes dark-mode Catppuccin colors for progress bars and attestation badges.

Changes needed:
- web/src/pages/Home.tsx: Verify hero-art-blend CSS class works (mix-blend-multiply in light mode)
- web/src/components/Motion.tsx: Make ParticleField, MyceliumLines, GradientBreath accept theme-aware colors. Extract default color arrays to module-level constants to prevent re-render loops (colors array dependency bug at line 394).
- web/src/pages/Graph.tsx lines 243-265: Import edgeColor() from graphTheme.ts and use useTheme() instead of hardcoded hex colors in the edge type legend
- web/src/pages/TrustDetail.tsx lines 41-73: Create a theme-aware color mapping for COMPONENT_INFO and ATTESTATION_TYPE_LABELS instead of hardcoded Catppuccin hex colors
- web/src/index.css: Add subtle warm tint to light mode background — change --color-background from #f8fafc to #f5f7fa or similar, add gentle gradient or surface differentiation

## Task 2: Security — Password Reset Session Invalidation
Priority: HIGH (Security)
The reset_password endpoint in src/api/auth_router.py (line 283) changes the password hash but does NOT set the token:inv:{entity_id} cache key to invalidate existing sessions. Compare with change_password in account_router.py (lines 109-119) which correctly does this. An attacker who compromised a session maintains access even after the user resets their password.

Fix: After resetting password, add cache.set(f"token:inv:{entity.id}", int(time.time()), ttl=settings.access_token_expire_minutes * 60) — same pattern as change_password.

## Task 3: Security — Rate Limit X-Forwarded-For Bypass
Priority: HIGH (Security)
src/api/rate_limit.py line 137: _get_client_ip() trusts X-Forwarded-For header blindly. An attacker can set any IP to bypass per-IP rate limiting. Add a trusted_proxies configuration. Only trust X-Forwarded-For when the direct client IP is in the trusted proxies list. Add TRUSTED_PROXIES setting to config.py.

## Task 4: Security — Gitignore Staging JWT Secret
Priority: HIGH (Security)
.env.staging contains JWT_SECRET=***REMOVED*** and is NOT in .gitignore. Anyone with repo access can forge staging tokens. Add .env.staging to .gitignore, or move JWT_SECRET to .env.secrets which is already gitignored.

## Task 5: Infrastructure — Add Global Exception Handlers
Priority: HIGH
src/main.py has no @app.exception_handler() registrations. Unhandled exceptions return FastAPI's default unstructured 500 response with no request_id for debugging. Add handlers for Exception, RequestValidationError, and StarletteHTTPException that return consistent JSON with request_id.

## Task 6: Infrastructure — Docker Container Runs as Root
Priority: HIGH
The Dockerfile never creates a non-root user. Add: RUN adduser --disabled-password --no-create-home appuser; USER appuser. Also fix the editable pip install (pip install -e ".") which is wrong for production — use pip install ".".

## Task 7: Infrastructure — Replace KEYS Command in Admin Router
Priority: HIGH
src/api/admin_router.py line 525 uses r.keys("rl:*") which is O(N) and blocks the entire Redis instance. Replace with r.scan(match="rl:*", count=100) async iterator, same pattern used in cache.invalidate_pattern.

## Task 8: Database — Add Missing ondelete to 11 ForeignKeys + Migration
Priority: HIGH
11 ForeignKey columns in src/models.py lack ondelete behavior (operator_id, resolved_by, parent_record_id, forked_from_entity_id, approved_by, Dispute FKs, ModerationAppeal.resolved_by, PropagationAlert.issued_by, Organization.created_by). Create a new Alembic migration to ALTER CONSTRAINT on the existing database to add proper ondelete (SET NULL or CASCADE as appropriate). Fix models.py to match.

## Task 9: API — Fix N+1 Queries in org_router and export_router
Priority: HIGH
- org_router.py lines 294-307: list_members does individual db.get(Entity, m.entity_id) per member. Replace with JOIN query.
- export_router.py lines 218-237: DM export does separate query per conversation. Batch-fetch all messages with conversation_id.in_(conv_ids).

## Task 10: API — Add Pagination to Unbounded List Endpoints
Priority: HIGH
These endpoints return all results with no limit/offset:
- GET /agents (agent_router.py lines 207-214)
- GET /marketplace/entity/{id} (marketplace_router.py lines 923-949)
- GET /organizations/{org_id}/members (org_router.py lines 282-307)
- GET /organizations/{org_id}/api-keys (org_router.py lines 520-555)
- GET /admin/safety/alerts (safety_router.py — has limit but no offset)
Add limit: int = Query(50, ge=1, le=200) and offset: int = Query(0, ge=0) parameters.

## Task 11: Code Quality — Consolidate Bridge Security Scanners
Priority: HIGH
5 bridge security scanner files (openclaw, langchain, crewai, autogen, semantic_kernel) in src/bridges/*/security.py are 90%+ identical — ~1,100 lines of copy-paste. Vulnerability/ScanResult dataclasses, BASE_PATTERNS (222 lines), scan_skill() are all duplicated. Extract into src/bridges/base_scanner.py. Each framework scanner becomes ~30 lines defining unique patterns. Similarly, 5 registry files (src/bridges/*/registry.py) are nearly identical ~600 lines. Extract into src/bridges/base_registry.py.

## Task 12: API — Stricter Rate Limit on Export and SSO Endpoints
Priority: MEDIUM
- GET /export/me executes 15+ queries but uses standard rate_limit_reads. Create a rate_limit_export tier (5/hour).
- SSO login/callback endpoints use rate_limit_writes instead of rate_limit_auth. Change to rate_limit_auth.
- POST /agents/register uses rate_limit_writes instead of rate_limit_auth.

## Task 13: Database — Add Missing db.refresh() After Mutations
Priority: MEDIUM
- agent_router.py line 519: setattr + flush without db.refresh(agent) — stale updated_at in response
- profile_router.py line 456: same pattern — stale updated_at
Add await db.refresh(obj) after flush and before returning response in both cases.

## Task 14: Frontend — Add Error Boundary Around ForceGraph
Priority: MEDIUM
ForceGraph2D/ForceGraph3D are third-party canvas/WebGL renderers that can throw if data is malformed or WebGL context is lost. No error boundary protects them. Wrap in a dedicated ErrorBoundary with fallback "Graph could not be rendered." Also add per-route error boundaries around other high-risk pages.

## Task 15: Infrastructure — WebSocket Reliability Improvements
Priority: MEDIUM
Three issues in src/ws.py and ws_router.py:
1. No reconnection loop for Redis subscriber — if Redis disconnects, the worker becomes permanently deaf to cross-worker broadcasts (lines 146-167). Add exponential backoff retry.
2. No backpressure — slow clients block broadcast loop. Wrap send_text in asyncio.wait_for with timeout.
3. ws_router.py lines 84-114: except only catches WebSocketDisconnect. Other exceptions (ConnectionResetError) leak connections. Add broader except handler.

## Task 16: Infrastructure — Health Endpoint Should Return 503 When Degraded
Priority: MEDIUM
src/main.py lines 244-269: /health returns HTTP 200 even when status is "degraded". Load balancers use status codes. Return 503 when degraded.

## Task 17: Code Quality — Extract Shared Admin Check and Password Validator
Priority: MEDIUM
- Admin check _require_admin() is defined in admin_router.py but duplicated inline in 10+ other routers. Move to src/api/deps.py as a shared dependency.
- Password validation logic is triplicated in schemas.py (2x) and account_router.py. Extract to shared validator function.
- Standardize log_action imports to top-level (currently inline in ~15 routers for no reason).

## Task 18: Infrastructure — Add Content-Security-Policy Header
Priority: MEDIUM
src/main.py security headers middleware (lines 144-157) sets X-Content-Type-Options, X-Frame-Options, etc. but NOT Content-Security-Policy. Add CSP: default-src 'self' as baseline for the API.

## Task 19: Frontend — Accessibility Improvements
Priority: MEDIUM
- Range input for autonomy level in Agents.tsx lacks aria-label
- Star rating buttons in ListingDetail.tsx lack aria-label
- Webhook event toggles lack aria-pressed state
- Graph container div has no accessible label (add role="img" aria-label)
- Filter/tab buttons across app lack proper ARIA tab roles
- Leaderboard table lacks caption

## Task 20: Frontend — Standardize Loading States to Skeletons
Priority: LOW
9 pages use plain text "Loading..." instead of skeleton components: Agents, Bookmarks, Leaderboard, Submolts, SubmoltDetail, TransactionHistory, TrustDetail, Webhooks, MyListings. Replace with skeleton loading components for consistency.

## Task 21: Infrastructure — Disable Swagger UI in Production
Priority: MEDIUM
src/main.py lines 91-92: docs_url="/docs" and redoc_url="/redoc" are always enabled. Change to docs_url="/docs" if settings.debug else None.

## Task 22: Database — Add Missing Indexes
Priority: LOW
Missing indexes on frequently-queried columns:
- Dispute.resolved_by (line 670)
- TokenBlacklist.entity_id (line 464)
- ModerationAppeal.appellant_id (line 1131)
Also add updated_at to mutable models that lack it: Dispute, Delegation, WebhookSubscription, Notification.

## Task 23: API — Fix Cluster Endpoint Privacy and Dispute Resolution Logic
Priority: MEDIUM
- graph_router.py lines 453-458: Cluster detail endpoint doesn't apply privacy-tier filter. PRIVATE entities may be exposed. Apply _build_privacy_filter.
- disputes_router.py lines 429-558: Either buyer or seller can unilaterally resolve dispute in their own favor. Require mutual consent or only allow non-initiating party to resolve.

## Task 24: Frontend — Fix setTimeout Memory Leaks
Priority: LOW
Multiple pages have setTimeout calls without cleanup on unmount:
- Toasts.tsx line 23: 4s timer not cancelled
- ResetPassword.tsx line 42: navigate timer not cancelled
- Agents.tsx line 235, Webhooks.tsx line 118: copy timers not cancelled
- Motion.tsx ParticleField line 394: colors array default creates new reference each render, causing teardown/rebuild loop. Make it a module-level constant.

## Task 25: Code Quality — Remove Dead Code and Clean Up
Priority: LOW
- Empty packages: src/identity/, src/social/, src/moderation/ — remove or populate
- v0-references components: move out of web/src/ to docs/
- Commented-out APScheduler code in main.py lines 210-233 — remove
- Unused AuthResponse TypeScript interface in web/src/types/index.ts
- Export router hardcoded limits (5000, 10000, etc.) — extract to named constants
- Version string "0.1.0" duplicated in main.py and pyproject.toml — single source
- Deprecated on_event("shutdown") — migrate to lifespan context manager
- graph_router.py line 656: entity_type regex missing $ anchor
- safety_router.py line 110: deprecated datetime.utcnow()
