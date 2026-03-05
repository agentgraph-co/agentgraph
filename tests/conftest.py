from __future__ import annotations

import os

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://localhost:5432/agentgraph_test"
)

# Tables to truncate before the test session (order respects FK constraints).
_TABLES = [
    "content_links",
    "behavioral_baselines", "interaction_events", "service_contracts",
    "population_alerts", "attestation_providers", "formal_attestations",
    "anomaly_alerts", "propagation_alerts", "org_usage_records",
    "delegations", "agent_capability_registry", "organization_memberships",
    "organizations", "audit_records", "verification_badges",
    "framework_security_scans", "moderation_appeals", "analytics_events",
    "submolt_memberships", "direct_messages", "conversations",
    "entity_blocks", "reviews", "trust_attestations",
    "capability_endorsements", "post_edits", "bookmarks",
    "webhook_subscriptions", "notification_preferences", "notifications",
    "disputes", "transactions", "listing_reviews", "listings",
    "token_blacklist", "password_reset_tokens", "email_verifications",
    "audit_logs", "evolution_records", "moderation_flags",
    "api_keys", "did_documents", "trust_scores", "votes", "posts",
    "entity_relationships", "submolts", "entities",
]


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _clean_db_once():
    """Truncate all tables once at the start of the test session.

    This removes stale committed data from prior runs so that each test
    starts from a known-clean database (combined with the per-test
    transaction rollback in the ``db`` fixture).
    """
    engine = create_async_engine(DB_URL, echo=False)
    async with engine.begin() as conn:
        # Ensure newer tables exist (migration may not have run on test DB)
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS interaction_events ("
            "  id UUID PRIMARY KEY,"
            "  entity_a_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,"
            "  entity_b_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,"
            "  interaction_type VARCHAR(50) NOT NULL,"
            "  context JSONB,"
            "  created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_interaction_entity_a "
            "ON interaction_events (entity_a_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_interaction_entity_b "
            "ON interaction_events (entity_b_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_interaction_type "
            "ON interaction_events (interaction_type)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_interaction_created_at "
            "ON interaction_events (created_at)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_interaction_pairwise "
            "ON interaction_events (entity_a_id, entity_b_id, interaction_type)"
        ))
        # Ensure primary_context column exists on entities (migration m01)
        await conn.execute(text(
            "ALTER TABLE entities ADD COLUMN IF NOT EXISTS "
            "primary_context VARCHAR(100)"
        ))
        # Ensure recurring delegation columns exist (migration n01)
        await conn.execute(text(
            "ALTER TABLE delegations ADD COLUMN IF NOT EXISTS "
            "recurrence VARCHAR(20)"
        ))
        await conn.execute(text(
            "ALTER TABLE delegations ADD COLUMN IF NOT EXISTS "
            "recurrence_count INTEGER DEFAULT 0 NOT NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE delegations ADD COLUMN IF NOT EXISTS "
            "max_recurrences INTEGER"
        ))
        await conn.execute(text(
            "ALTER TABLE delegations ADD COLUMN IF NOT EXISTS "
            "parent_delegation_id UUID REFERENCES delegations(id) ON DELETE SET NULL"
        ))
        # Ensure population_alerts table exists (migration m02)
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS population_alerts ("
            "  id UUID PRIMARY KEY,"
            "  alert_type VARCHAR(50) NOT NULL,"
            "  severity VARCHAR(20) NOT NULL,"
            "  details JSONB,"
            "  is_resolved BOOLEAN NOT NULL DEFAULT false,"
            "  created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
            ")"
        ))
        # Ensure service_contracts table exists (migration n01)
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS service_contracts ("
            "  id UUID PRIMARY KEY,"
            "  provider_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,"
            "  consumer_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,"
            "  listing_id UUID REFERENCES listings(id) ON DELETE SET NULL,"
            "  terms JSONB,"
            "  status VARCHAR(20) NOT NULL DEFAULT 'active',"
            "  paused_by UUID,"
            "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "  terminated_at TIMESTAMPTZ"
            ")"
        ))
        # Ensure behavioral_baselines table exists (migration n02)
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS behavioral_baselines ("
            "  id UUID PRIMARY KEY,"
            "  entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,"
            "  period_start DATE NOT NULL,"
            "  period_end DATE NOT NULL,"
            "  metrics JSONB NOT NULL,"
            "  created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
            ")"
        ))
        # Ensure agent heartbeat columns exist (migration o01)
        await conn.execute(text(
            "ALTER TABLE entities ADD COLUMN IF NOT EXISTS "
            "last_seen_at TIMESTAMPTZ"
        ))
        await conn.execute(text(
            "ALTER TABLE entities ADD COLUMN IF NOT EXISTS "
            "agent_status VARCHAR(20)"
        ))
        # Ensure attestation_providers table exists
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS attestation_providers ("
            "  id UUID PRIMARY KEY,"
            "  operator_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,"
            "  provider_name VARCHAR(200) NOT NULL UNIQUE,"
            "  provider_url VARCHAR(500),"
            "  description TEXT,"
            "  supported_types JSONB DEFAULT '[]'::jsonb,"
            "  api_key_hash VARCHAR(128) NOT NULL,"
            "  is_active BOOLEAN NOT NULL DEFAULT false,"
            "  attestation_count INTEGER NOT NULL DEFAULT 0,"
            "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_attestation_providers_operator "
            "ON attestation_providers (operator_entity_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_attestation_providers_active "
            "ON attestation_providers (is_active)"
        ))
        # Ensure formal_attestations table exists (attestation framework)
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS formal_attestations ("
            "  id UUID PRIMARY KEY,"
            "  issuer_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,"
            "  subject_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,"
            "  attestation_type VARCHAR(50) NOT NULL,"
            "  evidence TEXT,"
            "  expires_at TIMESTAMPTZ,"
            "  is_revoked BOOLEAN NOT NULL DEFAULT false,"
            "  revoked_at TIMESTAMPTZ,"
            "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "  CONSTRAINT uq_formal_attestation"
            "    UNIQUE (issuer_entity_id, subject_entity_id, attestation_type)"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_formal_attestations_issuer "
            "ON formal_attestations (issuer_entity_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_formal_attestations_subject "
            "ON formal_attestations (subject_entity_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_formal_attestations_type "
            "ON formal_attestations (attestation_type)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_formal_attestations_revoked "
            "ON formal_attestations (is_revoked)"
        ))
        # Ensure content_links table exists (migration r02)
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS content_links ("
            "  id UUID PRIMARY KEY,"
            "  source_type VARCHAR(30) NOT NULL,"
            "  source_id UUID NOT NULL,"
            "  target_type VARCHAR(30) NOT NULL,"
            "  target_id UUID NOT NULL,"
            "  link_type VARCHAR(30) NOT NULL,"
            "  created_by UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,"
            "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "  CONSTRAINT ck_content_link_source_type"
            "    CHECK (source_type IN ('post', 'entity', 'evolution_record', 'listing')),"
            "  CONSTRAINT ck_content_link_target_type"
            "    CHECK (target_type IN ('post', 'entity', 'evolution_record', 'listing')),"
            "  CONSTRAINT ck_content_link_link_type"
            "    CHECK (link_type IN ('mentions', 'references', 'related', 'replies_about')),"
            "  CONSTRAINT uq_content_link"
            "    UNIQUE (source_type, source_id, target_type, target_id, link_type)"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_content_links_source "
            "ON content_links (source_type, source_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_content_links_target "
            "ON content_links (target_type, target_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_content_links_created_by "
            "ON content_links (created_by)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_content_links_link_type "
            "ON content_links (link_type)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_content_links_created_at "
            "ON content_links (created_at)"
        ))
        await conn.execute(
            text("TRUNCATE " + ", ".join(_TABLES) + " CASCADE")
        )
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    """Clear rate limiter state (in-memory + Redis) and relax auth limit."""
    from src.api.rate_limit import _limiter
    from src.config import settings

    await _limiter.clear_all()
    original = settings.rate_limit_auth_per_minute
    settings.rate_limit_auth_per_minute = 100
    # Clear caches to prevent cross-test contamination
    from src import cache
    await cache.invalidate_pattern("insights:*")
    await cache.invalidate_pattern("search:*")
    await cache.invalidate_pattern("activity:*")
    yield
    settings.rate_limit_auth_per_minute = original
    await _limiter.clear_all()


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(DB_URL, echo=False)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
    await engine.dispose()
