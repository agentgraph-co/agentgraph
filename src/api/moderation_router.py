from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deactivation import cascade_deactivate
from src.api.deps import get_current_entity, require_admin
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import (
    APIKey,
    Entity,
    ModerationAppeal,
    ModerationFlag,
    ModerationReason,
    ModerationStatus,
    Post,
    WebhookSubscription,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/moderation", tags=["moderation"])


class CreateFlagRequest(BaseModel):
    target_type: str = Field(..., pattern="^(post|entity)$")
    target_id: uuid.UUID
    reason: ModerationReason
    details: str | None = Field(None, max_length=2000)


class FlagResponse(BaseModel):
    id: uuid.UUID
    reporter_entity_id: uuid.UUID | None
    target_type: str
    target_id: uuid.UUID
    reason: str
    details: str | None
    reporter_trust_score: float | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ResolveFlagRequest(BaseModel):
    status: ModerationStatus = Field(
        ...,
        description="Must be one of: dismissed, warned, removed, suspended, banned",
    )
    resolution_note: str | None = Field(None, max_length=2000)


class FlagListResponse(BaseModel):
    flags: list[FlagResponse]
    count: int
    total: int = 0
    has_more: bool = False


@router.post(
    "/flag", response_model=FlagResponse, status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
async def create_flag(
    body: CreateFlagRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    # Verify target exists
    if body.target_type == "post":
        target = await db.get(Post, body.target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Target post not found")
        if target.author_entity_id == current_entity.id:
            raise HTTPException(status_code=400, detail="Cannot flag your own content")
    elif body.target_type == "entity":
        target = await db.get(Entity, body.target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Target entity not found")
        if target.id == current_entity.id:
            raise HTTPException(status_code=400, detail="Cannot flag yourself")

    # Prevent duplicate active flags from the same reporter on the same target
    existing = await db.scalar(
        select(ModerationFlag).where(
            ModerationFlag.reporter_entity_id == current_entity.id,
            ModerationFlag.target_type == body.target_type,
            ModerationFlag.target_id == body.target_id,
            ModerationFlag.status == ModerationStatus.PENDING,
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="You already have a pending flag on this target",
        )

    if body.details:
        from src.content_filter import check_content, sanitize_html

        filter_result = check_content(body.details)
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Details rejected: {', '.join(filter_result.flags)}",
            )
        body.details = sanitize_html(body.details)

    # Fetch reporter's trust score for weighted flagging
    reporter_trust_score = None
    try:
        from src.models import TrustScore
        ts = await db.scalar(
            select(TrustScore.score).where(TrustScore.entity_id == current_entity.id)
        )
        reporter_trust_score = ts if ts is not None else 0.0
    except Exception:
        reporter_trust_score = 0.0

    flag = ModerationFlag(
        id=uuid.uuid4(),
        reporter_entity_id=current_entity.id,
        target_type=body.target_type,
        target_id=body.target_id,
        reason=body.reason,
        details=body.details,
        reporter_trust_score=reporter_trust_score,
        status=ModerationStatus.PENDING,
    )
    db.add(flag)
    await db.flush()

    # Dispatch moderation.flagged webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "moderation.flagged", {
            "flag_id": str(flag.id),
            "target_type": body.target_type,
            "target_id": str(body.target_id),
            "reason": body.reason.value,
            "reporter_id": str(current_entity.id),
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # Auto-hide post if flag threshold is exceeded
    if body.target_type == "post":
        from src.api.auto_moderation import check_flag_threshold

        await check_flag_threshold(db, body.target_id)

    await log_action(
        db,
        action="moderation.flag_created",
        entity_id=current_entity.id,
        resource_type=body.target_type,
        resource_id=body.target_id,
        details={
            "flag_id": str(flag.id),
            "reason": body.reason.value,
        },
    )

    return FlagResponse(
        id=flag.id,
        reporter_entity_id=flag.reporter_entity_id,
        target_type=flag.target_type,
        target_id=flag.target_id,
        reason=flag.reason.value,
        details=flag.details,
        reporter_trust_score=flag.reporter_trust_score,
        status=flag.status.value,
        created_at=flag.created_at,
    )


@router.get(
    "/flags", response_model=FlagListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_flags(
    status: ModerationStatus | None = Query(None),
    reason: ModerationReason | None = Query(None),
    target_type: str | None = Query(None),
    sort: str = Query("trust", pattern="^(trust|recent)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List moderation flags with filtering and pagination. Admin only."""
    require_admin(current_entity)

    query = select(ModerationFlag)
    if status is not None:
        query = query.where(ModerationFlag.status == status)
    if reason is not None:
        query = query.where(ModerationFlag.reason == reason)
    if target_type is not None:
        query = query.where(ModerationFlag.target_type == target_type)

    total = await db.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0

    if sort == "trust":
        # High-trust reporters' flags first, then by recency
        query = query.order_by(
            ModerationFlag.reporter_trust_score.desc().nullslast(),
            ModerationFlag.created_at.desc(),
        )
    else:
        query = query.order_by(ModerationFlag.created_at.desc())
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    flags = result.scalars().all()

    return FlagListResponse(
        flags=[
            FlagResponse(
                id=f.id,
                reporter_entity_id=f.reporter_entity_id,
                target_type=f.target_type,
                target_id=f.target_id,
                reason=f.reason.value,
                details=f.details,
                reporter_trust_score=f.reporter_trust_score,
                status=f.status.value,
                created_at=f.created_at,
            )
            for f in flags
        ],
        count=len(flags),
        total=total,
        has_more=(offset + len(flags)) < total,
    )


@router.get(
    "/flags/{flag_id}", response_model=FlagResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_flag(
    flag_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get a single moderation flag. Accessible by the reporter or admins."""
    flag = await db.get(ModerationFlag, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag not found")

    # Only the reporter or an admin can view
    if flag.reporter_entity_id != current_entity.id and not current_entity.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to view this flag")

    return FlagResponse(
        id=flag.id,
        reporter_entity_id=flag.reporter_entity_id,
        target_type=flag.target_type,
        target_id=flag.target_id,
        reason=flag.reason.value,
        details=flag.details,
        reporter_trust_score=flag.reporter_trust_score,
        status=flag.status.value,
        created_at=flag.created_at,
    )


@router.patch(
    "/flags/{flag_id}/resolve", response_model=FlagResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def resolve_flag(
    flag_id: uuid.UUID,
    body: ResolveFlagRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a moderation flag. Admin only."""
    require_admin(current_entity)

    if body.status == ModerationStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Cannot resolve to 'pending' status",
        )

    flag = await db.get(ModerationFlag, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag not found")
    if flag.status != ModerationStatus.PENDING:
        raise HTTPException(status_code=409, detail="Flag already resolved")

    flag.status = body.status
    flag.resolved_by = current_entity.id
    flag.resolution_note = body.resolution_note
    flag.resolved_at = func.now()

    # Auto-hide post if removal action
    if body.status == ModerationStatus.REMOVED and flag.target_type == "post":
        post = await db.get(Post, flag.target_id)
        if post:
            post.is_hidden = True

    # Warn: notify but leave account active
    if body.status == ModerationStatus.WARNED:
        try:
            from src.api.notification_router import create_notification

            target_entity_id = flag.target_id
            if flag.target_type == "post":
                post = await db.get(Post, flag.target_id)
                if post:
                    target_entity_id = post.author_entity_id
            await create_notification(
                db,
                entity_id=target_entity_id,
                kind="moderation",
                title="Content warning",
                body=f"Warning: your {flag.target_type} was flagged for {flag.reason.value}. "
                     f"Repeated violations may result in suspension.",
                reference_id=str(flag.id),
            )
        except Exception:
            logger.warning("Best-effort side effect failed", exc_info=True)

    # Suspend entity if suspension action
    if body.status in (ModerationStatus.SUSPENDED, ModerationStatus.BANNED):
        if flag.target_type == "entity":
            target_entity = await db.get(Entity, flag.target_id)
            if target_entity:
                target_entity.is_active = False
                await db.flush()
                await cascade_deactivate(
                    db, target_entity.id,
                    performed_by=current_entity.id,
                )

    await log_action(
        db,
        action=f"moderation.resolve.{body.status.value}",
        entity_id=current_entity.id,
        resource_type="moderation_flag",
        resource_id=flag.id,
        details={
            "target_type": flag.target_type,
            "target_id": str(flag.target_id),
            "resolution": body.status.value,
        },
    )

    # Dispatch moderation.resolved webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "moderation.resolved", {
            "flag_id": str(flag.id),
            "target_type": flag.target_type,
            "target_id": str(flag.target_id),
            "resolution_status": body.status.value,
            "resolver_id": str(current_entity.id),
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # Notify target entity of moderation action
    try:
        from src.api.notification_router import create_notification

        if flag.target_type == "post" and body.status == ModerationStatus.REMOVED:
            post = await db.get(Post, flag.target_id)
            if post:
                await create_notification(
                    db,
                    entity_id=post.author_entity_id,
                    kind="moderation",
                    title="Post removed",
                    body=f"Your post was removed for: {flag.reason.value}",
                    reference_id=str(flag.id),
                )
        elif flag.target_type == "entity" and body.status in (
            ModerationStatus.SUSPENDED, ModerationStatus.BANNED,
        ):
            await create_notification(
                db,
                entity_id=flag.target_id,
                kind="moderation",
                title=f"Account {body.status.value}",
                body=f"Your account was {body.status.value}: {flag.reason.value}",
                reference_id=str(flag.id),
            )
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    await db.flush()

    return FlagResponse(
        id=flag.id,
        reporter_entity_id=flag.reporter_entity_id,
        target_type=flag.target_type,
        target_id=flag.target_id,
        reason=flag.reason.value,
        details=flag.details,
        reporter_trust_score=flag.reporter_trust_score,
        status=flag.status.value,
        created_at=flag.created_at,
    )


@router.get("/stats", dependencies=[Depends(rate_limit_reads)])
async def moderation_stats(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get moderation statistics. Admin only."""
    require_admin(current_entity)

    pending = await db.scalar(
        select(func.count()).select_from(ModerationFlag).where(
            ModerationFlag.status == ModerationStatus.PENDING,
        )
    ) or 0

    total = await db.scalar(
        select(func.count()).select_from(ModerationFlag)
    ) or 0

    resolved = total - pending

    # Breakdown by reason
    reason_result = await db.execute(
        select(
            ModerationFlag.reason,
            func.count().label("count"),
        )
        .group_by(ModerationFlag.reason)
    )
    by_reason = {row[0].value: row[1] for row in reason_result.all()}

    # Breakdown by status
    status_result = await db.execute(
        select(
            ModerationFlag.status,
            func.count().label("count"),
        )
        .group_by(ModerationFlag.status)
    )
    by_status = {row[0].value: row[1] for row in status_result.all()}

    # Breakdown by target type
    target_result = await db.execute(
        select(
            ModerationFlag.target_type,
            func.count().label("count"),
        )
        .group_by(ModerationFlag.target_type)
    )
    by_target_type = {row[0]: row[1] for row in target_result.all()}

    return {
        "total_flags": total,
        "pending_flags": pending,
        "resolved_flags": resolved,
        "by_reason": by_reason,
        "by_status": by_status,
        "by_target_type": by_target_type,
    }


# --- Appeals ---


class CreateAppealRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class ResolveAppealRequest(BaseModel):
    action: str = Field(..., pattern="^(uphold|overturn)$")
    note: str = Field("", max_length=2000)


@router.post(
    "/flags/{flag_id}/appeal",
    status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
async def appeal_flag(
    flag_id: uuid.UUID,
    body: CreateAppealRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Appeal a moderation decision. Only the target of the flag can appeal."""
    flag = await db.get(ModerationFlag, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag not found")

    if flag.status == ModerationStatus.PENDING:
        raise HTTPException(
            status_code=400, detail="Cannot appeal a pending flag",
        )

    # Only the flagged entity (or the author of the flagged post) can appeal
    if flag.target_type == "entity":
        if flag.target_id != current_entity.id:
            raise HTTPException(
                status_code=403, detail="Only the flagged entity can appeal",
            )
    elif flag.target_type == "post":
        post = await db.get(Post, flag.target_id)
        if post is None or post.author_entity_id != current_entity.id:
            raise HTTPException(
                status_code=403, detail="Only the post author can appeal",
            )

    # Check for existing pending appeal
    existing = await db.scalar(
        select(ModerationAppeal).where(
            ModerationAppeal.flag_id == flag_id,
            ModerationAppeal.status == "pending",
        )
    )
    if existing:
        raise HTTPException(
            status_code=409, detail="A pending appeal already exists",
        )

    # Content filter on appeal reason
    from src.content_filter import check_content, sanitize_html

    filter_result = check_content(body.reason)
    if not filter_result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Appeal reason rejected: {', '.join(filter_result.flags)}",
        )
    body.reason = sanitize_html(body.reason)

    appeal = ModerationAppeal(
        id=uuid.uuid4(),
        flag_id=flag_id,
        appellant_id=current_entity.id,
        reason=body.reason,
    )
    db.add(appeal)

    await log_action(
        db,
        action="moderation.appeal",
        entity_id=current_entity.id,
        resource_type="moderation_appeal",
        resource_id=appeal.id,
        details={"flag_id": str(flag_id)},
    )
    await db.flush()

    return {
        "id": str(appeal.id),
        "flag_id": str(flag_id),
        "status": "pending",
        "reason": appeal.reason,
        "created_at": appeal.created_at.isoformat(),
    }


@router.get("/appeals", dependencies=[Depends(rate_limit_reads)])
async def list_appeals(
    status: str | None = Query(None, pattern="^(pending|upheld|overturned)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List moderation appeals. Admin only."""
    require_admin(current_entity)

    query = select(ModerationAppeal)
    count_query = select(func.count()).select_from(ModerationAppeal)

    if status:
        query = query.where(ModerationAppeal.status == status)
        count_query = count_query.where(ModerationAppeal.status == status)

    total = await db.scalar(count_query) or 0

    result = await db.execute(
        query.order_by(ModerationAppeal.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    appeals = result.scalars().all()

    return {
        "appeals": [
            {
                "id": str(a.id),
                "flag_id": str(a.flag_id),
                "appellant_id": str(a.appellant_id),
                "reason": a.reason,
                "status": a.status,
                "resolved_by": str(a.resolved_by) if a.resolved_by else None,
                "resolution_note": a.resolution_note,
                "created_at": a.created_at.isoformat(),
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
            }
            for a in appeals
        ],
        "total": total,
    }


@router.get("/appeals/{appeal_id}", dependencies=[Depends(rate_limit_reads)])
async def get_appeal(
    appeal_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get a single appeal. Accessible by the appellant or admins."""
    appeal = await db.get(ModerationAppeal, appeal_id)
    if appeal is None:
        raise HTTPException(status_code=404, detail="Appeal not found")

    if appeal.appellant_id != current_entity.id and not current_entity.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to view this appeal",
        )

    return {
        "id": str(appeal.id),
        "flag_id": str(appeal.flag_id),
        "appellant_id": str(appeal.appellant_id),
        "reason": appeal.reason,
        "status": appeal.status,
        "resolved_by": str(appeal.resolved_by) if appeal.resolved_by else None,
        "resolution_note": appeal.resolution_note,
        "created_at": appeal.created_at.isoformat(),
        "resolved_at": (
            appeal.resolved_at.isoformat() if appeal.resolved_at else None
        ),
    }


@router.patch(
    "/appeals/{appeal_id}",
    dependencies=[Depends(rate_limit_writes)],
)
async def resolve_appeal(
    appeal_id: uuid.UUID,
    body: ResolveAppealRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a moderation appeal. Admin only."""
    require_admin(current_entity)

    appeal = await db.get(ModerationAppeal, appeal_id)
    if appeal is None:
        raise HTTPException(status_code=404, detail="Appeal not found")

    if appeal.status != "pending":
        raise HTTPException(status_code=409, detail="Appeal already resolved")

    appeal.status = "upheld" if body.action == "uphold" else "overturned"
    appeal.resolved_by = current_entity.id
    appeal.resolution_note = body.note or None
    appeal.resolved_at = func.now()

    # If overturned, reverse the moderation action
    if body.action == "overturn":
        flag = await db.get(ModerationFlag, appeal.flag_id)
        if flag:
            # Unhide post if it was removed
            if flag.target_type == "post" and flag.status == ModerationStatus.REMOVED:
                post = await db.get(Post, flag.target_id)
                if post:
                    post.is_hidden = False

            # Reactivate entity if suspended/banned
            if flag.status in (ModerationStatus.SUSPENDED, ModerationStatus.BANNED):
                if flag.target_type == "entity":
                    target = await db.get(Entity, flag.target_id)
                    if target:
                        target.is_active = True
                        target.suspended_until = None

                        # Restore cascade effects: reactivate API keys
                        key_result = await db.execute(
                            select(APIKey).where(
                                APIKey.entity_id == flag.target_id,
                                APIKey.is_active.is_(False),
                            )
                        )
                        for key in key_result.scalars().all():
                            key.is_active = True
                            key.revoked_at = None

                        # Restore cascade effects: reactivate webhook subscriptions
                        await db.execute(
                            update(WebhookSubscription)
                            .where(
                                WebhookSubscription.entity_id == flag.target_id,
                                WebhookSubscription.is_active.is_(False),
                            )
                            .values(is_active=True)
                        )

            flag.status = ModerationStatus.DISMISSED
            flag.resolution_note = f"Overturned on appeal: {body.note or 'No reason given'}"

    await log_action(
        db,
        action=f"moderation.appeal.{body.action}",
        entity_id=current_entity.id,
        resource_type="moderation_appeal",
        resource_id=appeal.id,
        details={
            "flag_id": str(appeal.flag_id),
            "appellant_id": str(appeal.appellant_id),
        },
    )

    # Dispatch moderation.appeal_resolved webhook
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "moderation.appeal_resolved", {
            "appeal_id": str(appeal.id),
            "flag_id": str(appeal.flag_id),
            "action": body.action,
            "appellant_id": str(appeal.appellant_id),
            "resolver_id": str(current_entity.id),
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # Notify appellant of appeal decision
    try:
        from src.api.notification_router import create_notification

        status_text = "upheld" if body.action == "uphold" else "overturned"
        await create_notification(
            db,
            entity_id=appeal.appellant_id,
            kind="moderation",
            title=f"Appeal {status_text}",
            body=f"Your moderation appeal was {status_text}.",
            reference_id=str(appeal.id),
        )
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    await db.flush()

    return {
        "id": str(appeal.id),
        "status": appeal.status,
        "resolution_note": appeal.resolution_note,
        "resolved_by": str(current_entity.id),
    }
