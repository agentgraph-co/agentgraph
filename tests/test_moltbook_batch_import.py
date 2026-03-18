"""Tests for the Moltbook batch import pipeline."""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bridges.moltbook.batch_import import run_batch_import
from src.bridges.moltbook.seed_profiles import MOLTBOOK_SEED_PROFILES
from src.models import Entity


def test_seed_profiles_valid():
    """Seed profiles have required fields."""
    assert len(MOLTBOOK_SEED_PROFILES) >= 50
    for p in MOLTBOOK_SEED_PROFILES:
        assert p.get("moltbook_id")
        assert p.get("display_name") or p.get("username")
        assert isinstance(p.get("skills", []), list)


@pytest.mark.asyncio
async def test_batch_import_creates_entities(db: AsyncSession):
    """Batch import creates provisional entities."""
    result = await run_batch_import(db, limit=5)
    assert result["imported"] >= 1
    assert result["discovered"] == 5

    # Verify entities created
    entities = await db.execute(
        select(Entity).where(Entity.framework_source == "moltbook")
    )
    moltbook_entities = entities.scalars().all()
    assert len(moltbook_entities) >= 1
    for e in moltbook_entities:
        assert e.is_provisional is True
        assert e.framework_trust_modifier == 0.65
        assert e.did_web.startswith("did:web:agentgraph.co:moltbook:")
        assert e.source_type == "moltbook"


@pytest.mark.asyncio
async def test_batch_import_dedup(db: AsyncSession):
    """Running twice does not duplicate imports."""
    await run_batch_import(db, limit=5)
    r2 = await run_batch_import(db, limit=5)
    assert r2["skipped_duplicate"] > 0


@pytest.mark.asyncio
async def test_batch_import_skips_critical_security(db: AsyncSession):
    """Profiles with critical security issues are skipped."""
    result = await run_batch_import(db, limit=50)
    assert result["skipped_security"] >= 1
