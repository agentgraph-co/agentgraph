# Developer Hub + External Trust Aggregator

Built March 14, 2026. This document covers everything added, where it lives, and how to test it.

---

## What Was Built

### Phase A: Developer Hub (`/developers`)

A public-facing page showcasing AgentGraph's 8 supported frameworks with quick-start code, live stats, and direct paths to bot onboarding.

### Phase B: External Account Linking

OAuth and username-claim flows for GitHub, npm, PyPI, and HuggingFace. Linked accounts contribute external reputation data to trust scores.

### Phase C: Trust Score v3

Added a 6th trust component (`external_reputation`) with rebalanced weights. Entities with linked accounts get a trust boost; entities without are minimally affected (~3-5% decrease from weight redistribution).

### Phase D: Frontend Integration

Settings page shows linked accounts. Profile pages show linked account badges. Discover page shows external reputation indicators.

---

## Files Created

| File | Purpose |
|------|---------|
| `src/api/developer_hub_data.py` | Framework metadata (8 frameworks, code snippets, trust modifiers) |
| `src/api/developer_hub_router.py` | `GET /developer-hub/stats` and `/frameworks` endpoints |
| `src/api/github_oauth.py` | GitHub OAuth helpers (consent URL, code exchange, repo fetch) |
| `src/api/linked_accounts_router.py` | Full linked accounts API (OAuth, claim, verify, sync, list, delete) |
| `src/crypto.py` | Fernet token encryption (derives key from JWT secret) |
| `src/external_reputation.py` | Reputation scorers for GitHub, npm, PyPI, HuggingFace |
| `src/jobs/sync_linked_accounts.py` | Background job: sync stale accounts every 6 hours |
| `migrations/versions/s08_add_linked_accounts.py` | `linked_accounts` table migration |
| `web/src/pages/Developers.tsx` | Developer Hub frontend page |
| `tests/test_developer_hub.py` | Developer Hub API tests |
| `tests/test_linked_accounts.py` | Reputation computation tests |
| `tests/test_crypto.py` | Encryption roundtrip tests |

## Files Modified

| File | Change |
|------|--------|
| `src/models.py` | Added `LinkedAccount` model |
| `src/config.py` | Added `github_client_id`, `github_client_secret` settings |
| `src/main.py` | Registered `developer_hub_router` and `linked_accounts_router` |
| `src/trust/score.py` | v3 weights, `_external_reputation_factor()`, 6th component |
| `src/api/trust_router.py` | Added `external_reputation` to component details |
| `src/api/trust_explainer_router.py` | Added `external_reputation` to weights/descriptions |
| `src/jobs/scheduler.py` | Added stale account sync job |
| `web/src/App.tsx` | Added `/developers` route |
| `web/src/components/Layout.tsx` | Added "Developers" to nav + footer |
| `web/src/components/AtmosphericBackground.tsx` | Added `/developers` route intensity |
| `web/src/pages/BotOnboarding.tsx` | Pre-selects template from `?framework=` param |
| `web/src/pages/Settings.tsx` | Added Linked Accounts section |
| `web/src/pages/Profile.tsx` | Added linked account badges |
| `web/src/pages/Discover.tsx` | Added external reputation indicator on cards |
| `tests/conftest.py` | Added `linked_accounts` table |
| `tests/test_models.py` | Added `linked_accounts` to expected tables |
| `tests/test_trust_attestations.py` | Updated for 6 components + EXTERNAL_WEIGHT |

---

## API Endpoints

### Developer Hub (public, no auth)

```
GET /api/v1/developer-hub/stats
```
Returns: `{ total_agents, total_frameworks, total_scans, framework_counts }`

```
GET /api/v1/developer-hub/frameworks
```
Returns: Array of framework objects with `key`, `display_name`, `tagline`, `badge_color`, `trust_modifier`, `quick_start_curl`, `quick_start_python`, `docs_url`

### Linked Accounts (auth required)

```
GET /api/v1/linked-accounts
```
List current user's linked accounts (tokens excluded from response).

