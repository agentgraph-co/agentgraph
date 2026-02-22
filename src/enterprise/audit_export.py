"""Audit log export for enterprise compliance."""
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AuditLog, OrganizationMembership


async def export_audit_logs(
    db: AsyncSession,
    org_id: uuid.UUID,
    format: str = "json",
    days: int = 30,
    action_filter: str | None = None,
) -> str | list[dict]:
    """Export audit logs for all members of an organization.

    Args:
        db: Database session.
        org_id: Organization UUID.
        format: Output format -- "json" or "csv".
        days: Number of days to look back.
        action_filter: Optional substring filter on action field.

    Returns:
        List of dicts (json) or CSV string (csv).
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Get all member entity IDs
    members_q = select(OrganizationMembership.entity_id).where(
        OrganizationMembership.organization_id == org_id
    )
    member_result = await db.execute(members_q)
    member_ids = [r[0] for r in member_result.fetchall()]

    if not member_ids:
        return [] if format == "json" else ""

    # Query audit logs
    query = (
        select(AuditLog)
        .where(
            AuditLog.entity_id.in_(member_ids),
            AuditLog.created_at >= since,
        )
        .order_by(AuditLog.created_at.desc())
    )
    if action_filter:
        query = query.where(AuditLog.action.ilike(f"%{action_filter}%"))

    result = await db.execute(query)
    logs = result.scalars().all()

    records = [
        {
            "id": str(log.id),
            "entity_id": str(log.entity_id) if log.entity_id else None,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": str(log.resource_id) if log.resource_id else None,
            "details": log.details or {},
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]

    if format == "csv":
        output = io.StringIO()
        if records:
            writer = csv.DictWriter(output, fieldnames=records[0].keys())
            writer.writeheader()
            for row in records:
                row["details"] = json.dumps(row["details"])
                writer.writerow(row)
        return output.getvalue()

    return records
