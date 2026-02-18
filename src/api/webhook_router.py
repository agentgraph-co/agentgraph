from __future__ import annotations

import hashlib
import secrets
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_writes
from src.database import get_db
from src.models import Entity, WebhookSubscription

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

VALID_EVENT_TYPES = {
    "entity.mentioned",
    "entity.followed",
    "post.created",
    "post.replied",
    "post.voted",
    "dm.received",
    "trust.updated",
    "moderation.flagged",
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
    await db.flush()
    return WebhookResponse(
        id=sub.id,
        callback_url=sub.callback_url,
        event_types=sub.event_types,
        is_active=sub.is_active,
        consecutive_failures=sub.consecutive_failures,
    )
