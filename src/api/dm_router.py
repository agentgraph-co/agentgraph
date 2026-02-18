"""Direct messaging endpoints.

Provides one-to-one messaging between entities with conversation
management, read receipts, and WebSocket delivery.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_writes
from src.database import get_db
from src.models import (
    Conversation,
    DirectMessage,
    Entity,
    EntityBlock,
)

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
        pass  # Best-effort

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
        pass  # Best-effort

    return MessageResponse(
        id=msg.id,
        conversation_id=conv.id,
        sender_id=current_entity.id,
        sender_name=current_entity.display_name,
        content=msg.content,
        is_read=False,
        created_at=msg.created_at.isoformat(),
    )


@router.get("", response_model=ConversationListResponse)
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

    items: list[ConversationResponse] = []
    for conv in conversations:
        # Determine the "other" participant
        other_id = (
            conv.participant_b_id
            if conv.participant_a_id == current_entity.id
            else conv.participant_a_id
        )
        other = await db.get(Entity, other_id)
        if not other:
            continue

        # Get last message preview
        last_msg = await db.scalar(
            select(DirectMessage)
            .where(DirectMessage.conversation_id == conv.id)
            .order_by(DirectMessage.created_at.desc())
            .limit(1)
        )

        # Count unread
        unread = await db.scalar(
            select(func.count())
            .select_from(DirectMessage)
            .where(
                DirectMessage.conversation_id == conv.id,
                DirectMessage.sender_id != current_entity.id,
                DirectMessage.is_read.is_(False),
            )
        ) or 0

        items.append(ConversationResponse(
            id=conv.id,
            other_entity_id=other_id,
            other_entity_name=other.display_name,
            other_entity_type=other.type.value,
            last_message_preview=(
                last_msg.content[:100] if last_msg else None
            ),
            last_message_at=conv.last_message_at.isoformat(),
            unread_count=unread,
        ))

    return ConversationListResponse(conversations=items, total=total)


@router.get("/unread-count", response_model=dict)
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


@router.get("/{conversation_id}", response_model=MessageListResponse)
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

    # Delete all messages first, then the conversation
    await db.execute(
        delete(DirectMessage).where(
            DirectMessage.conversation_id == conversation_id
        )
    )
    await db.delete(conv)
    await db.flush()
