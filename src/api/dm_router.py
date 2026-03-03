"""Direct messaging endpoints.

Provides one-to-one messaging between entities with conversation
management, read receipts, and WebSocket delivery.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.database import get_db
from src.models import (
    Conversation,
    DirectMessage,
    Entity,
    EntityBlock,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messages", tags=["messages"])


# --- Schemas ---


class SendMessageRequest(BaseModel):
    recipient_id: uuid.UUID
    content: str = Field(..., min_length=1, max_length=5000)


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID
    sender_name: str
    content: str
    is_read: bool
    created_at: str


class ConversationResponse(BaseModel):
    id: uuid.UUID
    other_entity_id: uuid.UUID
    other_entity_name: str
    other_entity_type: str
    last_message_preview: str | None = None
    last_message_at: str
    unread_count: int = 0


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]
    total: int


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
    conversation_id: uuid.UUID
    has_more: bool = False


# --- Helpers ---


async def _get_or_create_conversation(
    db: AsyncSession,
    entity_a_id: uuid.UUID,
    entity_b_id: uuid.UUID,
) -> Conversation:
    """Get existing conversation or create a new one.

    Participant IDs are stored in sorted order to ensure uniqueness.
    """
    # Canonical ordering: smaller UUID = participant_a
    a_id, b_id = sorted([entity_a_id, entity_b_id])

    conv = await db.scalar(
        select(Conversation).where(
            Conversation.participant_a_id == a_id,
            Conversation.participant_b_id == b_id,
        )
    )
    if conv:
        return conv

    conv = Conversation(
        id=uuid.uuid4(),
        participant_a_id=a_id,
        participant_b_id=b_id,
    )
    db.add(conv)
    await db.flush()
    return conv


async def _check_blocked(
    db: AsyncSession, sender_id: uuid.UUID, recipient_id: uuid.UUID,
) -> bool:
    """Check if either party has blocked the other."""
    block = await db.scalar(
        select(EntityBlock).where(
            or_(
                (EntityBlock.blocker_id == sender_id)
                & (EntityBlock.blocked_id == recipient_id),
                (EntityBlock.blocker_id == recipient_id)
                & (EntityBlock.blocked_id == sender_id),
            )
        )
    )
    return block is not None


# --- Endpoints ---


@router.post(
    "",
    response_model=MessageResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
async def send_message(
    body: SendMessageRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Send a direct message to another entity."""
    from src.content_filter import check_content, sanitize_html

    result = check_content(body.content)
    if not result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Message rejected: {', '.join(result.flags)}",
        )
    body.content = sanitize_html(body.content)

    if body.recipient_id == current_entity.id:
        raise HTTPException(
            status_code=400, detail="Cannot send a message to yourself",
        )

    # Check recipient exists and is active
    recipient = await db.get(Entity, body.recipient_id)
    if not recipient or not recipient.is_active:
        raise HTTPException(status_code=404, detail="Recipient not found")

    # Check blocking
    if await _check_blocked(db, current_entity.id, body.recipient_id):
        raise HTTPException(
            status_code=403, detail="Cannot message this entity",
        )

    conv = await _get_or_create_conversation(
        db, current_entity.id, body.recipient_id,
    )

    msg = DirectMessage(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        sender_id=current_entity.id,
        content=body.content,
    )
    db.add(msg)
    conv.last_message_at = func.now()
    await db.flush()
    await db.refresh(msg)

    # Send notification
    try:
        from src.api.notification_router import create_notification

        await create_notification(
            db,
            entity_id=body.recipient_id,
            kind="message",
            title=f"New message from {current_entity.display_name}",
            body=body.content[:100],
            reference_id=str(conv.id),
        )
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # WebSocket delivery
    try:
        from src.ws import manager

        await manager.send_to_entity(
            str(body.recipient_id),
            "messages",
            {
                "type": "new_message",
                "message": {
                    "id": str(msg.id),
                    "conversation_id": str(conv.id),
                    "sender_id": str(current_entity.id),
                    "sender_name": current_entity.display_name,
                    "content": body.content,
                    "created_at": msg.created_at.isoformat(),
                },
            },
        )
    except Exception:
        pass

    # Dispatch webhook event
    try:
        from src.events import dispatch_webhooks

        await dispatch_webhooks(db, "dm.received", {
            "message_id": str(msg.id),
            "conversation_id": str(conv.id),
            "sender_id": str(current_entity.id),
            "sender_name": current_entity.display_name,
            "recipient_id": str(body.recipient_id),
        })
    except Exception:
        logger.warning("Best-effort side effect failed", exc_info=True)

    # Record pairwise interaction
    try:
        from src.interactions import record_interaction

        await record_interaction(
            db,
            entity_a_id=current_entity.id,
            entity_b_id=body.recipient_id,
            interaction_type="dm",
            context={
                "reference_id": str(msg.id),
                "conversation_id": str(conv.id),
            },
        )
    except Exception:
        logger.warning("Best-effort interaction recording failed", exc_info=True)

    # Audit log
    from src.audit import log_action

    await log_action(
        db,
        action="dm.send",
        entity_id=current_entity.id,
        resource_type="direct_message",
        resource_id=msg.id,
        details={"recipient_id": str(body.recipient_id)},
    )

    return MessageResponse(
        id=msg.id,
        conversation_id=conv.id,
        sender_id=current_entity.id,
        sender_name=current_entity.display_name,
        content=msg.content,
        is_read=False,
        created_at=msg.created_at.isoformat(),
    )


