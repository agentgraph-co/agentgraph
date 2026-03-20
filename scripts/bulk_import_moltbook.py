"""Bulk import Moltbook agents into AgentGraph.

Imports 700K+ agents efficiently using batched raw SQL with ON CONFLICT
DO NOTHING for idempotency. Each imported agent gets an Entity, TrustScore,
and provisional DID document.

Targets ~30 minutes for 700K agents (vs ~97 hours with single-bot import).

Usage:
    # Dry run with limit
    python3 scripts/bulk_import_moltbook.py --dry-run --limit 100

    # Import from JSON file (1000 per batch)
    python3 scripts/bulk_import_moltbook.py --input-file moltbook_dump.json

    # Staged import (1K -> 10K -> 100K -> all)
    python3 scripts/bulk_import_moltbook.py --input-file moltbook_dump.json --staged

    # Resume after interruption
    python3 scripts/bulk_import_moltbook.py --input-file moltbook_dump.json --resume

    # Use seed profiles (for testing)
    python3 scripts/bulk_import_moltbook.py --seed
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bulk_import_moltbook")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MOLTBOOK_TRUST_MODIFIER = 0.65
_MOLTBOOK_BASE_TRUST = 0.20  # Low base trust for unverified moltbook agents
_NAMESPACE_MOLTBOOK = uuid.UUID("a3e6f8c1-2b4d-4f5e-9a7c-8d1e3f5b7c9d")
_DID_METHOD = "did:web:agentgraph.co:moltbook"

# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------
_DEFAULT_DB_URL = "postgresql+asyncpg://localhost:5432/agentgraph_staging"


def _resolve_db_url() -> str:
    """Resolve DATABASE_URL from environment, normalizing driver prefix."""
    env_url = os.environ.get("DATABASE_URL", "")
    if env_url:
        if env_url.startswith("postgresql://"):
            env_url = env_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif env_url.startswith("postgres://"):
            env_url = env_url.replace("postgres://", "postgresql+asyncpg://", 1)
        return env_url
    return _DEFAULT_DB_URL


# ---------------------------------------------------------------------------
# UUID generation (deterministic for idempotency)
# ---------------------------------------------------------------------------
def moltbook_entity_uuid(moltbook_id: str) -> uuid.UUID:
    """Generate a deterministic UUID for a Moltbook agent.

    Uses uuid5 with a fixed namespace so re-running the import
    produces the same UUIDs and ON CONFLICT DO NOTHING works.
    """
    return uuid.uuid5(_NAMESPACE_MOLTBOOK, f"moltbook:{moltbook_id}")


def moltbook_trust_uuid(entity_id: uuid.UUID) -> uuid.UUID:
    """Deterministic UUID for the trust_score row."""
    return uuid.uuid5(_NAMESPACE_MOLTBOOK, f"trust:{entity_id}")


def moltbook_did_uuid(entity_id: uuid.UUID) -> uuid.UUID:
    """Deterministic UUID for the DID document row."""
    return uuid.uuid5(_NAMESPACE_MOLTBOOK, f"did:{entity_id}")


# ---------------------------------------------------------------------------
# Profile normalization
# ---------------------------------------------------------------------------
def _normalize_profile(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a raw Moltbook profile dict into import-ready fields.

    Returns None if the profile is invalid (missing required fields).
    """
    moltbook_id = raw.get("moltbook_id") or raw.get("id") or raw.get("username")
    if not moltbook_id:
        return None

    username = raw.get("username", "")
    display_name = raw.get("display_name") or raw.get("name") or username or "Unknown"
    # Truncate to 100 chars (Entity.display_name limit)
    display_name = display_name[:100]

    bio = raw.get("bio") or raw.get("description") or ""
    # Truncate long bios
    if len(bio) > 5000:
        bio = bio[:5000]

    skills = raw.get("skills") or raw.get("capabilities") or []
    avatar_url = raw.get("avatar_url")
    if avatar_url and len(avatar_url) > 500:
        avatar_url = None

    source_url = raw.get("profile_url") or raw.get("url") or f"https://moltbook.com/{username}"

    return {
        "moltbook_id": str(moltbook_id),
        "username": username,
        "display_name": display_name,
        "bio": bio,
        "skills": skills,
        "avatar_url": avatar_url,
        "source_url": source_url,
        "version": raw.get("version"),
    }


# ---------------------------------------------------------------------------
# Data source loaders
# ---------------------------------------------------------------------------
def load_from_json(filepath: str) -> list[dict[str, Any]]:
    """Load profiles from a JSON file (array of objects)."""
    logger.info("Loading profiles from %s ...", filepath)
    with open(filepath) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data).__name__}")
    logger.info("Loaded %d raw profiles from file", len(data))
    return data


