"""Dispute resolution endpoints for escrowed marketplace transactions.

Allows buyers to open disputes on escrow transactions, supports
negotiation between buyer and seller, escalation to admin, and
admin adjudication.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.config import settings
from src.database import get_db
from src.models import (
    Dispute,
    DisputeResolution,
    DisputeStatus,
    Entity,
    Transaction,
    TransactionStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/disputes", tags=["disputes"])


# --- Schemas ---


class OpenDisputeRequest(BaseModel):
    transaction_id: uuid.UUID
    reason: str = Field(..., min_length=10, max_length=2000)


class DisputeMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ResolveDisputeRequest(BaseModel):
    resolution: str = Field(
        ..., pattern="^(release_funds|cancel_auth|partial_refund)$",
    )
    amount_cents: int | None = Field(None, ge=0)


class AdjudicateDisputeRequest(BaseModel):
    resolution: str = Field(
        ..., pattern="^(release_funds|cancel_auth|partial_refund)$",
    )
    amount_cents: int | None = Field(None, ge=0)
    admin_note: str | None = Field(None, max_length=2000)


class DisputeResponse(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    opened_by: uuid.UUID
    reason: str
    status: str
    resolution: str | None = None
    resolution_amount_cents: int | None = None
    resolved_by: uuid.UUID | None = None
    admin_note: str | None = None
    deadline: str
    created_at: str
    resolved_at: str | None = None


class DisputeListResponse(BaseModel):
    disputes: list[DisputeResponse]
    total: int


def _dispute_response(dispute: Dispute) -> DisputeResponse:
    return DisputeResponse(
        id=dispute.id,
        transaction_id=dispute.transaction_id,
        opened_by=dispute.opened_by,
        reason=dispute.reason,
        status=dispute.status,
        resolution=dispute.resolution,
        resolution_amount_cents=dispute.resolution_amount_cents,
        resolved_by=dispute.resolved_by,
        admin_note=dispute.admin_note,
        deadline=dispute.deadline.isoformat(),
        created_at=dispute.created_at.isoformat(),
        resolved_at=dispute.resolved_at.isoformat() if dispute.resolved_at else None,
    )


# --- Endpoints ---


@router.post(
    "",
    response_model=DisputeResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
async def open_dispute(
    body: OpenDisputeRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Open a dispute on an escrowed transaction. Only the buyer can dispute."""
    from src.content_filter import check_content, sanitize_html

    # Validate reason content
    filter_result = check_content(body.reason)
    if not filter_result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Reason rejected: {', '.join(filter_result.flags)}",
        )

    txn = await db.get(Transaction, body.transaction_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Only the buyer can open a dispute
    if txn.buyer_entity_id != current_entity.id:
        raise HTTPException(
            status_code=403, detail="Only the buyer can open a dispute",
        )

    # Transaction must be in ESCROW status
    if txn.status != TransactionStatus.ESCROW:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot dispute a transaction with status '{txn.status.value}'",
        )

    # Check no existing dispute
    existing = await db.scalar(
        select(Dispute).where(Dispute.transaction_id == body.transaction_id)
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="A dispute already exists for this transaction",
        )

    deadline = datetime.now(timezone.utc) + timedelta(
        hours=settings.escrow_auto_release_hours,
    )

    dispute = Dispute(
        id=uuid.uuid4(),
        transaction_id=body.transaction_id,
        opened_by=current_entity.id,
        reason=sanitize_html(body.reason),
        status=DisputeStatus.OPEN.value,
        deadline=deadline,
    )
    db.add(dispute)

    # Move transaction to DISPUTED
    txn.status = TransactionStatus.DISPUTED
    await db.flush()

    from src.audit import log_action

    await log_action(
        db,
        action="dispute.open",
        entity_id=current_entity.id,
        resource_type="dispute",
        resource_id=dispute.id,
        details={
            "transaction_id": str(body.transaction_id),
            "reason": dispute.reason[:200],
        },
    )

    # Notify the seller
    try:
        from src.api.notification_router import create_notification

        await create_notification(
            db,
            entity_id=txn.seller_entity_id,
            kind="moderation",
            title="Dispute opened on your transaction",
            body=(
                f"A dispute has been opened for '{txn.listing_title}': "
                f"{dispute.reason[:100]}"
            ),
            reference_id=str(dispute.id),
        )
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # WebSocket broadcast
    try:
        from src.ws import manager

        await manager.send_to_entity(str(txn.seller_entity_id), "disputes", {
            "type": "dispute_opened",
            "dispute_id": str(dispute.id),
            "transaction_id": str(dispute.transaction_id),
            "reason": dispute.reason[:100],
            "opened_by": str(dispute.opened_by),
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return _dispute_response(dispute)


@router.get(
    "",
    response_model=DisputeListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_disputes(
    status: str | None = Query(
        None, pattern="^(open|negotiating|escalated|resolved|closed)$",
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List disputes where the current entity is the buyer or seller."""
    # Subquery to find transaction IDs where user is involved
    txn_subquery = (
        select(Transaction.id)
        .where(
            or_(
                Transaction.buyer_entity_id == current_entity.id,
                Transaction.seller_entity_id == current_entity.id,
            )
        )
        .subquery()
    )

    query = select(Dispute).where(
        Dispute.transaction_id.in_(select(txn_subquery))
    )

    if status:
        query = query.where(Dispute.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    result = await db.execute(
        query.order_by(Dispute.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    disputes = result.scalars().all()

    return DisputeListResponse(
        disputes=[_dispute_response(d) for d in disputes],
        total=total,
    )


@router.get(
    "/{dispute_id}",
    response_model=DisputeResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_dispute(
    dispute_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get dispute details. Accessible by buyer, seller, or admin."""
    dispute = await db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")

    txn = await db.get(Transaction, dispute.transaction_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Authorization: buyer, seller, or admin
    is_participant = (
        txn.buyer_entity_id == current_entity.id
        or txn.seller_entity_id == current_entity.id
    )
    if not is_participant and not current_entity.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to view this dispute",
        )

    return _dispute_response(dispute)


@router.post(
    "/{dispute_id}/message",
    dependencies=[Depends(rate_limit_writes)],
)
async def add_dispute_message(
    dispute_id: uuid.UUID,
    body: DisputeMessageRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Add a message to the dispute thread (creates a DM between buyer/seller)."""
    from src.content_filter import check_content, sanitize_html

    filter_result = check_content(body.message)
    if not filter_result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Message rejected: {', '.join(filter_result.flags)}",
        )

    dispute = await db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")

    if dispute.status in (DisputeStatus.RESOLVED.value, DisputeStatus.CLOSED.value):
        raise HTTPException(
            status_code=400, detail="Cannot message on a resolved/closed dispute",
        )

    txn = await db.get(Transaction, dispute.transaction_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Only buyer/seller/admin can message
    is_participant = (
        txn.buyer_entity_id == current_entity.id
        or txn.seller_entity_id == current_entity.id
    )
    if not is_participant and not current_entity.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized for this dispute",
        )

    # Determine recipient
    if current_entity.id == txn.buyer_entity_id:
        recipient_id = txn.seller_entity_id
    else:
        recipient_id = txn.buyer_entity_id

    # Create or find conversation and add message
    from src.models import Conversation, DirectMessage

    # Find existing conversation (either direction)
    conv = await db.scalar(
        select(Conversation).where(
            or_(
                (Conversation.participant_a_id == current_entity.id)
                & (Conversation.participant_b_id == recipient_id),
                (Conversation.participant_a_id == recipient_id)
                & (Conversation.participant_b_id == current_entity.id),
            )
        )
    )

    now = datetime.now(timezone.utc)
    sanitized_msg = sanitize_html(body.message)
    prefixed_msg = f"[Dispute #{str(dispute_id)[:8]}] {sanitized_msg}"

    if not conv:
        conv = Conversation(
            id=uuid.uuid4(),
            participant_a_id=current_entity.id,
            participant_b_id=recipient_id,
            last_message_at=now,
        )
        db.add(conv)
        await db.flush()

    dm = DirectMessage(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        sender_id=current_entity.id,
        content=prefixed_msg,
    )
    db.add(dm)
    conv.last_message_at = now

    # Move to negotiating if still open
    if dispute.status == DisputeStatus.OPEN.value:
        dispute.status = DisputeStatus.NEGOTIATING.value

    await db.flush()

    # Notify recipient
    try:
        from src.api.notification_router import create_notification

        await create_notification(
            db,
            entity_id=recipient_id,
            kind="message",
            title="New dispute message",
            body=f"New message on dispute for '{txn.listing_title}'",
            reference_id=str(dispute_id),
        )
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # WebSocket broadcast to the other party
    try:
        from src.ws import manager

        await manager.send_to_entity(str(recipient_id), "disputes", {
            "type": "dispute_message",
            "dispute_id": str(dispute.id),
            "sender_id": str(current_entity.id),
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return {
        "message_id": str(dm.id),
        "dispute_id": str(dispute_id),
        "content": prefixed_msg,
    }


@router.post(
    "/{dispute_id}/resolve",
    response_model=DisputeResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def resolve_dispute(
    dispute_id: uuid.UUID,
    body: ResolveDisputeRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Propose a resolution for the dispute. Buyer or seller can resolve."""
    dispute = await db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")

    if dispute.status in (DisputeStatus.RESOLVED.value, DisputeStatus.CLOSED.value):
        raise HTTPException(
            status_code=400, detail="Dispute is already resolved",
        )

    txn = await db.scalar(
        select(Transaction)
        .where(Transaction.id == dispute.transaction_id)
        .with_for_update()
    )
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Only buyer or seller
    is_participant = (
        txn.buyer_entity_id == current_entity.id
        or txn.seller_entity_id == current_entity.id
    )
    if not is_participant:
        raise HTTPException(
            status_code=403, detail="Only buyer or seller can resolve",
        )

    resolution_enum = DisputeResolution(body.resolution)

    # Validate partial refund amount
    if resolution_enum == DisputeResolution.PARTIAL_REFUND:
        if body.amount_cents is None or body.amount_cents <= 0:
            raise HTTPException(
                status_code=400,
                detail="Partial refund requires a positive amount_cents",
            )
        if body.amount_cents >= txn.amount_cents:
            raise HTTPException(
                status_code=400,
                detail="Partial refund amount must be less than transaction amount",
            )

    # Execute the resolution
    if resolution_enum == DisputeResolution.RELEASE_FUNDS:
        from src.payments.escrow import release_escrow

        await release_escrow(db, txn, current_entity.id)

    elif resolution_enum == DisputeResolution.CANCEL_AUTH:
        from src.payments.escrow import cancel_escrow

        await cancel_escrow(db, txn, current_entity.id)

    elif resolution_enum == DisputeResolution.PARTIAL_REFUND:
        from src.payments.escrow import partial_capture

        await partial_capture(db, txn, body.amount_cents, current_entity.id)

    dispute.status = DisputeStatus.RESOLVED.value
    dispute.resolution = body.resolution
    dispute.resolution_amount_cents = body.amount_cents
    dispute.resolved_by = current_entity.id
    dispute.resolved_at = datetime.now(timezone.utc)

    await db.flush()

    from src.audit import log_action

    await log_action(
        db,
        action="dispute.resolve",
        entity_id=current_entity.id,
        resource_type="dispute",
        resource_id=dispute.id,
        details={
            "resolution": body.resolution,
            "amount_cents": body.amount_cents,
            "transaction_id": str(txn.id),
        },
    )

    # Notify the other party
    try:
        from src.api.notification_router import create_notification

        other_id = (
            txn.seller_entity_id
            if current_entity.id == txn.buyer_entity_id
            else txn.buyer_entity_id
        )
        await create_notification(
            db,
            entity_id=other_id,
            kind="moderation",
            title="Dispute resolved",
            body=(
                f"Dispute for '{txn.listing_title}' has been resolved: "
                f"{body.resolution}"
            ),
            reference_id=str(dispute.id),
        )
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # WebSocket broadcast to both parties
    try:
        from src.ws import manager

        for party_id in [txn.buyer_entity_id, txn.seller_entity_id]:
            await manager.send_to_entity(str(party_id), "disputes", {
                "type": "dispute_resolved",
                "dispute_id": str(dispute.id),
                "resolution": dispute.resolution,
            })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return _dispute_response(dispute)


@router.post(
    "/{dispute_id}/escalate",
    response_model=DisputeResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def escalate_dispute(
    dispute_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Escalate a dispute to admin review."""
    dispute = await db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")

    if dispute.status in (DisputeStatus.RESOLVED.value, DisputeStatus.CLOSED.value):
        raise HTTPException(
            status_code=400, detail="Dispute is already resolved",
        )

    if dispute.status == DisputeStatus.ESCALATED.value:
        raise HTTPException(
            status_code=400, detail="Dispute is already escalated",
        )

    txn = await db.get(Transaction, dispute.transaction_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Only buyer or seller can escalate
    is_participant = (
        txn.buyer_entity_id == current_entity.id
        or txn.seller_entity_id == current_entity.id
    )
    if not is_participant:
        raise HTTPException(
            status_code=403, detail="Only buyer or seller can escalate",
        )

    dispute.status = DisputeStatus.ESCALATED.value
    await db.flush()

    from src.audit import log_action

    await log_action(
        db,
        action="dispute.escalate",
        entity_id=current_entity.id,
        resource_type="dispute",
        resource_id=dispute.id,
        details={"transaction_id": str(txn.id)},
    )

    # WebSocket broadcast to both parties
    try:
        from src.ws import manager

        for party_id in [txn.buyer_entity_id, txn.seller_entity_id]:
            await manager.send_to_entity(str(party_id), "disputes", {
                "type": "dispute_escalated",
                "dispute_id": str(dispute.id),
            })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return _dispute_response(dispute)


# --- Admin Endpoints ---


@router.get(
    "/admin/all",
    response_model=DisputeListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def admin_list_disputes(
    status: str | None = Query(
        None, pattern="^(open|negotiating|escalated|resolved|closed)$",
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Admin: list all disputes."""
    if not current_entity.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    query = select(Dispute)

    if status:
        query = query.where(Dispute.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    result = await db.execute(
        query.order_by(Dispute.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    disputes = result.scalars().all()

    return DisputeListResponse(
        disputes=[_dispute_response(d) for d in disputes],
        total=total,
    )


@router.post(
    "/admin/{dispute_id}/adjudicate",
    response_model=DisputeResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def admin_adjudicate_dispute(
    dispute_id: uuid.UUID,
    body: AdjudicateDisputeRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Admin: adjudicate a dispute with a binding resolution."""
    if not current_entity.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    dispute = await db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")

    if dispute.status in (DisputeStatus.RESOLVED.value, DisputeStatus.CLOSED.value):
        raise HTTPException(
            status_code=400, detail="Dispute is already resolved",
        )

    txn = await db.scalar(
        select(Transaction)
        .where(Transaction.id == dispute.transaction_id)
        .with_for_update()
    )
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    resolution_enum = DisputeResolution(body.resolution)

    # Validate partial refund
    if resolution_enum == DisputeResolution.PARTIAL_REFUND:
        if body.amount_cents is None or body.amount_cents <= 0:
            raise HTTPException(
                status_code=400,
                detail="Partial refund requires a positive amount_cents",
            )
        if body.amount_cents >= txn.amount_cents:
            raise HTTPException(
                status_code=400,
                detail="Partial refund amount must be less than transaction amount",
            )

    # Execute the resolution
    if resolution_enum == DisputeResolution.RELEASE_FUNDS:
        from src.payments.escrow import release_escrow

        await release_escrow(db, txn, current_entity.id)

    elif resolution_enum == DisputeResolution.CANCEL_AUTH:
        from src.payments.escrow import cancel_escrow

        await cancel_escrow(db, txn, current_entity.id)

    elif resolution_enum == DisputeResolution.PARTIAL_REFUND:
        from src.payments.escrow import partial_capture

        await partial_capture(db, txn, body.amount_cents, current_entity.id)

    dispute.status = DisputeStatus.RESOLVED.value
    dispute.resolution = body.resolution
    dispute.resolution_amount_cents = body.amount_cents
    dispute.resolved_by = current_entity.id
    dispute.admin_note = body.admin_note
    dispute.resolved_at = datetime.now(timezone.utc)

    await db.flush()

    from src.audit import log_action

    await log_action(
        db,
        action="dispute.admin_adjudicate",
        entity_id=current_entity.id,
        resource_type="dispute",
        resource_id=dispute.id,
        details={
            "resolution": body.resolution,
            "amount_cents": body.amount_cents,
            "admin_note": body.admin_note,
            "transaction_id": str(txn.id),
        },
    )

    # Notify both parties
    try:
        from src.api.notification_router import create_notification

        for entity_id in (txn.buyer_entity_id, txn.seller_entity_id):
            await create_notification(
                db,
                entity_id=entity_id,
                kind="moderation",
                title="Dispute adjudicated by admin",
                body=(
                    f"An admin has resolved the dispute for "
                    f"'{txn.listing_title}': {body.resolution}"
                ),
                reference_id=str(dispute.id),
            )
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # WebSocket broadcast to both parties
    try:
        from src.ws import manager

        for party_id in [txn.buyer_entity_id, txn.seller_entity_id]:
            await manager.send_to_entity(str(party_id), "disputes", {
                "type": "dispute_adjudicated",
                "dispute_id": str(dispute.id),
                "resolution": dispute.resolution,
            })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    return _dispute_response(dispute)
