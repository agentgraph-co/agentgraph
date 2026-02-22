"""AIP message router for WebSocket-based agent communication.

Routes incoming AIP protocol messages to the appropriate handler
(discover, negotiate, delegate) and returns response messages.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.protocol.delegation import (
    accept_delegation,
    cancel_delegation,
    create_delegation,
    update_delegation_progress,
)
from src.protocol.messages import AIPMessageType
from src.protocol.registry import search_capabilities

logger = logging.getLogger(__name__)


def _make_response(
    msg_type: str,
    correlation_id: str,
    sender_id: str,
    payload: dict,
) -> dict:
    """Build a standard AIP response message dict."""
    return {
        "type": msg_type,
        "correlation_id": correlation_id,
        "sender_id": sender_id,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _make_error(
    correlation_id: str,
    code: str,
    message: str,
    details: dict | None = None,
) -> dict:
    """Build an AIP error response."""
    return _make_response(
        AIPMessageType.ERROR.value,
        correlation_id,
        "system",
        {"code": code, "message": message, "details": details or {}},
    )


async def handle_aip_message(
    db: AsyncSession,
    entity_id: str,
    message: dict,
) -> dict | None:
    """Route an incoming AIP message to the appropriate handler.

    Returns a response dict or None.
    """
    msg_type = message.get("type")
    correlation_id = message.get("correlation_id", uuid.uuid4().hex[:16])
    payload = message.get("payload", {})

    try:
        if msg_type == AIPMessageType.DISCOVER_REQUEST.value:
            return await _handle_discover(db, entity_id, correlation_id, payload)
        elif msg_type == AIPMessageType.DELEGATE_REQUEST.value:
            return await _handle_delegate(db, entity_id, correlation_id, payload)
        elif msg_type == AIPMessageType.DELEGATE_STATUS.value:
            return await _handle_delegate_status(db, entity_id, correlation_id, payload)
        elif msg_type == AIPMessageType.ACK.value:
            # ACKs don't need a response
            return None
        else:
            return _make_error(
                correlation_id,
                "UNKNOWN_MESSAGE_TYPE",
                f"Unknown or unsupported message type: {msg_type}",
            )
    except Exception as exc:
        logger.exception("Error handling AIP message type=%s", msg_type)
        return _make_error(
            correlation_id,
            "INTERNAL_ERROR",
            str(exc),
        )


async def _handle_discover(
    db: AsyncSession,
    entity_id: str,
    correlation_id: str,
    payload: dict,
) -> dict:
    """Handle discover_request: search for agents by capability."""
    results = await search_capabilities(
        db,
        capability_name=payload.get("capability"),
        min_trust=payload.get("min_trust_score"),
        framework=payload.get("framework"),
        limit=payload.get("limit", 10),
    )
    return _make_response(
        AIPMessageType.DISCOVER_RESPONSE.value,
        correlation_id,
        "system",
        {"agents": results},
    )


async def _handle_delegate(
    db: AsyncSession,
    entity_id: str,
    correlation_id: str,
    payload: dict,
) -> dict:
    """Handle delegate_request: create a new delegation."""
    delegate_id = payload.get("delegate_entity_id")
    if not delegate_id:
        return _make_error(
            correlation_id,
            "MISSING_FIELD",
            "delegate_entity_id is required in payload",
        )

    try:
        delegation = await create_delegation(
            db,
            delegator_id=uuid.UUID(entity_id),
            delegate_id=uuid.UUID(delegate_id),
            task_description=payload.get("task_description", ""),
            constraints=payload.get("constraints", {}),
            timeout_seconds=payload.get("timeout_seconds", 3600),
        )
        return _make_response(
            AIPMessageType.ACK.value,
            correlation_id,
            "system",
            {
                "delegation_id": str(delegation.id),
                "correlation_id": delegation.correlation_id,
                "status": delegation.status,
            },
        )
    except Exception as exc:
        return _make_error(correlation_id, "DELEGATE_ERROR", str(exc))


async def _handle_delegate_status(
    db: AsyncSession,
    entity_id: str,
    correlation_id: str,
    payload: dict,
) -> dict:
    """Handle delegate_status: update an existing delegation."""
    delegation_id_str = payload.get("delegation_id")
    action = payload.get("status") or payload.get("action")

    if not delegation_id_str or not action:
        return _make_error(
            correlation_id,
            "MISSING_FIELD",
            "delegation_id and status/action are required",
        )

    try:
        delegation_id = uuid.UUID(delegation_id_str)
        if action == "accept":
            delegation = await accept_delegation(
                db, delegation_id, uuid.UUID(entity_id),
            )
        elif action == "cancel":
            delegation = await cancel_delegation(
                db, delegation_id, uuid.UUID(entity_id),
            )
        else:
            delegation = await update_delegation_progress(
                db,
                delegation_id,
                uuid.UUID(entity_id),
                status=action,
                result=payload.get("result"),
            )

        return _make_response(
            AIPMessageType.ACK.value,
            correlation_id,
            "system",
            {
                "delegation_id": str(delegation.id),
                "status": delegation.status,
            },
        )
    except (ValueError, PermissionError) as exc:
        return _make_error(correlation_id, "DELEGATION_ERROR", str(exc))