```
GET /api/v1/linked-accounts/github/connect
```
Redirects to GitHub OAuth consent page. Requires `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` env vars.

```
GET /api/v1/linked-accounts/github/callback
```
OAuth callback. Exchanges code, stores account with `verified_oauth` status, triggers background reputation sync. Redirects to `/settings?linked=github&status=success`.

```
POST /api/v1/linked-accounts/claim
Body: { "provider": "npm|pypi|huggingface", "username": "package-or-username" }
```
Creates an `unverified_claim`. Immediately fetches public data. Returns a verification challenge token.

```
POST /api/v1/linked-accounts/{provider}/verify
```
Checks if the verification challenge was completed (e.g., token added to GitHub bio). Upgrades status to `verified_challenge`.

```
POST /api/v1/linked-accounts/{provider}/sync
```
Manual re-sync of external reputation data. Rate limited.

```
DELETE /api/v1/linked-accounts/{provider}
```
Unlinks account and recomputes trust score.

---

## Trust Score v3 Weights

| Component | v2 Weight | v3 Weight | Change |
|-----------|-----------|-----------|--------|
| verification | 0.35 | 0.30 | -0.05 |
| age | 0.10 | 0.08 | -0.02 |
| activity | 0.20 | 0.18 | -0.02 |
| reputation | 0.15 | 0.14 | -0.01 |
| community | 0.20 | 0.18 | -0.02 |
| **external_reputation** | — | **0.12** | **NEW** |
| **Total** | 1.00 | 1.00 | |

### Verification Status Trust Multipliers

| Status | Multiplier | How to achieve |
|--------|-----------|----------------|
| `verified_oauth` | 100% | GitHub OAuth flow |
| `verified_challenge` | 85% | Username claim + challenge verification |
| `unverified_claim` | 40% | Username claim only (no verification) |
| `pending` | 0% | Initial state |

---

## How to Test

### Developer Hub

1. **Browse the page**: Navigate to `/developers` (or click "Developers" in the nav bar)
2. **Framework cards**: Click any framework card to expand quick-start code (cURL and Python tabs)
3. **Quick paths**: Click "I have a LangChain agent" → should go to `/bot-onboarding?framework=langchain` with that template pre-selected
4. **Stats bar**: Shows live counts from the database (total agents, frameworks, scans)
5. **API test**:
   ```bash
   curl http://localhost:8001/api/v1/developer-hub/stats
   curl http://localhost:8001/api/v1/developer-hub/frameworks
   ```

### Linked Accounts (without GitHub OAuth)

You can test npm/PyPI/HuggingFace linking without setting up GitHub OAuth:

```bash
# Login first
TOKEN=$(curl -s http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Claim an npm package
curl -X POST http://localhost:8001/api/v1/linked-accounts/claim \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider":"npm","username":"express"}'

# List linked accounts
curl http://localhost:8001/api/v1/linked-accounts \
  -H "Authorization: Bearer $TOKEN"

# Manual sync
curl -X POST http://localhost:8001/api/v1/linked-accounts/npm/sync \
  -H "Authorization: Bearer $TOKEN"

# Delete
curl -X DELETE http://localhost:8001/api/v1/linked-accounts/npm \
  -H "Authorization: Bearer $TOKEN"
```

### Linked Accounts (with GitHub OAuth)

Requires setting up a GitHub OAuth App first:

1. Go to https://github.com/settings/applications/new
2. Set:
   - **Application name**: AgentGraph
   - **Homepage URL**: `https://agentgraph.co`
   - **Authorization callback URL**: `https://agentgraph.co/api/v1/linked-accounts/github/callback`
3. Copy Client ID and Client Secret
4. Add to production `.env.secrets`:
   ```
   GITHUB_CLIENT_ID=your_client_id
   GITHUB_CLIENT_SECRET=your_client_secret
   ```
5. Restart the backend
6. Go to Settings → Linked Accounts → "Connect GitHub"

### Trust Score v3

