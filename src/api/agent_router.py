from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.agent_service import (
    create_agent,
    get_agent_by_id,
    get_operator_agents,
    rotate_api_key,
)
from src.api.deps import get_current_entity
from src.api.schemas import (
    AgentCreatedResponse,
    AgentResponse,
    ApiKeyRotatedResponse,
    CreateAgentRequest,
    MessageResponse,
    UpdateAgentRequest,
)
from src.database import get_db
from src.models import Entity, EntityType

router = APIRouter(prefix="/agents", tags=["agents"])


def _require_human(entity: Entity) -> None:
    if entity.type != EntityType.HUMAN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only humans can manage agents",
        )


def _require_owner(operator: Entity, agent: Entity) -> None:
    if agent.operator_id != operator.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this agent",
        )


@router.post("", response_model=AgentCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_endpoint(
    body: CreateAgentRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    _require_human(current_entity)

    agent, plaintext_key = await create_agent(
        db,
        operator=current_entity,
        display_name=body.display_name,
        capabilities=body.capabilities,
        autonomy_level=body.autonomy_level,
        bio_markdown=body.bio_markdown,
    )
    return AgentCreatedResponse(
        agent=AgentResponse.model_validate(agent),
        api_key=plaintext_key,
    )


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    _require_human(current_entity)
    agents = await get_operator_agents(db, current_entity.id)
    return [AgentResponse.model_validate(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _require_human(current_entity)
    _require_owner(current_entity, agent)
    return AgentResponse.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    body: UpdateAgentRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _require_human(current_entity)
    _require_owner(current_entity, agent)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(agent, field, value)
    await db.flush()

    return AgentResponse.model_validate(agent)


@router.post("/{agent_id}/rotate-key", response_model=ApiKeyRotatedResponse)
async def rotate_key(
    agent_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _require_human(current_entity)
    _require_owner(current_entity, agent)

    new_key = await rotate_api_key(db, agent)
    return ApiKeyRotatedResponse(
        api_key=new_key,
        message="API key rotated. Old key is now revoked.",
    )


@router.delete("/{agent_id}", response_model=MessageResponse)
async def deactivate_agent(
    agent_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    agent = await get_agent_by_id(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    _require_human(current_entity)
    _require_owner(current_entity, agent)

    agent.is_active = False
    await db.flush()
    return MessageResponse(message="Agent deactivated")
