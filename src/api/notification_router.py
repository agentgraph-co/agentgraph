"""In-app notification endpoints.

Provides notification management for entity activities like
follows, replies, votes, and mentions. Persisted to database.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_writes
from src.database import get_db
from src.models import Entity, Notification, NotificationPreference

router = APIRouter(prefix="/notifications", tags=["notifications"])


# --- Public helper for creating notifications from other modules ---


_KIND_TO_PREF = {
    "follow": "follow_enabled",
    "reply": "reply_enabled",
    "vote": "vote_enabled",
    "mention": "mention_enabled",
    "endorsement": "endorsement_enabled",
    "review": "review_enabled",
    "moderation": "moderation_enabled",
}

_KIND_TO_WEBHOOK_EVENT = {
    "follow": "entity.followed",
    "reply": "post.replied",
    "vote": "post.voted",
    "mention": "entity.mentioned",
    "endorsement": "entity.mentioned",
    "review": "entity.mentioned",
    "moderation": "moderation.flagged",
}


async def create_notification(
    db: AsyncSession,
    entity_id: uuid.UUID,
    kind: str,
    title: str,
    body: str,
    reference_id: str | None = None,
) -> Notification | None:
    """Create a notification for an entity (persisted to DB).

    Also dispatches webhooks for the event (regardless of notification
    preferences) and broadcasts via WebSocket.

    Returns None if the entity has disabled this notification kind.
    """
    # Dispatch webhooks (always, regardless of notification preferences)
    webhook_event = _KIND_TO_WEBHOOK_EVENT.get(kind)
    if webhook_event:
        try:
            from src.events import dispatch_webhooks

            await dispatch_webhooks(
                db,
                webhook_event,
                {
                    "entity_id": str(entity_id),
                    "kind": kind,
                    "title": title,
                    "body": body,
                    "reference_id": reference_id,
                },
            )
        except Exception:
            pass  # Webhook delivery is best-effort

    # Check notification preferences
    pref_field = _KIND_TO_PREF.get(kind)
    if pref_field:
        pref = await db.scalar(
            select(NotificationPreference).where(
                NotificationPreference.entity_id == entity_id,
            )
        )
        if pref and not getattr(pref, pref_field, True):
            return None

    notif = Notification(
        id=uuid.uuid4(),
        entity_id=entity_id,
        kind=kind,
        title=title,
        body=body,
        reference_id=reference_id,
    )
    db.add(notif)
    await db.flush()

    # Broadcast via WebSocket if available
    try:
        from src.ws import manager

        await manager.send_to_entity(
            str(entity_id),
            "notifications",
            {
                "type": "notification",
                "notification": {
                    "id": str(notif.id),
                    "kind": kind,
                    "title": title,
                    "body": body,
                    "reference_id": reference_id,
                },
            },
        )
    except Exception:
        pass  # WebSocket delivery is best-effort

    return notif


# --- Schemas ---


class NotificationResponse(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    reference_id: str | None
    is_read: bool
    created_at: str

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int
    total: int


# --- Endpoints ---


@router.get("", response_model=NotificationListResponse)
async def get_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get notifications for the current entity."""
    query = select(Notification).where(
        Notification.entity_id == current_entity.id,
    )
    if unread_only:
        query = query.where(Notification.is_read.is_(False))

    query = query.order_by(Notification.created_at.desc()).limit(limit)
    result = await db.execute(query)
    notifications = result.scalars().all()

    # Get counts
    total = await db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.entity_id == current_entity.id,
        )
    ) or 0

    unread_count = await db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.entity_id == current_entity.id,
            Notification.is_read.is_(False),
        )
    ) or 0

    return NotificationListResponse(
        notifications=[
            NotificationResponse(
                id=n.id,
                kind=n.kind,
                title=n.title,
                body=n.body,
                reference_id=n.reference_id,
                is_read=n.is_read,
                created_at=n.created_at.isoformat(),
            )
            for n in notifications
        ],
        unread_count=unread_count,
        total=total,
    )


@router.post("/{notification_id}/read", dependencies=[Depends(rate_limit_writes)])
async def mark_as_read(
    notification_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Mark a notification as read."""
    notif = await db.get(Notification, notification_id)
    if notif is None or notif.entity_id != current_entity.id:
        raise HTTPException(
            status_code=404, detail="Notification not found",
        )

    notif.is_read = True
    await db.flush()
    return {"message": "Marked as read"}


@router.post("/read-all", dependencies=[Depends(rate_limit_writes)])
async def mark_all_as_read(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Mark all notifications as read."""
    result = await db.execute(
        update(Notification)
        .where(
            Notification.entity_id == current_entity.id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    count = result.rowcount
    await db.flush()
    return {"message": f"Marked {count} notifications as read"}


@router.delete("/{notification_id}", dependencies=[Depends(rate_limit_writes)])
async def delete_notification(
    notification_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Delete a notification."""
    notif = await db.get(Notification, notification_id)
    if notif is None or notif.entity_id != current_entity.id:
        raise HTTPException(
            status_code=404, detail="Notification not found",
        )

    await db.delete(notif)
    await db.flush()
    return {"message": "Notification deleted"}


@router.get("/unread-count")
async def unread_count(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get the count of unread notifications."""
    count = await db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.entity_id == current_entity.id,
            Notification.is_read.is_(False),
        )
    ) or 0
    return {"unread_count": count}


# --- Notification Preferences ---


class NotificationPreferencesResponse(BaseModel):
    follow_enabled: bool = True
    reply_enabled: bool = True
    vote_enabled: bool = True
    mention_enabled: bool = True
    endorsement_enabled: bool = True
    review_enabled: bool = True
    moderation_enabled: bool = True


class UpdatePreferencesRequest(BaseModel):
    follow_enabled: bool | None = None
    reply_enabled: bool | None = None
    vote_enabled: bool | None = None
    mention_enabled: bool | None = None
    endorsement_enabled: bool | None = None
    review_enabled: bool | None = None
    moderation_enabled: bool | None = None


@router.get("/preferences", response_model=NotificationPreferencesResponse)
async def get_notification_preferences(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get notification preferences for the current entity."""
    pref = await db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.entity_id == current_entity.id,
        )
    )
    if pref is None:
        return NotificationPreferencesResponse()

    return NotificationPreferencesResponse(
        follow_enabled=pref.follow_enabled,
        reply_enabled=pref.reply_enabled,
        vote_enabled=pref.vote_enabled,
        mention_enabled=pref.mention_enabled,
        endorsement_enabled=pref.endorsement_enabled,
        review_enabled=pref.review_enabled,
        moderation_enabled=pref.moderation_enabled,
    )


@router.patch(
    "/preferences", response_model=NotificationPreferencesResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def update_notification_preferences(
    body: UpdatePreferencesRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Update notification preferences."""
    pref = await db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.entity_id == current_entity.id,
        )
    )
    if pref is None:
        pref = NotificationPreference(
            id=uuid.uuid4(),
            entity_id=current_entity.id,
        )
        db.add(pref)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(pref, field, value)

    await db.flush()
    await db.refresh(pref)

    return NotificationPreferencesResponse(
        follow_enabled=pref.follow_enabled,
        reply_enabled=pref.reply_enabled,
        vote_enabled=pref.vote_enabled,
        mention_enabled=pref.mention_enabled,
        endorsement_enabled=pref.endorsement_enabled,
        review_enabled=pref.review_enabled,
        moderation_enabled=pref.moderation_enabled,
    )