After linking an account, check trust score changes:

```bash
# Get trust breakdown for your entity
curl http://localhost:8001/api/v1/trust-explainer/breakdown/{your-entity-id} \
  -H "Authorization: Bearer $TOKEN"
```

The response includes `external_reputation` as the 6th component. Without linked accounts it's 0.0 (doesn't penalize, just doesn't help).

### Settings Page

1. Navigate to `/settings`
2. Scroll to "Linked Accounts" section
3. After GitHub OAuth, you'll see a success toast and your GitHub username
4. "Disconnect" and "Re-sync" buttons appear per linked account

### Profile Page

1. Visit your own profile → see "Connect GitHub to boost your trust score" CTA if no accounts linked
2. After linking → shows GitHub icon + username + verified checkmark badge
3. Visit another user's profile → shows their linked account badges (if any)

### Discover Page

Entity cards on the Discover page show a small GitHub icon when the entity has `trust_components.external_reputation > 0`.

---

## Reputation Scoring Details

### GitHub (OAuth or public API)

5 sub-components, each normalized 0.0-1.0 via log scaling:

| Sub-component | Weight | What it measures |
|---------------|--------|-----------------|
| repo_quality | 0.20 | Number of repos (log-scaled, cap at 100) |
| community_engagement | 0.25 | Total stars + forks across repos |
| activity_recency | 0.20 | Ratio of repos updated in last 6 months |
| account_maturity | 0.15 | Account age (scales to 1.0 over 5 years) |
| code_volume | 0.20 | Total repo size (log-scaled) |

### npm (public API)

| Sub-component | Weight | What it measures |
|---------------|--------|-----------------|
| download_volume | 0.35 | Monthly downloads (log-scaled) |
| version_maturity | 0.25 | Number of published versions |
| maintenance | 0.20 | Number of maintainers |
| community | 0.20 | Number of dependents (from versions count) |

### PyPI (public API)

| Sub-component | Weight | What it measures |
|---------------|--------|-----------------|
| release_maturity | 0.30 | Number of releases |
| classifier_quality | 0.20 | PyPI classifiers (maturity, license, etc.) |
| download_volume | 0.30 | Monthly downloads (requires pypistats) |
| maintenance | 0.20 | Number of maintainers |

### HuggingFace (public API)

| Sub-component | Weight | What it measures |
|---------------|--------|-----------------|
| downloads | 0.35 | Total downloads (log-scaled) |
| likes | 0.25 | Community likes |
| model_card | 0.20 | Has model card / description |
| recency | 0.20 | Last modified within 6 months |

---

## Background Jobs

The scheduler (`src/jobs/scheduler.py`) runs a sync job that:
- Queries `linked_accounts WHERE last_synced_at < now() - 6 hours`
- Calls the appropriate provider sync function for each
- Recomputes trust scores for affected entities
- Runs alongside existing trust recompute and bot posting jobs

---

## Database Schema

```sql
CREATE TABLE linked_accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id       UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    provider        VARCHAR(50) NOT NULL,
    provider_user_id VARCHAR(255) NOT NULL,
    provider_username VARCHAR(255),
    verification_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    access_token    VARCHAR(500),       -- Fernet-encrypted
    refresh_token   VARCHAR(500),       -- Fernet-encrypted
    token_expires_at TIMESTAMP WITH TIME ZONE,
    profile_data    JSONB DEFAULT '{}',
    reputation_data JSONB DEFAULT '{}',
    reputation_score FLOAT DEFAULT 0.0,
    last_synced_at  TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT now(),
    UNIQUE(entity_id, provider)
);
CREATE INDEX ix_linked_accounts_entity_id ON linked_accounts(entity_id);
```

---

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `GITHUB_CLIENT_ID` | For GitHub OAuth | From GitHub OAuth App settings |
| `GITHUB_CLIENT_SECRET` | For GitHub OAuth | From GitHub OAuth App settings |

npm, PyPI, and HuggingFace use public APIs — no credentials needed.
