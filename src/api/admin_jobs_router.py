from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity, require_admin
from src.database import get_db
from src.jobs.expire_provisional import expire_provisional_agents
from src.models import Entity

router = APIRouter(prefix="/admin/jobs", tags=["admin"])


@router.post("/expire-provisional")
async def trigger_expire_provisional(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger the provisional agent expiration job (admin only)."""
    require_admin(current_entity)
    summary = await expire_provisional_agents(db)
    await db.commit()
    return summary


@router.post("/trust-recompute")
async def trigger_trust_recompute(
    deep: bool = Query(False, description="Use enhanced recompute with decay/recency"),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger trust score recomputation for all active entities (admin only).

    Pass ?deep=true for enhanced recompute with attestation decay and
    activity recency weighting.
    """
    require_admin(current_entity)

    if deep:
        from src.jobs.trust_recompute import run_trust_recompute
        summary = await run_trust_recompute(db)
    else:
        from src.trust.score import batch_recompute
        count = await batch_recompute(db)
        summary = {"entities_processed": count, "mode": "simple"}

    return summary


@router.post("/refresh-attestation-weights")
async def trigger_refresh_attestation_weights(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Re-weight attestations using current attester trust scores (admin only).

    Updates attestation weights that were set at creation time with
    each attester's current trust score.
    """
    require_admin(current_entity)

    from src.trust.score import refresh_attestation_weights
    updated = await refresh_attestation_weights(db)
    return {"attestations_updated": updated}


@router.post("/moltbook-import")
async def trigger_moltbook_import(
    limit: int = Query(10, ge=1, le=50),
    dry_run: bool = Query(False),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger a batch import of Moltbook agents (admin only)."""
    require_admin(current_entity)
    from src.bridges.moltbook.batch_import import run_batch_import

    summary = await run_batch_import(db, limit=limit, dry_run=dry_run)
    if not dry_run:
        await db.commit()
    return summary


@router.get("/moltbook-import/stats")
async def get_moltbook_import_stats(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get Moltbook import statistics (admin only)."""
    require_admin(current_entity)
    from sqlalchemy import func, select

    from src.models import Entity as EntityModel

    total = await db.scalar(
        select(func.count(EntityModel.id)).where(
            EntityModel.framework_source == "moltbook",
        )
    )
    claimed = await db.scalar(
        select(func.count(EntityModel.id)).where(
            EntityModel.framework_source == "moltbook",
            EntityModel.is_provisional.is_(False),
        )
    )
    unclaimed = await db.scalar(
        select(func.count(EntityModel.id)).where(
            EntityModel.framework_source == "moltbook",
            EntityModel.is_provisional.is_(True),
        )
    )
    return {
        "total_imported": total or 0,
        "claimed": claimed or 0,
        "unclaimed": unclaimed or 0,
    }
