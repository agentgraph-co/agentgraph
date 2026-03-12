"""Remove seeded human accounts (@example.com) from any database.

Safely deletes seed data while preserving real user accounts.
Deletes related data (posts, votes, relationships, etc.) first.

Usage:
    python3 scripts/remove_seed_humans.py                    # staging (default)
    DATABASE_URL=postgresql+asyncpg://...  python3 scripts/remove_seed_humans.py
"""
from __future__ import annotations

import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_DB_URL = "postgresql+asyncpg://localhost:5432/agentgraph_staging"
_env_url = os.environ.get("DATABASE_URL", "")

if _env_url:
    if _env_url.startswith("postgresql://"):
        _env_url = _env_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif _env_url.startswith("postgres://"):
        _env_url = _env_url.replace("postgres://", "postgresql+asyncpg://", 1)

DATABASE_URL = _env_url or _DEFAULT_DB_URL

# The seed humans all use @example.com — real users do NOT
SEED_EMAIL_DOMAIN = "@example.com"


async def _safe_delete(db, sql: str, params: dict, label: str) -> int:
    """Run a delete inside a savepoint so failures don't abort the txn."""
    try:
        nested = await db.begin_nested()
        r = await db.execute(text(sql), params)
        await nested.commit()
        if r.rowcount > 0:
            print(f"  Deleted {r.rowcount} rows from {label}")
        return r.rowcount
    except Exception:
        await nested.rollback()
        return 0


async def main() -> None:
    print(f"Connecting to: {DATABASE_URL.split('@')[-1]}")  # hide credentials

    engine = create_async_engine(DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        async with db.begin():
            # Find seed humans by email domain
            result = await db.execute(
                text(
                    "SELECT id, email, display_name FROM entities "
                    "WHERE email LIKE :pattern"
                ),
                {"pattern": f"%{SEED_EMAIL_DOMAIN}"},
            )
            seed_humans = result.all()

            if not seed_humans:
                print("No seed humans found. Nothing to do.")
                await engine.dispose()
                return

            print(f"\nFound {len(seed_humans)} seed human(s) to remove:")
            for row in seed_humans:
                print(f"  - {row.display_name} ({row.email})")

            ids = [str(row.id) for row in seed_humans]

            # Delete related data in dependency order
            # Each uses a savepoint so missing tables/columns don't abort
            _del = "DELETE FROM {} WHERE {} = ANY(:ids)"
            cleanup_ops = [
                (_del.format("votes", "entity_id"), "votes"),
                (_del.format("notifications", "entity_id"), "notifications"),
                (_del.format("moderation_flags", "reporter_entity_id"), "mod_flags (reporter)"),
                (_del.format("moderation_flags", "target_entity_id"), "mod_flags (target)"),
                (_del.format("audit_logs", "entity_id"), "audit_logs"),
                (_del.format("analytics_events", "entity_id"), "analytics_events"),
                (_del.format("api_keys", "entity_id"), "api_keys"),
                (_del.format("webhook_subscriptions", "entity_id"), "webhook_subs"),
                (_del.format("did_documents", "entity_id"), "did_documents"),
                (_del.format("evolution_records", "entity_id"), "evolution_records"),
                (_del.format("trust_scores", "entity_id"), "trust_scores"),
                (_del.format("email_verifications", "entity_id"), "email_verifications"),
                (_del.format("entity_relationships", "source_entity_id"), "rels (source)"),
                (_del.format("entity_relationships", "target_entity_id"), "rels (target)"),
                # Votes on their posts
                (
                    "DELETE FROM votes WHERE post_id IN "
                    "(SELECT id FROM posts WHERE author_entity_id = ANY(:ids))",
                    "votes on seed posts",
                ),
                # Replies to their posts
                (
                    "DELETE FROM posts WHERE parent_post_id IN "
                    "(SELECT id FROM posts WHERE author_entity_id = ANY(:ids))",
                    "replies to seed posts",
                ),
                # Their posts
                ("DELETE FROM posts WHERE author_entity_id = ANY(:ids)", "posts"),
                # Marketplace listings
                ("DELETE FROM listings WHERE owner_entity_id = ANY(:ids)", "listings"),
                # Organizations
                ("DELETE FROM organizations WHERE created_by = ANY(:ids)", "organizations"),
            ]

            for sql, label in cleanup_ops:
                await _safe_delete(db, sql, {"ids": ids}, label)

            # Finally delete the entities themselves
            count = await _safe_delete(
                db,
                "DELETE FROM entities WHERE id = ANY(:ids)",
                {"ids": ids},
                "entities",
            )
            print(f"\n  Removed {count} seed human entities.")

    await engine.dispose()
    print("\nDone! Seed humans removed.")


if __name__ == "__main__":
    asyncio.run(main())
