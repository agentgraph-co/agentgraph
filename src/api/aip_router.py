"""AIP v1 REST endpoints.

Provides REST API for the Agent Interaction Protocol: capability discovery,
negotiation, delegation management, service contracts, and protocol schema
introspection.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.audit import log_action
from src.database import get_db
from src.interactions import record_interaction
from src.models import Entity, Listing, ServiceContract
from src.protocol.delegation import (
    accept_delegation,
    cancel_delegation,
    create_delegation,
    get_delegation,
    list_delegations,
    update_delegation_progress,
)
from src.protocol.messages import AIP_V1_SCHEMA
from src.protocol.registry import (
    list_capabilities,
    register_capability,
    search_capabilities,
    unregister_capability,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aip", tags=["aip"])


# --- Request/Response schemas ---


class RegisterCapabilityRequest(BaseModel):
    capability_name: str = Field(..., max_length=200)
    version: str = Field(default="1.0.0", max_length=50)
    description: str = Field(default="")
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)


class NegotiateRequest(BaseModel):
    target_entity_id: str
    capability_name: str
    proposed_terms: dict = Field(default_factory=dict)
    message: str | None = None


class DelegateRequest(BaseModel):
    delegate_entity_id: str
    task_description: str = Field(..., min_length=1)
    constraints: dict = Field(default_factory=dict)
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)
    recurrence: str | None = Field(
        default=None, pattern="^(daily|weekly|monthly)$",
    )
    max_recurrences: int | None = Field(default=None, ge=1)
    parent_delegation_id: str | None = None


class DelegationUpdateRequest(BaseModel):
    action: str = Field(..., pattern="^(accept|reject|complete|fail|in_progress)$")
    result: dict | None = None


class CreateContractRequest(BaseModel):
    provider_entity_id: str
    consumer_entity_id: str
    listing_id: str | None = None
    terms: dict | None = None


class UpdateContractRequest(BaseModel):
    action: str = Field(..., pattern="^(pause|resume|terminate)$")


# --- Helper ---


def _delegation_to_dict(d) -> dict:
    """Serialize a Delegation model to a JSON-safe dict."""
    result = {
        "id": str(d.id),
        "delegator_entity_id": str(d.delegator_entity_id),
        "delegate_entity_id": str(d.delegate_entity_id),
        "task_description": d.task_description,
        "constraints": d.constraints or {},
        "status": d.status,
        "result": d.result,
        "correlation_id": d.correlation_id,
        "timeout_at": d.timeout_at.isoformat() if d.timeout_at else None,
        "accepted_at": d.accepted_at.isoformat() if d.accepted_at else None,
        "completed_at": d.completed_at.isoformat() if d.completed_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "recurrence": d.recurrence,
        "recurrence_count": d.recurrence_count,
        "max_recurrences": d.max_recurrences,
        "parent_delegation_id": str(d.parent_delegation_id) if d.parent_delegation_id else None,
    }
    return result


def _contract_to_dict(c) -> dict:
    """Serialize a ServiceContract model to a JSON-safe dict."""
    return {
        "id": str(c.id),
        "provider_entity_id": str(c.provider_entity_id),
        "consumer_entity_id": str(c.consumer_entity_id),
        "listing_id": str(c.listing_id) if c.listing_id else None,
        "terms": c.terms,
        "status": c.status,
        "paused_by": str(c.paused_by) if c.paused_by else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "terminated_at": c.terminated_at.isoformat() if c.terminated_at else None,
    }


def _capability_to_dict(c) -> dict:
    """Serialize an AgentCapabilityRegistry model to a JSON-safe dict."""
    return {
        "id": str(c.id),
        "entity_id": str(c.entity_id),
        "capability_name": c.capability_name,
        "version": c.version,
        "description": c.description,
        "input_schema": c.input_schema or {},
        "output_schema": c.output_schema or {},
        "is_active": c.is_active,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


# --- Endpoints ---


@router.get("/schema")
async def get_aip_schema() -> dict:
    """Return AIP v1 JSON schema (self-documenting protocol description)."""
    return AIP_V1_SCHEMA


@router.get("/discover")
async def discover_agents(
    request=Depends(rate_limit_reads),
    capability: str | None = Query(None, description="Capability name to search for"),
    min_trust_score: float | None = Query(None, ge=0.0, le=1.0),
    framework: str | None = Query(None),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Discover agents by capability, trust score, or framework."""
    results = await search_capabilities(
        db,
        capability_name=capability,
        min_trust=min_trust_score,
        framework=framework,
        limit=limit,
    )
    return {"agents": results, "count": len(results)}


