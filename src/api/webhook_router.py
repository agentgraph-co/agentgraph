from __future__ import annotations

import hashlib
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.database import get_db
from src.models import Entity, WebhookSubscription

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

VALID_EVENT_TYPES = {
    "entity.mentioned",
    "entity.followed",
    "post.replied",
    "post.voted",
    "trust.updated",
    "moderation.flagged",
}


class CreateWebhookRequest(BaseModel):
    callback_url: HttpUrl
    event_types: list[str] = Field(..., min_length=1)

    model_config = {"json_schema_extra": {"examples": [
        {"callback_url": "https://example.com/webhook", "event_types": ["entity.followed"]}
    ]}}


class WebhookResponse(BaseModel):
    id: uuid.UUID
    callback_url: str
    event_types: list[str]
    is_active: bool
    consecutive_failures: int

    model_config = {"from_attributes": True}


class WebhookCreatedResponse(BaseModel):
    webhook: WebhookResponse
    secret: str  # plaintext, shown once


class WebhookListResponse(BaseModel):
    webhooks: list[WebhookResponse]
    count: int


@router.post("", response_model=WebhookCreatedResponse, status_code=201)
async def create_webhook(
    body: CreateWebhookRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    invalid = set(body.event_types) - VALID_EVENT_TYPES
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event types: {', '.join(sorted(invalid))}",
        )

    secret = secrets.token_urlsafe(32)
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()

    sub = WebhookSubscription(
        id=uuid.uuid4(),
        entity_id=current_entity.id,
        callback_url=str(body.callback_url),
        secret_hash=secret_hash,
        event_types=list(body.event_types),
        is_active=True,
        consecutive_failures=0,
    )
    db.add(sub)
    await db.flush()

    return WebhookCreatedResponse(
        webhook=WebhookResponse(
            id=sub.id,
            callback_url=sub.callback_url,
            event_types=sub.event_types,
            is_active=sub.is_active,
            consecutive_failures=sub.consecutive_failures,
        ),
        secret=secret,
    )


@router.get("", response_model=WebhookListResponse)
async def list_webhooks(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.entity_id == current_entity.id,
        )
    )
    subs = result.scalars().all()
    return WebhookListResponse(
        webhooks=[
            WebhookResponse(
                id=s.id,
                callback_url=s.callback_url,
                event_types=s.event_types,
                is_active=s.is_active,
                consecutive_failures=s.consecutive_failures,
            )
            for s in subs
        ],
        count=len(subs),
    )


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    sub = await db.get(WebhookSubscription, webhook_id)
    if sub is None or sub.entity_id != current_entity.id:
        raise HTTPException(status_code=404, detail="Webhook not found")

    await db.delete(sub)
    await db.flush()


@router.patch("/{webhook_id}/activate", response_model=WebhookResponse)
async def activate_webhook(
    webhook_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    sub = await db.get(WebhookSubscription, webhook_id)
    if sub is None or sub.entity_id != current_entity.id:
        raise HTTPException(status_code=404, detail="Webhook not found")

    sub.is_active = True
    sub.consecutive_failures = 0
    await db.flush()
    return WebhookResponse(
        id=sub.id,
        callback_url=sub.callback_url,
        event_types=sub.event_types,
        is_active=sub.is_active,
        consecutive_failures=sub.consecutive_failures,
    )


@router.patch("/{webhook_id}/deactivate", response_model=WebhookResponse)
async def deactivate_webhook(
    webhook_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    sub = await db.get(WebhookSubscription, webhook_id)
    if sub is None or sub.entity_id != current_entity.id:
        raise HTTPException(status_code=404, detail="Webhook not found")

    sub.is_active = False
    await db.flush()
    return WebhookResponse(
        id=sub.id,
        callback_url=sub.callback_url,
        event_types=sub.event_types,
        is_active=sub.is_active,
        consecutive_failures=sub.consecutive_failures,
    )
