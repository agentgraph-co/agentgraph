"""AIP v1 message schema definitions.

Defines the structured JSON message types used for agent-to-agent
communication over REST and WebSocket channels.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class AIPMessageType(str, enum.Enum):
    DISCOVER_REQUEST = "discover_request"
    DISCOVER_RESPONSE = "discover_response"
    NEGOTIATE_REQUEST = "negotiate_request"
    NEGOTIATE_RESPONSE = "negotiate_response"
    DELEGATE_REQUEST = "delegate_request"
    DELEGATE_STATUS = "delegate_status"
    EVOLVE_NOTIFICATION = "evolve_notification"
    ACK = "ack"
    ERROR = "error"


class AIPMessage(BaseModel):
    """Top-level AIP protocol message envelope."""

    type: AIPMessageType
    correlation_id: str = Field(..., max_length=64)
    sender_id: str
    payload: dict = Field(default_factory=dict)
    timestamp: str | None = None

    def with_timestamp(self) -> AIPMessage:
        """Return a copy with the current UTC timestamp set."""
        return self.model_copy(
            update={"timestamp": datetime.now(timezone.utc).isoformat()},
        )


# --- Specific payload schemas ---


class DiscoverPayload(BaseModel):
    """Payload for discover_request messages."""

    capability: str | None = None
    min_trust_score: float | None = None
    framework: str | None = None
    limit: int = 10


class NegotiatePayload(BaseModel):
    """Payload for negotiate_request messages."""

    capability_name: str
    proposed_terms: dict = Field(default_factory=dict)
    message: str | None = None


class DelegatePayload(BaseModel):
    """Payload for delegate_request messages."""

    task_description: str
    constraints: dict = Field(default_factory=dict)
    timeout_seconds: int = 3600


class DelegateStatusPayload(BaseModel):
    """Payload for delegate_status messages."""

    delegation_id: str
    status: str
    result: dict | None = None


class ErrorPayload(BaseModel):
    """Payload for error messages."""

    code: str
    message: str
    details: dict = Field(default_factory=dict)


# --- AIP v1 schema descriptor ---

AIP_V1_SCHEMA = {
    "protocol": "AIP",
    "version": "1.0.0",
    "description": (
        "Agent Interaction Protocol v1 — structured JSON protocol "
        "for agent-to-agent communication"
    ),
    "message_types": {
        msg_type.value: msg_type.value.replace("_", " ").title()
        for msg_type in AIPMessageType
    },
    "transport": ["REST", "WebSocket"],
    "payload_schemas": {
        "discover_request": {
            "capability": "string | null",
            "min_trust_score": "float | null",
            "framework": "string | null",
            "limit": "int (default 10)",
        },
        "negotiate_request": {
            "capability_name": "string (required)",
            "proposed_terms": "object",
            "message": "string | null",
        },
        "delegate_request": {
            "task_description": "string (required)",
            "constraints": "object",
            "timeout_seconds": "int (default 3600)",
        },
        "delegate_status": {
            "delegation_id": "string (required)",
            "status": "string (required)",
            "result": "object | null",
        },
        "error": {
            "code": "string (required)",
            "message": "string (required)",
            "details": "object",
        },
    },
}
