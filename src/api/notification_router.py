"""In-app notification endpoints.

Provides notification management for entity activities like
follows, replies, votes, and mentions.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.deps import get_current_entity
from src.models import Entity

router = APIRouter(prefix="/notifications", tags=["notifications"])


# --- In-memory notification store (will be migrated to DB table) ---

_notifications: dict[str, list[dict]] = {}  # entity_id -> [notification]


def _add_notification(
    entity_id: uuid.UUID,
    kind: str,
    title: str,
    body: str,
    reference_id: str | None = None,
) -> dict:
    """Create a notification for an entity."""
    key = str(entity_id)
    if key not in _notifications:
        _notifications[key] = []

    notif = {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "title": title,
        "body": body,
        "reference_id": reference_id,
        "is_read": False,
        "created_at": datetime.utcnow().isoformat(),
    }
    _notifications[key].insert(0, notif)

    # Cap at 200 notifications per entity
    if len(_notifications[key]) > 200:
        _notifications[key] = _notifications[key][:200]

    return notif


def clear_notifications() -> None:
    """Clear all notifications. Used in testing."""
    _notifications.clear()


# --- Schemas ---


class NotificationResponse(BaseModel):
    id: str
    kind: str
    title: str
    body: str
    reference_id: str | None
    is_read: bool
    created_at: str


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
):
    """Get notifications for the current entity."""
    key = str(current_entity.id)
    all_notifs = _notifications.get(key, [])

    if unread_only:
        filtered = [n for n in all_notifs if not n["is_read"]]
    else:
        filtered = all_notifs

    unread_count = sum(1 for n in all_notifs if not n["is_read"])

    return NotificationListResponse(
        notifications=[
            NotificationResponse(**n) for n in filtered[:limit]
        ],
        unread_count=unread_count,
        total=len(all_notifs),
    )


@router.post("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    current_entity: Entity = Depends(get_current_entity),
):
    """Mark a notification as read."""
    key = str(current_entity.id)
    notifs = _notifications.get(key, [])

    for n in notifs:
        if n["id"] == notification_id:
            n["is_read"] = True
            return {"message": "Marked as read"}

    raise HTTPException(status_code=404, detail="Notification not found")


@router.post("/read-all")
async def mark_all_as_read(
    current_entity: Entity = Depends(get_current_entity),
):
    """Mark all notifications as read."""
    key = str(current_entity.id)
    notifs = _notifications.get(key, [])

    count = 0
    for n in notifs:
        if not n["is_read"]:
            n["is_read"] = True
            count += 1

    return {"message": f"Marked {count} notifications as read"}


@router.get("/unread-count")
async def unread_count(
    current_entity: Entity = Depends(get_current_entity),
):
    """Get the count of unread notifications."""
    key = str(current_entity.id)
    notifs = _notifications.get(key, [])
    count = sum(1 for n in notifs if not n["is_read"])
    return {"unread_count": count}
