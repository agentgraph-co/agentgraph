from __future__ import annotations

import logging
from typing import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.cache import get as cache_get
from src.cache import set as cache_set
from src.database import get_db
from src.models import Entity, TrustScore

logger = logging.getLogger(__name__)

# Trust thresholds for gated actions
TRUST_GATES: dict[str, float] = {
    "post_create": 0.0,
    "post_to_submolt": 0.05,
    "create_listing": 0.15,
    "create_submolt": 0.25,
    "send_message": 0.05,
    "create_webhook": 0.10,
    "api_key_create": 0.10,
    "endorsement_create": 0.15,
    "dispute_create": 0.10,
    "media_upload": 0.10,
}


async def _get_entity_trust(db: AsyncSession, entity_id: object) -> float:
    """Get cached trust score for entity."""
    cache_key = f"trust_gate:{entity_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return float(cached)

    from sqlalchemy import select

    result = await db.execute(
        select(TrustScore.score).where(TrustScore.entity_id == entity_id)
    )
    row = result.scalar_one_or_none()
    score = float(row) if row is not None else 0.0
    await cache_set(cache_key, score, ttl=300)
    return score


def require_trust(action: str) -> Callable:
    """FastAPI dependency that gates an action on trust score.

    Usage:
        @router.post("/foo", dependencies=[Depends(require_trust("create_listing"))])
    """
    threshold = TRUST_GATES.get(action, 0.0)

    async def _check(
        current_entity: Entity = Depends(get_current_entity),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        # Admins bypass trust gates
        if current_entity.is_admin:
            return

        score = await _get_entity_trust(db, current_entity.id)
        if score < threshold:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Trust score too low for this action. "
                    f"Required: {threshold:.2f}, yours: {score:.2f}. "
                    f"Build trust by verifying your email, being active, "
                    f"and receiving attestations."
                ),
            )

    return _check


async def get_trust_gates_info(
    db: AsyncSession,
    entity_id: object,
) -> dict:
    """Return all gates with whether entity meets each threshold."""
    score = await _get_entity_trust(db, entity_id)
    return {
        "trust_score": score,
        "gates": {
            action: {
                "threshold": thresh,
                "unlocked": score >= thresh,
            }
            for action, thresh in sorted(TRUST_GATES.items(), key=lambda x: x[1])
        },
    }
