"""AIP v2 — Agent Interaction Protocol direct messaging and channels.

Provides agent-to-agent communication with typed messages, named channels,
trust-score capture at send time, and capability negotiation.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.database import get_db
from src.models import (
    AgentCapabilityRegistry,
    AIPChannel,
    AIPMessage,
    Entity,
    TrustScore,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aip/v2", tags=["aip-v2"])


# --- Schemas ---


class SendAIPMessageRequest(BaseModel):
    recipient_entity_id: uuid.UUID
    message_type: str = Field(
        ..., pattern="^(request|response|event|notification)$",
    )
    payload: dict = Field(default_factory=dict)
    channel_id: uuid.UUID | None = None


class AIPMessageResponse(BaseModel):
    id: uuid.UUID
    sender_entity_id: uuid.UUID
    recipient_entity_id: uuid.UUID | None
    channel_id: uuid.UUID | None
    message_type: str
    payload: dict
    sender_trust_score: float | None
    is_read: bool
    created_at: str


class AIPMessageListResponse(BaseModel):
    messages: list[AIPMessageResponse]
    total: int


class CreateChannelRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    participant_ids: list[uuid.UUID] = Field(..., min_length=2)
    description: str | None = None


class AIPChannelResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_by_entity_id: uuid.UUID
    participant_ids: list[str]
    is_active: bool
    created_at: str
    updated_at: str


class ChannelListResponse(BaseModel):
    channels: list[AIPChannelResponse]
    total: int


class NegotiateV2Request(BaseModel):
    target_entity_id: uuid.UUID
    requested_capabilities: list[str] = Field(..., min_length=1)


class NegotiateV2Response(BaseModel):
    target_entity_id: str
    requested: list[str]
    supported: list[str]
    unsupported: list[str]


# --- Helpers ---


def _message_to_response(msg: AIPMessage) -> AIPMessageResponse:
    return AIPMessageResponse(
        id=msg.id,
        sender_entity_id=msg.sender_entity_id,
        recipient_entity_id=msg.recipient_entity_id,
        channel_id=msg.channel_id,
        message_type=msg.message_type,
        payload=msg.payload or {},
        sender_trust_score=msg.sender_trust_score,
        is_read=msg.is_read,
        created_at=msg.created_at.isoformat() if msg.created_at else "",
    )


def _channel_to_response(ch: AIPChannel) -> AIPChannelResponse:
    return AIPChannelResponse(
        id=ch.id,
        name=ch.name,
        description=ch.description,
        created_by_entity_id=ch.created_by_entity_id,
        participant_ids=ch.participant_ids or [],
        is_active=ch.is_active,
        created_at=ch.created_at.isoformat() if ch.created_at else "",
        updated_at=ch.updated_at.isoformat() if ch.updated_at else "",
    )


async def _get_sender_trust(db: AsyncSession, entity_id: uuid.UUID) -> float | None:
    """Fetch the current trust score for the sender, or None."""
    ts = await db.scalar(
        select(TrustScore.score).where(TrustScore.entity_id == entity_id)
    )
    return float(ts) if ts is not None else None


# --- Endpoints ---


@router.post(
    "/messages",
    response_model=AIPMessageResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
async def send_aip_message(
    body: SendAIPMessageRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Send an AIP v2 message to another entity."""
    if body.recipient_entity_id == current_entity.id:
        raise HTTPException(
            status_code=400, detail="Cannot send a message to yourself",
        )

    # Validate recipient exists
    recipient = await db.get(Entity, body.recipient_entity_id)
    if not recipient or not recipient.is_active:
        raise HTTPException(status_code=404, detail="Recipient not found")

    # If channel_id specified, validate it and that both are participants
    if body.channel_id:
        channel = await db.get(AIPChannel, body.channel_id)
        if not channel or not channel.is_active:
            raise HTTPException(status_code=404, detail="Channel not found")
        sender_str = str(current_entity.id)
        recipient_str = str(body.recipient_entity_id)
        participants = channel.participant_ids or []
        if sender_str not in participants:
            raise HTTPException(
                status_code=403, detail="You are not a participant of this channel",
            )
        if recipient_str not in participants:
            raise HTTPException(
                status_code=400,
                detail="Recipient is not a participant of this channel",
            )

    # Capture sender trust score
    trust_score = await _get_sender_trust(db, current_entity.id)

    msg = AIPMessage(
        id=uuid.uuid4(),
        sender_entity_id=current_entity.id,
        recipient_entity_id=body.recipient_entity_id,
        channel_id=body.channel_id,
        message_type=body.message_type,
        payload=body.payload,
        sender_trust_score=trust_score,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)

    return _message_to_response(msg)


