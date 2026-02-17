"""Audit logging for security-critical actions.

Provides an immutable audit trail for compliance and trust.
All security-relevant actions should be logged here.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AuditLog


async def log_action(
    db: AsyncSession,
    action: str,
    entity_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Record an audit log entry."""
    entry = AuditLog(
        id=uuid.uuid4(),
        entity_id=entity_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()
    return entry
