"""Emergency handlers - network alerts and broadcast protocols.

Provides functions for broadcasting safety alerts across the network
and persisting them for audit trail and dashboard display.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import PropagationAlert

logger = logging.getLogger(__name__)

_VALID_SEVERITIES = {"info", "warning", "critical"}


async def broadcast_network_alert(
    db: AsyncSession,
    alert_type: str,
    message: str,
    severity: str,
    issued_by: uuid.UUID | None = None,
) -> PropagationAlert:
    """Create a PropagationAlert record and broadcast via WebSocket.

    Args:
        db: Database session.
        alert_type: Type of alert (e.g. "freeze", "quarantine", "network_alert").
        message: Human-readable alert message.
        severity: One of "info", "warning", "critical".
        issued_by: Entity ID of the admin who issued the alert (optional).

    Returns:
        The created PropagationAlert record.
    """
    if severity not in _VALID_SEVERITIES:
        raise ValueError(f"Invalid severity: {severity}. Must be one of {_VALID_SEVERITIES}")

    alert = PropagationAlert(
        id=uuid.uuid4(),
        alert_type=alert_type,
        severity=severity,
        message=message,
        issued_by=issued_by,
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)

    # Best-effort WebSocket broadcast
    try:
        from src.ws import manager

        await manager.broadcast_to_channel("safety", {
            "type": "network_alert",
            "alert_type": alert_type,
            "severity": severity,
            "message": message,
            "alert_id": str(alert.id),
        })
    except Exception:
        logger.warning("WebSocket broadcast failed for safety alert", exc_info=True)

    return alert


async def get_recent_alerts(
    db: AsyncSession,
    limit: int = 20,
) -> list[PropagationAlert]:
    """Fetch the most recent propagation alerts.

    Args:
        db: Database session.
        limit: Maximum number of alerts to return.

    Returns:
        List of PropagationAlert records ordered by created_at descending.
    """
    result = await db.execute(
        select(PropagationAlert)
        .order_by(PropagationAlert.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