@router.get(
    "/messages",
    response_model=AIPMessageListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_inbox(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    message_type: str | None = Query(None, pattern="^(request|response|event|notification)$"),
    since: datetime | None = Query(None),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get AIP v2 inbox (messages received by current entity)."""
    base = select(AIPMessage).where(
        AIPMessage.recipient_entity_id == current_entity.id,
    )

    if message_type:
        base = base.where(AIPMessage.message_type == message_type)
    if since:
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        base = base.where(AIPMessage.created_at >= since)

    total = await db.scalar(
        select(func.count()).select_from(base.subquery()),
    ) or 0

    query = base.order_by(AIPMessage.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    messages = result.scalars().all()

    return AIPMessageListResponse(
        messages=[_message_to_response(m) for m in messages],
        total=total,
    )


@router.post(
    "/channels",
    response_model=AIPChannelResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_writes)],
)
async def create_channel(
    body: CreateChannelRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Create a named AIP v2 channel between 2+ entities."""
    # Creator must be in participants
    if current_entity.id not in body.participant_ids:
        raise HTTPException(
            status_code=400,
            detail="Creator must be included in participant_ids",
        )

    # Validate all participants exist
    for pid in body.participant_ids:
        entity = await db.get(Entity, pid)
        if not entity or not entity.is_active:
            raise HTTPException(
                status_code=404,
                detail=f"Participant {pid} not found",
            )

    channel = AIPChannel(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
        created_by_entity_id=current_entity.id,
        participant_ids=[str(pid) for pid in body.participant_ids],
    )
    db.add(channel)
    await db.flush()
    await db.refresh(channel)

    return _channel_to_response(channel)


@router.get(
    "/channels",
    response_model=ChannelListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def list_channels(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """List AIP v2 channels the current entity participates in."""
    me_str = str(current_entity.id)

    # JSONB contains check — participant_ids is a JSON array of UUID strings
    base = select(AIPChannel).where(
        AIPChannel.is_active.is_(True),
        AIPChannel.participant_ids.contains([me_str]),
    )

    total = await db.scalar(
        select(func.count()).select_from(base.subquery()),
    ) or 0

    query = base.order_by(AIPChannel.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    channels = result.scalars().all()

    return ChannelListResponse(
        channels=[_channel_to_response(ch) for ch in channels],
        total=total,
    )


@router.get(
    "/channels/{channel_id}/messages",
    response_model=AIPMessageListResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_channel_messages(
    channel_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    since: datetime | None = Query(None),
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get message history for an AIP v2 channel."""
    channel = await db.get(AIPChannel, channel_id)
    if not channel or not channel.is_active:
        raise HTTPException(status_code=404, detail="Channel not found")

    me_str = str(current_entity.id)
    if me_str not in (channel.participant_ids or []):
        raise HTTPException(
            status_code=403, detail="Not a participant of this channel",
        )

    base = select(AIPMessage).where(AIPMessage.channel_id == channel_id)

    if since:
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        base = base.where(AIPMessage.created_at >= since)

    total = await db.scalar(
        select(func.count()).select_from(base.subquery()),
    ) or 0

    query = base.order_by(AIPMessage.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    messages = result.scalars().all()

    return AIPMessageListResponse(
        messages=[_message_to_response(m) for m in messages],
        total=total,
    )


@router.post(
    "/negotiate",
    response_model=NegotiateV2Response,
    dependencies=[Depends(rate_limit_reads)],
)
async def negotiate_capabilities(
    body: NegotiateV2Request,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Capability negotiation: check which capabilities the target supports."""
    # Validate target entity exists
    target = await db.get(Entity, body.target_entity_id)
    if not target or not target.is_active:
        raise HTTPException(status_code=404, detail="Target entity not found")

    # Query the capability registry for the target
    result = await db.execute(
        select(AgentCapabilityRegistry.capability_name).where(
            AgentCapabilityRegistry.entity_id == body.target_entity_id,
            AgentCapabilityRegistry.is_active.is_(True),
            AgentCapabilityRegistry.capability_name.in_(body.requested_capabilities),
        )
    )
    found_names = {row[0] for row in result.all()}

    supported = [c for c in body.requested_capabilities if c in found_names]
    unsupported = [c for c in body.requested_capabilities if c not in found_names]

    return NegotiateV2Response(
        target_entity_id=str(body.target_entity_id),
        requested=body.requested_capabilities,
        supported=supported,
        unsupported=unsupported,
    )
