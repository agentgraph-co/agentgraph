from __future__ import annotations

import os

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://localhost:5432/agentgraph"
)

# Tables to truncate before the test session (order respects FK constraints).
_TABLES = [
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
    # Clear insights/analytics cache to prevent cross-test contamination
    from src import cache
    await cache.invalidate_pattern("insights:*")
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