@router.post("/negotiate")
async def negotiate_capability(
    body: NegotiateRequest,
    request=Depends(rate_limit_writes),
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Initiate a capability negotiation with another entity."""
    from src.content_filter import check_content, sanitize_html

    if body.message:
        filter_result = check_content(body.message)
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Message rejected: {', '.join(filter_result.flags)}",
            )
        body.message = sanitize_html(body.message)

    # Create an audit record for the negotiation attempt
    await log_action(
        db,
        action="aip.negotiate",
        entity_id=entity.id,
        details={
            "target_entity_id": body.target_entity_id,
            "capability_name": body.capability_name,
            "proposed_terms": body.proposed_terms,
        },
    )

    return {
        "status": "negotiation_initiated",
        "initiator_id": str(entity.id),
        "target_entity_id": body.target_entity_id,
        "capability_name": body.capability_name,
        "proposed_terms": body.proposed_terms,
        "message": body.message,
    }


@router.post("/delegate", status_code=201)
async def create_delegation_endpoint(
    body: DelegateRequest,
    request=Depends(rate_limit_writes),
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new delegation request to another entity."""
    from src.content_filter import check_content, sanitize_html

    filter_result = check_content(body.task_description)
    if not filter_result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Task description rejected: {', '.join(filter_result.flags)}",
        )
    body.task_description = sanitize_html(body.task_description)

    try:
        delegate_uuid = uuid.UUID(body.delegate_entity_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid delegate_entity_id")

    if delegate_uuid == entity.id:
        raise HTTPException(status_code=400, detail="Cannot delegate to yourself")

    parent_uuid = None
    if body.parent_delegation_id:
        try:
            parent_uuid = uuid.UUID(body.parent_delegation_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid parent_delegation_id")

    delegation = await create_delegation(
        db,
        delegator_id=entity.id,
        delegate_id=delegate_uuid,
        task_description=body.task_description,
        constraints=body.constraints,
        timeout_seconds=body.timeout_seconds,
        recurrence=body.recurrence,
        max_recurrences=body.max_recurrences,
        parent_delegation_id=parent_uuid,
    )

    # Record interaction
    interaction_type = "recurring_delegation" if body.recurrence else "delegation"
    await record_interaction(
        db,
        entity_a_id=entity.id,
        entity_b_id=delegate_uuid,
        interaction_type=interaction_type,
        context={
            "delegation_id": str(delegation.id),
            "recurrence": body.recurrence,
        },
    )

    await log_action(
        db,
        action="aip.delegate.create",
        entity_id=entity.id,
        resource_type="delegation",
        resource_id=delegation.id,
        details={
            "delegate_entity_id": body.delegate_entity_id,
            "task_description": body.task_description,
            "recurrence": body.recurrence,
        },
    )

    return _delegation_to_dict(delegation)


@router.get("/delegations")
async def list_delegations_endpoint(
    request=Depends(rate_limit_reads),
    role: str = Query("all", pattern="^(delegator|delegate|all)$"),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List delegations for the current entity."""
    delegations = await list_delegations(
        db, entity.id, role=role, status=status, limit=limit, offset=offset,
    )
    return {
        "delegations": [_delegation_to_dict(d) for d in delegations],
        "count": len(delegations),
    }


@router.get("/delegations/{delegation_id}")
async def get_delegation_endpoint(
    delegation_id: uuid.UUID,
    request=Depends(rate_limit_reads),
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get delegation details. Must be delegator or delegate."""
    delegation = await get_delegation(db, delegation_id)
    if delegation is None:
        raise HTTPException(status_code=404, detail="Delegation not found")

    # Only participants can view
    if (
        delegation.delegator_entity_id != entity.id
        and delegation.delegate_entity_id != entity.id
    ):
        raise HTTPException(status_code=403, detail="Not a participant of this delegation")

    return _delegation_to_dict(delegation)


@router.patch("/delegations/{delegation_id}")
async def update_delegation_endpoint(
    delegation_id: uuid.UUID,
    body: DelegationUpdateRequest,
    request=Depends(rate_limit_writes),
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update a delegation: accept, reject, complete, fail, or mark in_progress."""
    try:
        action = body.action
        if action == "accept":
            delegation = await accept_delegation(db, delegation_id, entity.id)
        elif action == "reject":
            # Reject is treated as cancel by the delegate
            delegation = await cancel_delegation(db, delegation_id, entity.id)
        elif action == "complete":
            delegation = await update_delegation_progress(
                db, delegation_id, entity.id, status="completed", result=body.result,
            )
        elif action == "fail":
            delegation = await update_delegation_progress(
                db, delegation_id, entity.id, status="failed", result=body.result,
            )
        elif action == "in_progress":
            delegation = await update_delegation_progress(
                db, delegation_id, entity.id, status="in_progress",
            )
        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

        # Record interaction for completed recurring delegations
        if action == "complete" and delegation.recurrence:
            await record_interaction(
                db,
                entity_a_id=delegation.delegate_entity_id,
                entity_b_id=delegation.delegator_entity_id,
                interaction_type="recurring_delegation",
                context={
                    "delegation_id": str(delegation_id),
                    "action": "completed",
                    "recurrence_count": delegation.recurrence_count,
                },
            )

        await log_action(
            db,
            action=f"aip.delegate.{action}",
            entity_id=entity.id,
            resource_type="delegation",
            resource_id=delegation_id,
        )

        return _delegation_to_dict(delegation)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/capabilities/{entity_id}")
async def get_entity_capabilities(
    entity_id: uuid.UUID,
    request=Depends(rate_limit_reads),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get registered capabilities for a specific entity."""
    caps = await list_capabilities(db, entity_id)
    return {
        "entity_id": str(entity_id),
        "capabilities": [_capability_to_dict(c) for c in caps],
        "count": len(caps),
    }


@router.post("/capabilities", status_code=201)
async def register_capability_endpoint(
    body: RegisterCapabilityRequest,
    request=Depends(rate_limit_writes),
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Register a new capability for the current entity."""
    from src.content_filter import check_content, sanitize_html

    if body.description:
        filter_result = check_content(body.description)
        if not filter_result.is_clean:
            raise HTTPException(
                status_code=400,
                detail=f"Description rejected: {', '.join(filter_result.flags)}",
            )
        body.description = sanitize_html(body.description)

    filter_result = check_content(body.capability_name)
    if not filter_result.is_clean:
        raise HTTPException(
            status_code=400,
            detail=f"Capability name rejected: {', '.join(filter_result.flags)}",
        )

    try:
        cap = await register_capability(
            db,
            entity_id=entity.id,
            name=body.capability_name,
            version=body.version,
            description=body.description,
            input_schema=body.input_schema,
            output_schema=body.output_schema,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    await log_action(
        db,
        action="aip.capability.register",
        entity_id=entity.id,
        resource_type="capability",
        resource_id=cap.id,
        details={"capability_name": body.capability_name},
    )

    return _capability_to_dict(cap)


@router.delete("/capabilities/{capability_id}")
async def unregister_capability_endpoint(
    capability_id: uuid.UUID,
    request=Depends(rate_limit_writes),
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Unregister (deactivate) a capability."""
    removed = await unregister_capability(db, entity.id, capability_id)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail="Capability not found or not owned by you",
        )

    await log_action(
        db,
        action="aip.capability.unregister",
        entity_id=entity.id,
        resource_type="capability",
        resource_id=capability_id,
    )

    return {"status": "unregistered", "capability_id": str(capability_id)}


# --- Service Contract Endpoints ---


@router.post("/contracts", status_code=201)
async def create_contract(
    body: CreateContractRequest,
    request=Depends(rate_limit_writes),
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a service contract between a provider and consumer."""
    try:
        provider_uuid = uuid.UUID(body.provider_entity_id)
        consumer_uuid = uuid.UUID(body.consumer_entity_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entity ID format")

    # Caller must be either provider or consumer
    if entity.id != provider_uuid and entity.id != consumer_uuid:
        raise HTTPException(
            status_code=403,
            detail="You must be either the provider or consumer to create a contract",
        )

    if provider_uuid == consumer_uuid:
        raise HTTPException(
            status_code=400, detail="Provider and consumer must be different entities",
        )

    # Validate both entities exist
    provider = await db.get(Entity, provider_uuid)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider entity not found")
    consumer = await db.get(Entity, consumer_uuid)
    if consumer is None:
        raise HTTPException(status_code=404, detail="Consumer entity not found")

    # Validate listing if provided
    listing_uuid = None
    if body.listing_id:
        try:
            listing_uuid = uuid.UUID(body.listing_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid listing_id format")
        listing = await db.get(Listing, listing_uuid)
        if listing is None:
            raise HTTPException(status_code=404, detail="Listing not found")

    contract = ServiceContract(
        id=uuid.uuid4(),
        provider_entity_id=provider_uuid,
        consumer_entity_id=consumer_uuid,
        listing_id=listing_uuid,
        terms=body.terms,
        status="active",
    )
    db.add(contract)
    await db.flush()
    await db.refresh(contract)

    # Record interaction
    await record_interaction(
        db,
        entity_a_id=provider_uuid,
        entity_b_id=consumer_uuid,
        interaction_type="service_contract",
        context={"contract_id": str(contract.id), "action": "created"},
    )

    await log_action(
        db,
        action="aip.contract.create",
        entity_id=entity.id,
        resource_type="service_contract",
        resource_id=contract.id,
        details={
            "provider_entity_id": str(provider_uuid),
            "consumer_entity_id": str(consumer_uuid),
        },
    )

    return _contract_to_dict(contract)


@router.get("/contracts")
async def list_contracts(
    request=Depends(rate_limit_reads),
    status: str | None = Query(None, pattern="^(active|paused|terminated)$"),
    role: str = Query("all", pattern="^(provider|consumer|all)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List service contracts for the current entity."""
    query = select(ServiceContract)

    if role == "provider":
        query = query.where(ServiceContract.provider_entity_id == entity.id)
    elif role == "consumer":
        query = query.where(ServiceContract.consumer_entity_id == entity.id)
    else:
        query = query.where(
            (ServiceContract.provider_entity_id == entity.id)
            | (ServiceContract.consumer_entity_id == entity.id)
        )

    if status:
        query = query.where(ServiceContract.status == status)

    query = query.order_by(ServiceContract.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    contracts = result.scalars().all()

    return {
        "contracts": [_contract_to_dict(c) for c in contracts],
        "count": len(contracts),
    }


@router.get("/contracts/{contract_id}")
async def get_contract(
    contract_id: uuid.UUID,
    request=Depends(rate_limit_reads),
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get contract details with delegation history. Must be provider or consumer."""
    contract = await db.get(ServiceContract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    if (
        contract.provider_entity_id != entity.id
        and contract.consumer_entity_id != entity.id
    ):
        raise HTTPException(
            status_code=403, detail="Not a participant of this contract",
        )

    contract_data = _contract_to_dict(contract)

    # Include delegation history linked by the same provider/consumer pair
    from src.models import Delegation

    deleg_query = select(Delegation).where(
        Delegation.delegator_entity_id.in_(
            [contract.provider_entity_id, contract.consumer_entity_id]
        ),
        Delegation.delegate_entity_id.in_(
            [contract.provider_entity_id, contract.consumer_entity_id]
        ),
    ).order_by(Delegation.created_at.desc()).limit(50)

    deleg_result = await db.execute(deleg_query)
    delegations = deleg_result.scalars().all()
    contract_data["delegations"] = [_delegation_to_dict(d) for d in delegations]

    return contract_data


@router.patch("/contracts/{contract_id}")
async def update_contract(
    contract_id: uuid.UUID,
    body: UpdateContractRequest,
    request=Depends(rate_limit_writes),
    entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update contract status: pause, resume, or terminate."""
    contract = await db.get(ServiceContract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    is_provider = contract.provider_entity_id == entity.id
    is_consumer = contract.consumer_entity_id == entity.id

    if not is_provider and not is_consumer:
        raise HTTPException(
            status_code=403, detail="Not a participant of this contract",
        )

    action = body.action

    if action == "pause":
        if contract.status != "active":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot pause contract in '{contract.status}' status",
            )
        contract.status = "paused"
        contract.paused_by = entity.id

    elif action == "resume":
        if contract.status != "paused":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot resume contract in '{contract.status}' status",
            )
        # Only the party that paused can resume
        if contract.paused_by and contract.paused_by != entity.id:
            raise HTTPException(
                status_code=403,
                detail="Only the party that paused the contract can resume it",
            )
        contract.status = "active"
        contract.paused_by = None

    elif action == "terminate":
        if contract.status == "terminated":
            raise HTTPException(
                status_code=400, detail="Contract is already terminated",
            )
        contract.status = "terminated"
        contract.terminated_at = datetime.now(timezone.utc)

    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

    await db.flush()
    await db.refresh(contract)

    # Record interaction for contract state change
    other_entity_id = (
        contract.consumer_entity_id if is_provider else contract.provider_entity_id
    )
    await record_interaction(
        db,
        entity_a_id=entity.id,
        entity_b_id=other_entity_id,
        interaction_type="service_contract",
        context={"contract_id": str(contract.id), "action": action},
    )

    await log_action(
        db,
        action=f"aip.contract.{action}",
        entity_id=entity.id,
        resource_type="service_contract",
        resource_id=contract.id,
    )

    return _contract_to_dict(contract)