def load_from_seed() -> list[dict[str, Any]]:
    """Load profiles from the built-in seed_profiles module."""
    # Import locally to avoid requiring the full src package
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from src.bridges.moltbook.seed_profiles import MOLTBOOK_SEED_PROFILES
    logger.info("Loaded %d seed profiles", len(MOLTBOOK_SEED_PROFILES))
    return list(MOLTBOOK_SEED_PROFILES)


# ---------------------------------------------------------------------------
# Batch helpers
# ---------------------------------------------------------------------------
def _chunk(items: list[Any], size: int) -> Iterator[list[Any]]:
    """Yield successive chunks of `size` from `items`."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _build_entity_row(
    profile: dict[str, Any], now: datetime
) -> dict[str, Any]:
    """Build a dict of column values for the entities table."""
    eid = moltbook_entity_uuid(profile["moltbook_id"])
    did_web = f"{_DID_METHOD}:{profile['moltbook_id']}"
    return {
        "id": str(eid),
        "type": "agent",
        "display_name": profile["display_name"],
        "bio_markdown": profile["bio"],
        "avatar_url": profile["avatar_url"],
        "did_web": did_web,
        "capabilities": json.dumps(profile["skills"]),
        "framework_source": "moltbook",
        "framework_trust_modifier": _MOLTBOOK_TRUST_MODIFIER,
        "source_url": profile["source_url"],
        "source_type": "moltbook",
        "is_active": True,
        "is_admin": False,
        "is_quarantined": False,
        "is_provisional": True,
        "privacy_tier": "public",
        "operator_approved": False,
        "email_verified": False,
        "created_at": now,
        "updated_at": now,
    }


def _build_trust_row(
    profile: dict[str, Any], now: datetime
) -> dict[str, Any]:
    """Build a dict of column values for the trust_scores table."""
    eid = moltbook_entity_uuid(profile["moltbook_id"])
    tid = moltbook_trust_uuid(eid)
    score = _MOLTBOOK_BASE_TRUST * _MOLTBOOK_TRUST_MODIFIER  # 0.13
    return {
        "id": str(tid),
        "entity_id": str(eid),
        "score": round(score, 4),
        "components": json.dumps({
            "base": _MOLTBOOK_BASE_TRUST,
            "framework_modifier": _MOLTBOOK_TRUST_MODIFIER,
            "verification": 0.0,
            "activity": 0.0,
            "import_source": "moltbook_bulk",
        }),
        "contextual_scores": json.dumps({}),
        "computed_at": now,
        "updated_at": now,
    }


def _build_did_row(
    profile: dict[str, Any], now: datetime
) -> dict[str, Any]:
    """Build a dict of column values for the did_documents table."""
    eid = moltbook_entity_uuid(profile["moltbook_id"])
    did_id = moltbook_did_uuid(eid)
    did_uri = f"{_DID_METHOD}:{profile['moltbook_id']}"
    document = {
        "@context": ["https://www.w3.org/ns/did/v1"],
        "id": did_uri,
        "controller": did_uri,
        "verificationMethod": [],
        "service": [
            {
                "id": f"{did_uri}#moltbook",
                "type": "MoltbookProfile",
                "serviceEndpoint": profile["source_url"],
            }
        ],
        "agentgraph:importSource": "moltbook",
        "agentgraph:importedAt": now.isoformat(),
    }
    return {
        "id": str(did_id),
        "entity_id": str(eid),
        "did_uri": did_uri,
        "document": json.dumps(document),
        "did_status": "PROVISIONAL",
        "created_at": now,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------
_INSERT_ENTITIES_SQL = """
INSERT INTO entities (
    id, type, display_name, bio_markdown, avatar_url, did_web,
    capabilities, framework_source, framework_trust_modifier,
    source_url, source_type, is_active, is_admin, is_quarantined,
    is_provisional, privacy_tier, operator_approved, email_verified,
    created_at, updated_at
) VALUES (
    :id, :type, :display_name, :bio_markdown, :avatar_url, :did_web,
    :capabilities::jsonb, :framework_source, :framework_trust_modifier,
    :source_url, :source_type, :is_active, :is_admin, :is_quarantined,
    :is_provisional, :privacy_tier, :operator_approved, :email_verified,
    :created_at, :updated_at
)
ON CONFLICT (id) DO NOTHING
"""

_INSERT_TRUST_SQL = """
INSERT INTO trust_scores (
    id, entity_id, score, components, contextual_scores, computed_at, updated_at
) VALUES (
    :id, :entity_id, :score, :components::jsonb, :contextual_scores::jsonb,
    :computed_at, :updated_at
)
ON CONFLICT (entity_id) DO NOTHING
"""

_INSERT_DID_SQL = """
INSERT INTO did_documents (
    id, entity_id, did_uri, document, did_status, created_at, updated_at
) VALUES (
    :id, :entity_id, :did_uri, :document::jsonb, :did_status,
    :created_at, :updated_at
)
ON CONFLICT (entity_id) DO NOTHING
"""

_COUNT_EXISTING_SQL = """
SELECT COUNT(*) FROM entities
WHERE framework_source = 'moltbook' AND source_type = 'moltbook'
"""


# ---------------------------------------------------------------------------
# Main import logic
# ---------------------------------------------------------------------------
async def run_import(
    profiles: list[dict[str, Any]],
    batch_size: int,
    dry_run: bool,
    resume: bool,
    db_url: str,
) -> dict[str, Any]:
    """Execute the bulk import.

    Returns a stats dict with counts and timing.
    """
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        db_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )

    stats = {
        "total_input": len(profiles),
        "normalized": 0,
        "skipped_invalid": 0,
        "skipped_existing": 0,
        "inserted_entities": 0,
        "inserted_trust": 0,
        "inserted_did": 0,
        "batch_errors": 0,
        "elapsed_seconds": 0.0,
    }

    t_start = time.monotonic()

    # Normalize all profiles
    normalized: list[dict[str, Any]] = []
    for raw in profiles:
        p = _normalize_profile(raw)
        if p is None:
            stats["skipped_invalid"] += 1
        else:
            normalized.append(p)
    stats["normalized"] = len(normalized)
    logger.info(
        "Normalized %d profiles (%d invalid, skipped)",
        len(normalized),
        stats["skipped_invalid"],
    )

    if not normalized:
        logger.warning("No valid profiles to import")
        stats["elapsed_seconds"] = time.monotonic() - t_start
        await engine.dispose()
        return stats

    # If resume mode, filter out already-imported moltbook_ids
    if resume:
        logger.info("Resume mode: checking for existing entities...")
        existing_ids: set = set()
        async with engine.begin() as conn:
            result = await conn.execute(
                sa_text(
                    "SELECT source_url FROM entities "
                    "WHERE framework_source = 'moltbook' AND source_type = 'moltbook'"
                )
            )
            for row in result:
                existing_ids.add(row[0])
        before = len(normalized)
        normalized = [p for p in normalized if p["source_url"] not in existing_ids]
        stats["skipped_existing"] = before - len(normalized)
        logger.info(
            "Resume: %d already exist, %d remaining to import",
            stats["skipped_existing"],
            len(normalized),
        )

    if dry_run:
        logger.info("=== DRY RUN === Would import %d entities", len(normalized))
        for i, p in enumerate(normalized[:10]):
            eid = moltbook_entity_uuid(p["moltbook_id"])
            logger.info(
                "  [%d] %s (id=%s, source=%s)",
                i + 1,
                p["display_name"],
                eid,
                p["source_url"],
            )
        if len(normalized) > 10:
            logger.info("  ... and %d more", len(normalized) - 10)
        stats["elapsed_seconds"] = time.monotonic() - t_start
        await engine.dispose()
        return stats

    # Import in batches
    now = datetime.now(timezone.utc)
    total = len(normalized)
    batch_num = 0

    for chunk in _chunk(normalized, batch_size):
        batch_num += 1
        batch_start = time.monotonic()
        try:
            entity_rows = [_build_entity_row(p, now) for p in chunk]
            trust_rows = [_build_trust_row(p, now) for p in chunk]
            did_rows = [_build_did_row(p, now) for p in chunk]

            async with engine.begin() as conn:
                # Insert entities
                await conn.execute(sa_text(_INSERT_ENTITIES_SQL), entity_rows)

                # Insert trust scores
                await conn.execute(sa_text(_INSERT_TRUST_SQL), trust_rows)

                # Insert DID documents
                await conn.execute(sa_text(_INSERT_DID_SQL), did_rows)

            inserted = len(chunk)  # approximate; ON CONFLICT skips are silent
            stats["inserted_entities"] += inserted
            stats["inserted_trust"] += inserted
            stats["inserted_did"] += inserted

            done = min(batch_num * batch_size, total)
            pct = (done / total) * 100
            batch_elapsed = time.monotonic() - batch_start
            rate = len(chunk) / batch_elapsed if batch_elapsed > 0 else 0
            logger.info(
                "Imported %d/%d (%.1f%%) — batch %d: %d rows in %.2fs (%.0f/s)",
                done,
                total,
                pct,
                batch_num,
                len(chunk),
                batch_elapsed,
                rate,
            )
        except Exception as exc:
            stats["batch_errors"] += 1
            done = min(batch_num * batch_size, total)
            logger.error(
                "Batch %d failed (rows %d-%d): %s",
                batch_num,
                done - len(chunk) + 1,
                done,
                exc,
            )
            # Continue with next batch
            continue

    stats["elapsed_seconds"] = time.monotonic() - t_start

    # Get final count
    try:
        async with engine.begin() as conn:
            result = await conn.execute(sa_text(_COUNT_EXISTING_SQL))
            row = result.fetchone()
            total_in_db = row[0] if row else 0
        logger.info("Total Moltbook entities now in DB: %d", total_in_db)
    except Exception as exc:
        logger.warning("Could not count final entities: %s", exc)

    await engine.dispose()
    return stats


# ---------------------------------------------------------------------------
# Staged import
# ---------------------------------------------------------------------------
async def run_staged_import(
    profiles: list[dict[str, Any]],
    batch_size: int,
    db_url: str,
) -> None:
    """Run import in stages: 1K, 10K, 100K, then all.

    Pauses between stages for manual verification.
    """
    stages = [1_000, 10_000, 100_000, len(profiles)]
    for stage_limit in stages:
        if stage_limit > len(profiles):
            stage_limit = len(profiles)
        logger.info("=" * 60)
        logger.info("STAGE: Importing first %d profiles", stage_limit)
        logger.info("=" * 60)

        subset = profiles[:stage_limit]
        stats = await run_import(
            profiles=subset,
            batch_size=batch_size,
            dry_run=False,
            resume=True,  # Always resume in staged mode
            db_url=db_url,
        )
        _print_stats(stats)

        if stage_limit >= len(profiles):
            logger.info("All profiles imported. Done.")
            break

        logger.info(
            "Stage complete. Next stage: %d profiles.",
            min(stages[stages.index(stage_limit) + 1], len(profiles)),
        )
        try:
            response = input("Continue to next stage? [y/N] ").strip().lower()
            if response != "y":
                logger.info("Stopped at user request after %d profiles.", stage_limit)
                break
        except (EOFError, KeyboardInterrupt):
            logger.info("\nAborted by user.")
            break


# ---------------------------------------------------------------------------
# Stats display
# ---------------------------------------------------------------------------
def _print_stats(stats: dict[str, Any]) -> None:
    """Print import statistics."""
    elapsed = stats["elapsed_seconds"]
    rate = stats["normalized"] / elapsed if elapsed > 0 else 0
    logger.info("=" * 50)
    logger.info("Import Statistics:")
    logger.info("  Total input profiles:   %d", stats["total_input"])
    logger.info("  Normalized (valid):     %d", stats["normalized"])
    logger.info("  Skipped (invalid):      %d", stats["skipped_invalid"])
    logger.info("  Skipped (existing):     %d", stats["skipped_existing"])
    logger.info("  Inserted entities:      ~%d", stats["inserted_entities"])
    logger.info("  Inserted trust scores:  ~%d", stats["inserted_trust"])
    logger.info("  Inserted DID docs:      ~%d", stats["inserted_did"])
    logger.info("  Batch errors:           %d", stats["batch_errors"])
    logger.info("  Elapsed time:           %.2fs", elapsed)
    logger.info("  Throughput:             %.0f profiles/s", rate)
    logger.info("=" * 50)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk import Moltbook agents into AgentGraph",
    )
    parser.add_argument(
        "--input-file",
        help="Path to JSON file containing array of agent profiles",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Use built-in seed profiles (50 agents) for testing",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of entities per batch (default: 1000)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of profiles to import (for testing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and count profiles without inserting",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Import in stages (1K, 10K, 100K, all) with pauses",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip entities that already exist in the DB",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override DATABASE_URL (default: from env or staging DB)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # Resolve database URL
    if args.database_url:
        db_url = args.database_url
    else:
        db_url = _resolve_db_url()
    logger.info("Database: %s", db_url.split("@")[-1] if "@" in db_url else db_url)

    # Load profiles
    if args.input_file:
        profiles = load_from_json(args.input_file)
    elif args.seed:
        profiles = load_from_seed()
    else:
        logger.error("Must specify --input-file or --seed")
        sys.exit(1)

    # Apply limit
    if args.limit is not None:
        profiles = profiles[: args.limit]
        logger.info("Limited to %d profiles", len(profiles))

    if not profiles:
        logger.error("No profiles to import")
        sys.exit(1)

    # Run import
    if args.staged and not args.dry_run:
        await run_staged_import(
            profiles=profiles,
            batch_size=args.batch_size,
            db_url=db_url,
        )
    else:
        stats = await run_import(
            profiles=profiles,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            resume=args.resume,
            db_url=db_url,
        )
        _print_stats(stats)


if __name__ == "__main__":
    asyncio.run(main())
