from __future__ import annotations

import hashlib
import secrets
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.models import Entity, WebhookSubscription

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

VALID_EVENT_TYPES = {
    "entity.mentioned",
    "entity.followed",
    "entity.messaged",
    "post.created",
    "post.replied",
    "post.voted",
    "dm.received",
    "trust.updated",
    "moderation.flagged",
    "endorsement.created",
    "endorsement.removed",
    "evolution.created",
    "marketplace.listing_created",
    "marketplace.purchased",
    "marketplace.cancelled",
    "marketplace.refunded",
}


_BLOCKED_HOSTS = (
    "localhost", "127.0.0.1", "0.0.0.0", "169.254", "10.", "192.168.",
    "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.",
    "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.",
    "172.28.", "172.29.", "172.30.", "172.31.",
    "::1", "[::1]", "fe80:", "fc00:", "fd",
)


def _validate_callback_url(v: HttpUrl | str | None) -> HttpUrl | str | None:
    if v is None:
        return v
    url_str = str(v)
    parsed = urlparse(url_str)
    hostname = parsed.hostname or ""
    for b in _BLOCKED_HOSTS:
        if hostname.startswith(b):
            raise ValueError("callback_url cannot point to internal addresses")
    return v


class UpdateWebhookRequest(BaseModel):
    callback_url: HttpUrl | None = None
    event_types: list[str] | None = Field(None, min_length=1)

    @field_validator("callback_url")
    @classmethod
    def check_ssrf(cls, v: HttpUrl | None) -> HttpUrl | None:
        return _validate_callback_url(v)


class CreateWebhookRequest(BaseModel):
    callback_url: HttpUrl
    event_types: list[str] = Field(..., min_length=1)

    @field_validator("callback_url")
    @classmethod
    def check_ssrf(cls, v: HttpUrl) -> HttpUrl:
        return _validate_callback_url(v)

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


@router.post(
    "", response_model=WebhookCreatedResponse, status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
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

    # Cap webhooks per entity
    existing_count = await db.scalar(
        select(func.count()).select_from(WebhookSubscription).where(
            WebhookSubscription.entity_id == current_entity.id,
            WebhookSubscription.is_active.is_(True),
        )
    ) or 0
    if existing_count >= 10:
        raise HTTPException(
            status_code=409,
            detail="Maximum of 10 active webhooks per entity",
        )

    secret = secrets.token_urlsafe(32)
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()

    sub = WebhookSubscription(
        id=uuid.uuid4(),
        entity_id=current_entity.id,
        callback_url=str(body.callback_url),
        secret_hash=secret_hash,
        signing_key=secret,
        event_types=list(body.event_types),
        is_active=True,
        consecutive_failures=0,
    )
    db.add(sub)
    await log_action(
        db,
        action="webhook.create",
        entity_id=current_entity.id,
        resource_type="webhook",
        resource_id=sub.id,
        details={"event_types": sub.event_types},
    )
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
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    base = select(WebhookSubscription).where(
        WebhookSubscription.entity_id == current_entity.id,
    )
    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0

    result = await db.execute(
        base.order_by(WebhookSubscription.created_at.desc())
        .offset(offset).limit(limit)
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
        count=total,
    )


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get a single webhook by ID."""
    sub = await db.get(WebhookSubscription, webhook_id)
    if sub is None or sub.entity_id != current_entity.id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return WebhookResponse(
        id=sub.id,
        callback_url=sub.callback_url,
        event_types=sub.event_types,
        is_active=sub.is_active,
        consecutive_failures=sub.consecutive_failures,
    )


@router.patch(
    "/{webhook_id}", response_model=WebhookResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def update_webhook(
    webhook_id: uuid.UUID,
    body: UpdateWebhookRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Update webhook callback URL and/or event types."""
    sub = await db.get(WebhookSubscription, webhook_id)
    if sub is None or sub.entity_id != current_entity.id:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if body.event_types is not None:
        invalid = set(body.event_types) - VALID_EVENT_TYPES
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid event types: {', '.join(sorted(invalid))}",
            )
        sub.event_types = list(body.event_types)

    if body.callback_url is not None:
        sub.callback_url = str(body.callback_url)

    await log_action(
        db,
        action="webhook.update",
        entity_id=current_entity.id,
        resource_type="webhook",
        resource_id=sub.id,
    )
    await db.flush()
    return WebhookResponse(
        id=sub.id,
        callback_url=sub.callback_url,
        event_types=sub.event_types,
        is_active=sub.is_active,
        consecutive_failures=sub.consecutive_failures,
    )


@router.delete(
    "/{webhook_id}", status_code=204,
    dependencies=[Depends(rate_limit_writes)],
)
async def delete_webhook(
    webhook_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    sub = await db.get(WebhookSubscription, webhook_id)
    if sub is None or sub.entity_id != current_entity.id:
        raise HTTPException(status_code=404, detail="Webhook not found")

    await log_action(
        db,
        action="webhook.delete",
        entity_id=current_entity.id,
        resource_type="webhook",
        resource_id=sub.id,
    )
    await db.delete(sub)
    await db.flush()


@router.patch(
    "/{webhook_id}/activate", response_model=WebhookResponse,
    dependencies=[Depends(rate_limit_writes)],
)
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
    await log_action(
        db,
        action="webhook.activate",
        entity_id=current_entity.id,
        resource_type="webhook",
        resource_id=webhook_id,
    )
    await db.flush()
    return WebhookResponse(
        id=sub.id,
        callback_url=sub.callback_url,
        event_types=sub.event_types,
        is_active=sub.is_active,
        consecutive_failures=sub.consecutive_failures,
    )


@router.patch(
    "/{webhook_id}/deactivate", response_model=WebhookResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def deactivate_webhook(
    webhook_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    sub = await db.get(WebhookSubscription, webhook_id)
    if sub is None or sub.entity_id != current_entity.id:
        raise HTTPException(status_code=404, detail="Webhook not found")

    sub.is_active = False
    await log_action(
        db,
        action="webhook.deactivate",
        entity_id=current_entity.id,
        resource_type="webhook",
        resource_id=webhook_id,
    )
    await db.flush()
    return WebhookResponse(
        id=sub.id,
        callback_url=sub.callback_url,
        event_types=sub.event_types,
        is_active=sub.is_active,
        consecutive_failures=sub.consecutive_failures,
    )
