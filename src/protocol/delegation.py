"""AIP delegation state machine.

Manages the lifecycle of task delegations between entities:
create -> accept -> in_progress -> completed/failed, with cancel support.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Delegation

# Valid state transitions: {current_status: set(allowed_next_statuses)}
_VALID_TRANSITIONS = {
    "pending": {"accepted", "cancelled", "expired"},
    "accepted": {"in_progress", "completed", "failed", "cancelled"},
    "in_progress": {"completed", "failed", "cancelled"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
    "expired": set(),
}


async def create_delegation(
    db: AsyncSession,
    delegator_id: uuid.UUID,
    delegate_id: uuid.UUID,
    task_description: str,
    constraints: dict | None = None,
    timeout_seconds: int = 3600,
    recurrence: str | None = None,
    max_recurrences: int | None = None,
    parent_delegation_id: uuid.UUID | None = None,
) -> Delegation:
    """Create a new delegation request.

    Parameters
    ----------
    recurrence : str, optional
        Recurrence schedule: "daily", "weekly", or "monthly".
        None means one-shot delegation.
    max_recurrences : int, optional
        Maximum number of recurring executions.  None = unlimited.
    parent_delegation_id : UUID, optional
        If this is a recurring instance, links to the original delegation.
    """
    if recurrence and recurrence not in ("daily", "weekly", "monthly"):
        raise ValueError(f"Invalid recurrence: {recurrence}")

    now = datetime.now(timezone.utc)
    correlation_id = uuid.uuid4().hex[:16]

    delegation = Delegation(
        id=uuid.uuid4(),
        delegator_entity_id=delegator_id,
        delegate_entity_id=delegate_id,
        task_description=task_description,
        constraints=constraints or {},
        status="pending",
        correlation_id=correlation_id,
        timeout_at=now + timedelta(seconds=timeout_seconds),
        created_at=now,
        recurrence=recurrence,
        max_recurrences=max_recurrences,
        parent_delegation_id=parent_delegation_id,
    )
    db.add(delegation)
    await db.flush()
    return delegation


async def accept_delegation(
    db: AsyncSession,
    delegation_id: uuid.UUID,
    delegate_id: uuid.UUID,
) -> Delegation:
    """Accept a pending delegation. Only the delegate can accept."""
    delegation = await _get_and_validate(
        db, delegation_id, delegate_id, role="delegate",
        expected_status="pending", target_status="accepted",
    )
    delegation.status = "accepted"
    delegation.accepted_at = datetime.now(timezone.utc)
    await db.flush()
    return delegation


async def update_delegation_progress(
    db: AsyncSession,
    delegation_id: uuid.UUID,
    delegate_id: uuid.UUID,
    status: str,
    result: dict | None = None,
) -> Delegation:
    """Update delegation status (in_progress/completed/failed).

    Only the delegate can update progress.
    """
    delegation = await _get_delegation_or_raise(db, delegation_id)

    if str(delegation.delegate_entity_id) != str(delegate_id):
        raise PermissionError("Only the delegate can update delegation progress")

    if status not in _VALID_TRANSITIONS.get(delegation.status, set()):
        raise ValueError(
            f"Cannot transition from '{delegation.status}' to '{status}'"
        )

    delegation.status = status
    if result is not None:
        delegation.result = result
    if status in ("completed", "failed"):
        delegation.completed_at = datetime.now(timezone.utc)
    # Increment recurrence count for recurring delegations on completion
    if status == "completed" and delegation.recurrence:
        delegation.recurrence_count = (delegation.recurrence_count or 0) + 1
    await db.flush()
    return delegation


async def reject_delegation(
    db: AsyncSession,
    delegation_id: uuid.UUID,
    delegate_id: uuid.UUID,
) -> Delegation:
    """Reject a pending delegation. Only the delegate can reject."""
    delegation = await _get_delegation_or_raise(db, delegation_id)

    if str(delegation.delegate_entity_id) != str(delegate_id):
        raise PermissionError("Only the delegate can reject a delegation")

    if delegation.status != "pending":
        raise ValueError(
            f"Cannot reject delegation in '{delegation.status}' status"
        )

    delegation.status = "cancelled"
    delegation.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return delegation


async def cancel_delegation(
    db: AsyncSession,
    delegation_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> Delegation:
    """Cancel a delegation. Delegator can cancel pending/accepted/in_progress.

    Delegate can also cancel (reject) a pending delegation.
    """
    delegation = await _get_delegation_or_raise(db, delegation_id)

    is_delegator = str(delegation.delegator_entity_id) == str(entity_id)
    is_delegate = str(delegation.delegate_entity_id) == str(entity_id)

    if not is_delegator and not is_delegate:
        raise PermissionError("Only participants can cancel a delegation")

    if is_delegate and delegation.status != "pending":
        raise PermissionError(
            "Delegate can only cancel (reject) a pending delegation"
        )

    if "cancelled" not in _VALID_TRANSITIONS.get(delegation.status, set()):
        raise ValueError(
            f"Cannot cancel delegation in '{delegation.status}' status"
        )

    delegation.status = "cancelled"
    delegation.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return delegation


async def get_delegation(
    db: AsyncSession,
    delegation_id: uuid.UUID,
) -> Delegation | None:
    """Get a delegation by ID."""
    result = await db.execute(
        select(Delegation).where(Delegation.id == delegation_id)
    )
    return result.scalar_one_or_none()


async def list_delegations(
    db: AsyncSession,
    entity_id: uuid.UUID,
    role: str = "all",
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Delegation]:
    """List delegations for an entity filtered by role and status."""
    query = select(Delegation)

    if role == "delegator":
        query = query.where(Delegation.delegator_entity_id == entity_id)
    elif role == "delegate":
        query = query.where(Delegation.delegate_entity_id == entity_id)
    else:
        # "all" — show delegations where entity is either side
        query = query.where(
            (Delegation.delegator_entity_id == entity_id)
            | (Delegation.delegate_entity_id == entity_id)
        )

    if status:
        query = query.where(Delegation.status == status)

    query = query.order_by(Delegation.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


# --- Internal helpers ---


async def _get_delegation_or_raise(
    db: AsyncSession, delegation_id: uuid.UUID,
) -> Delegation:
    """Fetch a delegation or raise ValueError if not found."""
    result = await db.execute(
        select(Delegation).where(Delegation.id == delegation_id)
    )
    delegation = result.scalar_one_or_none()
    if delegation is None:
        raise ValueError("Delegation not found")
    return delegation


async def _get_and_validate(
    db: AsyncSession,
    delegation_id: uuid.UUID,
    entity_id: uuid.UUID,
    role: str,
    expected_status: str,
    target_status: str,
) -> Delegation:
    """Fetch delegation and validate role + status transition."""
    delegation = await _get_delegation_or_raise(db, delegation_id)

    if role == "delegate":
        if str(delegation.delegate_entity_id) != str(entity_id):
            raise PermissionError("Only the delegate can perform this action")
    elif role == "delegator":
        if str(delegation.delegator_entity_id) != str(entity_id):
            raise PermissionError("Only the delegator can perform this action")

    if delegation.status != expected_status:
        raise ValueError(
            f"Cannot transition from '{delegation.status}' to '{target_status}'"
        )

    return delegation
