"""Tests for AIP delegation MCP tools."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Delegation, Entity


@pytest_asyncio.fixture
async def agent_a(db: AsyncSession) -> Entity:
    eid = uuid.uuid4()
    agent = Entity(
        id=eid,
        email=f"agent_a_{uuid.uuid4().hex[:6]}@test.com",
        display_name="Agent A",
        type="agent",
        is_active=True,
        did_web=f"did:web:agentgraph.co:agents:{eid}",
    )
    db.add(agent)
    await db.flush()
    return agent


@pytest_asyncio.fixture
async def agent_b(db: AsyncSession) -> Entity:
    eid = uuid.uuid4()
    agent = Entity(
        id=eid,
        email=f"agent_b_{uuid.uuid4().hex[:6]}@test.com",
        display_name="Agent B",
        type="agent",
        is_active=True,
        did_web=f"did:web:agentgraph.co:agents:{eid}",
    )
    db.add(agent)
    await db.flush()
    return agent


@pytest.mark.asyncio
async def test_delegate_task_creates_delegation(
    db: AsyncSession, agent_a: Entity, agent_b: Entity,
):
    from src.bridges.mcp_handler import handle_tool_call

    result = await handle_tool_call(
        "agentgraph_delegate_task",
        {
            "delegate_entity_id": str(agent_b.id),
            "task_description": "Summarize this document",
            "timeout_seconds": 1800,
        },
        entity=agent_a,
        db=db,
    )

    assert result["status"] == "pending"
    assert "delegation_id" in result
    assert result["delegate_entity_id"] == str(agent_b.id)

    # Verify in DB
    delegation = await db.get(Delegation, uuid.UUID(result["delegation_id"]))
    assert delegation is not None
    assert delegation.delegator_entity_id == agent_a.id
    assert delegation.delegate_entity_id == agent_b.id
    assert delegation.task_description == "Summarize this document"


@pytest.mark.asyncio
async def test_delegate_task_not_found_target(
    db: AsyncSession, agent_a: Entity,
):
    from src.bridges.mcp_handler import MCPError, handle_tool_call

    with pytest.raises(MCPError, match="not found"):
        await handle_tool_call(
            "agentgraph_delegate_task",
            {
                "delegate_entity_id": str(uuid.uuid4()),
                "task_description": "Test task",
            },
            entity=agent_a,
            db=db,
        )


@pytest.mark.asyncio
async def test_accept_delegation(
    db: AsyncSession, agent_a: Entity, agent_b: Entity,
):
    from src.bridges.mcp_handler import handle_tool_call

    # Create delegation
    create_result = await handle_tool_call(
        "agentgraph_delegate_task",
        {
            "delegate_entity_id": str(agent_b.id),
            "task_description": "Test task",
        },
        entity=agent_a,
        db=db,
    )
    delegation_id = create_result["delegation_id"]

    # Accept as delegate (agent_b)
    accept_result = await handle_tool_call(
        "agentgraph_accept_delegation",
        {"delegation_id": delegation_id, "action": "accept"},
        entity=agent_b,
        db=db,
    )

    assert accept_result["status"] == "accepted"
    assert accept_result["action"] == "accept"


@pytest.mark.asyncio
async def test_reject_delegation(
    db: AsyncSession, agent_a: Entity, agent_b: Entity,
):
    from src.bridges.mcp_handler import handle_tool_call

    create_result = await handle_tool_call(
        "agentgraph_delegate_task",
        {
            "delegate_entity_id": str(agent_b.id),
            "task_description": "Test task",
        },
        entity=agent_a,
        db=db,
    )

    reject_result = await handle_tool_call(
        "agentgraph_accept_delegation",
        {"delegation_id": create_result["delegation_id"], "action": "reject"},
        entity=agent_b,
        db=db,
    )

    assert reject_result["status"] == "rejected"


@pytest.mark.asyncio
async def test_complete_delegation_with_result(
    db: AsyncSession, agent_a: Entity, agent_b: Entity,
):
    from src.bridges.mcp_handler import handle_tool_call

    create_result = await handle_tool_call(
        "agentgraph_delegate_task",
        {
            "delegate_entity_id": str(agent_b.id),
            "task_description": "Summarize X",
        },
        entity=agent_a,
        db=db,
    )
    delegation_id = create_result["delegation_id"]

    # Accept first
    await handle_tool_call(
        "agentgraph_accept_delegation",
        {"delegation_id": delegation_id, "action": "accept"},
        entity=agent_b,
        db=db,
    )

    # Then complete
    complete_result = await handle_tool_call(
        "agentgraph_accept_delegation",
        {
            "delegation_id": delegation_id,
            "action": "complete",
            "result": {"summary": "Here is the summary"},
        },
        entity=agent_b,
        db=db,
    )

    assert complete_result["status"] == "completed"

    delegation = await db.get(Delegation, uuid.UUID(delegation_id))
    assert delegation.result == {"summary": "Here is the summary"}


@pytest.mark.asyncio
async def test_invalid_state_transition(
    db: AsyncSession, agent_a: Entity, agent_b: Entity,
):
    from src.bridges.mcp_handler import MCPError, handle_tool_call

    create_result = await handle_tool_call(
        "agentgraph_delegate_task",
        {
            "delegate_entity_id": str(agent_b.id),
            "task_description": "Test",
        },
        entity=agent_a,
        db=db,
    )

    # Try to complete a pending delegation (should fail — must accept first)
    with pytest.raises(MCPError, match="Cannot complete"):
        await handle_tool_call(
            "agentgraph_accept_delegation",
            {
                "delegation_id": create_result["delegation_id"],
                "action": "complete",
            },
            entity=agent_b,
            db=db,
        )


@pytest.mark.asyncio
async def test_only_delegate_can_update(
    db: AsyncSession, agent_a: Entity, agent_b: Entity,
):
    from src.bridges.mcp_handler import MCPError, handle_tool_call

    create_result = await handle_tool_call(
        "agentgraph_delegate_task",
        {
            "delegate_entity_id": str(agent_b.id),
            "task_description": "Test",
        },
        entity=agent_a,
        db=db,
    )

    # agent_a (the delegator) tries to accept — should fail
    with pytest.raises(MCPError, match="Only the delegate"):
        await handle_tool_call(
            "agentgraph_accept_delegation",
            {
                "delegation_id": create_result["delegation_id"],
                "action": "accept",
            },
            entity=agent_a,
            db=db,
        )


@pytest.mark.asyncio
async def test_list_delegations(
    db: AsyncSession, agent_a: Entity, agent_b: Entity,
):
    from src.bridges.mcp_handler import handle_tool_call

    # Create two delegations
    await handle_tool_call(
        "agentgraph_delegate_task",
        {
            "delegate_entity_id": str(agent_b.id),
            "task_description": "Task 1",
        },
        entity=agent_a,
        db=db,
    )
    await handle_tool_call(
        "agentgraph_delegate_task",
        {
            "delegate_entity_id": str(agent_b.id),
            "task_description": "Task 2",
        },
        entity=agent_a,
        db=db,
    )

    # List as delegator
    result = await handle_tool_call(
        "agentgraph_list_delegations",
        {"role": "delegator"},
        entity=agent_a,
        db=db,
    )
    assert result["count"] >= 2

    # List as delegate
    result = await handle_tool_call(
        "agentgraph_list_delegations",
        {"role": "delegate"},
        entity=agent_b,
        db=db,
    )
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_list_delegations_filter_status(
    db: AsyncSession, agent_a: Entity, agent_b: Entity,
):
    from src.bridges.mcp_handler import handle_tool_call

    await handle_tool_call(
        "agentgraph_delegate_task",
        {
            "delegate_entity_id": str(agent_b.id),
            "task_description": "Filter test",
        },
        entity=agent_a,
        db=db,
    )

    result = await handle_tool_call(
        "agentgraph_list_delegations",
        {"status": "pending"},
        entity=agent_a,
        db=db,
    )
    assert result["count"] >= 1
    assert all(d["status"] == "pending" for d in result["delegations"])


@pytest.mark.asyncio
async def test_discover_agents_via_mcp(
    db: AsyncSession, agent_a: Entity, agent_b: Entity,
):
    from src.bridges.mcp_handler import handle_tool_call

    result = await handle_tool_call(
        "agentgraph_discover_agents",
        {"limit": 10},
        entity=agent_a,
        db=db,
    )
    assert "agents" in result
    assert result["count"] >= 2
    ids = {a["id"] for a in result["agents"]}
    assert str(agent_a.id) in ids
    assert str(agent_b.id) in ids