@router.get(
    "", response_model=ConversationListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_conversations(
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List conversations for the current entity, ordered by most recent."""
    base = select(Conversation).where(
        or_(
            Conversation.participant_a_id == current_entity.id,
            Conversation.participant_b_id == current_entity.id,
        )
    )

    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0

    query = base.order_by(
        Conversation.last_message_at.desc()
    ).offset(offset).limit(limit)

    result = await db.execute(query)
    conversations = result.scalars().all()

    if not conversations:
        return ConversationListResponse(conversations=[], total=total)

    # Collect all "other" participant IDs and conversation IDs in one pass
    conv_ids = [c.id for c in conversations]
    other_ids: dict[uuid.UUID, uuid.UUID] = {}
    for conv in conversations:
        other_ids[conv.id] = (
            conv.participant_b_id
            if conv.participant_a_id == current_entity.id
            else conv.participant_a_id
        )

    # Batch-fetch all other entities (1 query instead of N)
    entity_ids = list(set(other_ids.values()))
    entities_result = await db.execute(
        select(Entity).where(Entity.id.in_(entity_ids))
    )
    entity_map = {e.id: e for e in entities_result.scalars().all()}

    # Batch-fetch last message per conversation using DISTINCT ON (1 query)
    last_msgs_result = await db.execute(
        select(DirectMessage)
        .where(DirectMessage.conversation_id.in_(conv_ids))
        .order_by(DirectMessage.conversation_id, DirectMessage.created_at.desc())
        .distinct(DirectMessage.conversation_id)
    )
    last_msg_map = {
        msg.conversation_id: msg for msg in last_msgs_result.scalars().all()
    }

    # Batch-fetch unread counts per conversation (1 query)
    unread_result = await db.execute(
        select(
            DirectMessage.conversation_id,
            func.count().label("cnt"),
        )
        .where(
            DirectMessage.conversation_id.in_(conv_ids),
            DirectMessage.sender_id != current_entity.id,
            DirectMessage.is_read.is_(False),
        )
        .group_by(DirectMessage.conversation_id)
    )
    unread_map = {row[0]: row[1] for row in unread_result.all()}

    items: list[ConversationResponse] = []
    for conv in conversations:
        oid = other_ids[conv.id]
        other = entity_map.get(oid)
        if not other:
            continue

        last_msg = last_msg_map.get(conv.id)

        items.append(ConversationResponse(
            id=conv.id,
            other_entity_id=oid,
            other_entity_name=other.display_name,
            other_entity_type=other.type.value,
            last_message_preview=(
                last_msg.content[:100] if last_msg else None
            ),
            last_message_at=conv.last_message_at.isoformat(),
            unread_count=unread_map.get(conv.id, 0),
        ))

    return ConversationListResponse(conversations=items, total=total)


@router.get(
    "/unread-count", response_model=dict,
    dependencies=[Depends(rate_limit_reads)],
)
async def unread_message_count(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get total unread message count across all conversations."""
    conv_ids_query = select(Conversation.id).where(
        or_(
            Conversation.participant_a_id == current_entity.id,
            Conversation.participant_b_id == current_entity.id,
        )
    )

    count = await db.scalar(
        select(func.count())
        .select_from(DirectMessage)
        .where(
            DirectMessage.conversation_id.in_(conv_ids_query),
            DirectMessage.sender_id != current_entity.id,
            DirectMessage.is_read.is_(False),
        )
    ) or 0

    return {"unread_count": count}


@router.get(
    "/{conversation_id}", response_model=MessageListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    before: uuid.UUID | None = Query(None),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get messages in a conversation, with cursor pagination."""
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if (
        conv.participant_a_id != current_entity.id
        and conv.participant_b_id != current_entity.id
    ):
        raise HTTPException(status_code=403, detail="Not your conversation")

    query = (
        select(DirectMessage, Entity.display_name)
        .join(Entity, DirectMessage.sender_id == Entity.id)
        .where(DirectMessage.conversation_id == conversation_id)
    )

    if before:
        # Get the created_at of the cursor message for pagination
        cursor_msg = await db.get(DirectMessage, before)
        if cursor_msg:
            query = query.where(
                DirectMessage.created_at < cursor_msg.created_at,
            )

    query = query.order_by(DirectMessage.created_at.desc()).limit(limit + 1)
    result = await db.execute(query)
    rows = result.all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    messages = [
        MessageResponse(
            id=msg.id,
            conversation_id=msg.conversation_id,
            sender_id=msg.sender_id,
            sender_name=sender_name,
            content=msg.content,
            is_read=msg.is_read,
            created_at=msg.created_at.isoformat(),
        )
        for msg, sender_name in rows
    ]

    # Mark received messages as read
    for msg, _ in rows:
        if msg.sender_id != current_entity.id and not msg.is_read:
            msg.is_read = True
    await db.flush()

    return MessageListResponse(
        messages=messages,
        conversation_id=conversation_id,
        has_more=has_more,
    )


@router.delete(
    "/{conversation_id}/messages/{message_id}",
    status_code=204,
    dependencies=[Depends(rate_limit_writes)],
)
async def delete_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single message. Only the sender can delete their own message."""
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if current_entity.id not in (conv.participant_a_id, conv.participant_b_id):
        raise HTTPException(status_code=403, detail="Not a participant")

    msg = await db.get(DirectMessage, message_id)
    if msg is None or msg.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="Message not found")

    if msg.sender_id != current_entity.id:
        raise HTTPException(
            status_code=403, detail="Can only delete your own messages",
        )

    from src.audit import log_action

    await log_action(
        db,
        action="dm.delete_message",
        entity_id=current_entity.id,
        resource_type="direct_message",
        resource_id=message_id,
        details={"conversation_id": str(conversation_id)},
    )

    await db.delete(msg)
    await db.flush()


@router.delete(
    "/{conversation_id}",
    status_code=204,
    dependencies=[Depends(rate_limit_writes)],
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation and all its messages.

    Only participants can delete a conversation.
    """
    conv = await db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if current_entity.id not in (conv.participant_a_id, conv.participant_b_id):
        raise HTTPException(status_code=403, detail="Not a participant")

    from src.audit import log_action

    await log_action(
        db,
        action="dm.delete_conversation",
        entity_id=current_entity.id,
        resource_type="conversation",
        resource_id=conversation_id,
    )

    # Delete all messages first, then the conversation
    await db.execute(
        delete(DirectMessage).where(
            DirectMessage.conversation_id == conversation_id
        )
    )
    await db.delete(conv)
    await db.flush()
