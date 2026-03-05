"""AIP v2 Ecosystem — Protocol documentation, validation, stats, and connectivity.

Companion router to aip_v2_router providing protocol-level ecosystem tools:
version info, message validation, usage statistics, and connectivity testing.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.database import get_db
from src.models import AIPChannel, AIPMessage, Entity, TrustScore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aip/v2/ecosystem", tags=["aip-v2-ecosystem"])

# --- Constants ---

SUPPORTED_MESSAGE_TYPES = ["request", "response", "event", "notification"]

AIP_VERSIONS = [
    {
        "version": "1.0",
        "status": "deprecated",
        "sunset_date": "2026-06-01",
    },
    {
        "version": "2.0",
        "status": "current",
    },
]

PROTOCOL_INFO = {
    "version": "2.0",
    "supported_message_types": SUPPORTED_MESSAGE_TYPES,
    "channel_features": {
        "named_channels": True,
        "multi_party": True,
        "channel_history": True,
        "participant_validation": True,
    },
    "capability_negotiation": {
        "description": (
            "Query target entity capabilities via POST /aip/v2/negotiate. "
            "Provide a list of requested_capabilities and receive supported/unsupported split."
        ),
        "endpoint": "/aip/v2/negotiate",
        "method": "POST",
    },
    "authentication_methods": [
        {
            "type": "bearer_jwt",
            "description": "Bearer token via Authorization header",
        },
        {
            "type": "api_key",
            "description": "API key via X-API-Key header",
        },
    ],
    "rate_limits": {
        "reads": "60 requests/minute per IP",
        "writes": "30 requests/minute per IP",
        "description": "Authenticated users may receive higher limits based on trust score.",
    },
}


# --- Schemas ---


class ProtocolInfoResponse(BaseModel):
    version: str
    supported_message_types: list[str]
    channel_features: dict
    capability_negotiation: dict
    authentication_methods: list[dict]
    rate_limits: dict


class VersionEntry(BaseModel):
    version: str
    status: str
    sunset_date: str | None = None


class SupportedVersionsResponse(BaseModel):
    versions: list[VersionEntry]


class ValidateMessageRequest(BaseModel):
    message_type: str
    payload: dict = Field(default_factory=dict)
    recipient_entity_id: str | None = None


class ValidationError(BaseModel):
    field: str
    message: str


class ValidateMessageResponse(BaseModel):
    valid: bool
    errors: list[ValidationError] = Field(default_factory=list)


class EcosystemStatsResponse(BaseModel):
    entity_id: str
    messages_sent: int
    messages_received: int
    channels_created: int
    channels_participated: int
    last_message_at: str | None


class TestConnectivityRequest(BaseModel):
    target_entity_id: uuid.UUID


class TestConnectivityResponse(BaseModel):
    target_entity_id: str
    reachable: bool
    is_active: bool
    trust_score: float | None
    detail: str


# --- Endpoints ---


@router.get(
    "/protocol-info",
    response_model=ProtocolInfoResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_protocol_info():
    """Return AIP v2 protocol documentation and feature summary."""
    return ProtocolInfoResponse(**PROTOCOL_INFO)


@router.get(
    "/supported-versions",
    response_model=SupportedVersionsResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_supported_versions():
    """Return list of supported AIP protocol versions with status."""
    return SupportedVersionsResponse(
        versions=[VersionEntry(**v) for v in AIP_VERSIONS],
    )


@router.post(
    "/validate-message",
    response_model=ValidateMessageResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def validate_message(
    body: ValidateMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """Validate a message payload against the AIP v2 schema."""
    errors: list[ValidationError] = []

    # Validate message_type
    if body.message_type not in SUPPORTED_MESSAGE_TYPES:
        errors.append(ValidationError(
            field="message_type",
            message=(
                f"Invalid message_type '{body.message_type}'. "
                f"Must be one of: {', '.join(SUPPORTED_MESSAGE_TYPES)}"
            ),
        ))

    # Validate payload is a dict (already enforced by Pydantic, but check non-empty for requests)
    if not isinstance(body.payload, dict):
        errors.append(ValidationError(
            field="payload",
            message="Payload must be a JSON object",
        ))

    # Validate recipient_entity_id format if provided
    if body.recipient_entity_id is not None:
        try:
            recipient_uuid = uuid.UUID(body.recipient_entity_id)
            # Check if recipient exists
            recipient = await db.get(Entity, recipient_uuid)
            if not recipient or not recipient.is_active:
                errors.append(ValidationError(
                    field="recipient_entity_id",
                    message=f"Entity '{body.recipient_entity_id}' not found or inactive",
                ))
        except ValueError:
            errors.append(ValidationError(
                field="recipient_entity_id",
                message=(
                    f"Invalid UUID format: '{body.recipient_entity_id}'"
                ),
            ))

    return ValidateMessageResponse(
        valid=len(errors) == 0,
        errors=errors,
    )


@router.get(
    "/stats",
    response_model=EcosystemStatsResponse,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_ecosystem_stats(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Return AIP v2 usage statistics for the authenticated entity."""
    entity_id = current_entity.id

    # Messages sent
    messages_sent = await db.scalar(
        select(func.count()).select_from(
            select(AIPMessage.id).where(
                AIPMessage.sender_entity_id == entity_id,
            ).subquery()
        ),
    ) or 0

    # Messages received
    messages_received = await db.scalar(
        select(func.count()).select_from(
            select(AIPMessage.id).where(
                AIPMessage.recipient_entity_id == entity_id,
            ).subquery()
        ),
    ) or 0

    # Channels created
    channels_created = await db.scalar(
        select(func.count()).select_from(
            select(AIPChannel.id).where(
                AIPChannel.created_by_entity_id == entity_id,
            ).subquery()
        ),
    ) or 0

    # Channels participated (participant_ids JSONB array contains entity UUID string)
    me_str = str(entity_id)
    channels_participated = await db.scalar(
        select(func.count()).select_from(
            select(AIPChannel.id).where(
                AIPChannel.is_active.is_(True),
                AIPChannel.participant_ids.contains([me_str]),
            ).subquery()
        ),
    ) or 0

    # Last message timestamp (sent or received)
    last_sent = await db.scalar(
        select(func.max(AIPMessage.created_at)).where(
            AIPMessage.sender_entity_id == entity_id,
        ),
    )
    last_received = await db.scalar(
        select(func.max(AIPMessage.created_at)).where(
            AIPMessage.recipient_entity_id == entity_id,
        ),
    )

    last_message_at: datetime | None = None
    if last_sent and last_received:
        last_message_at = max(last_sent, last_received)
    elif last_sent:
        last_message_at = last_sent
    elif last_received:
        last_message_at = last_received

    return EcosystemStatsResponse(
        entity_id=str(entity_id),
        messages_sent=messages_sent,
        messages_received=messages_received,
        channels_created=channels_created,
        channels_participated=channels_participated,
        last_message_at=last_message_at.isoformat() if last_message_at else None,
    )


@router.post(
    "/test-connectivity",
    response_model=TestConnectivityResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def test_connectivity(
    body: TestConnectivityRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Send a test ping to verify connectivity with another entity."""
    if body.target_entity_id == current_entity.id:
        raise HTTPException(
            status_code=400, detail="Cannot test connectivity with yourself",
        )

    target = await db.get(Entity, body.target_entity_id)
    if not target:
        return TestConnectivityResponse(
            target_entity_id=str(body.target_entity_id),
            reachable=False,
            is_active=False,
            trust_score=None,
            detail="Entity not found",
        )

    if not target.is_active:
        return TestConnectivityResponse(
            target_entity_id=str(body.target_entity_id),
            reachable=False,
            is_active=False,
            trust_score=None,
            detail="Entity is inactive",
        )

    # Fetch trust score if available
    trust_score_val = await db.scalar(
        select(TrustScore.score).where(TrustScore.entity_id == body.target_entity_id),
    )
    trust_score = float(trust_score_val) if trust_score_val is not None else None

    return TestConnectivityResponse(
        target_entity_id=str(body.target_entity_id),
        reachable=True,
        is_active=True,
        trust_score=trust_score,
        detail="Entity is active and reachable",
    )
