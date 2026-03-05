"""Tests for interaction analytics instrumentation."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, EntityType, InteractionEvent, TrustScore


@pytest_asyncio.fixture
async def agent_a(db: AsyncSession) -> Entity:
    eid = uuid.uuid4()
    agent = Entity(
        id=eid,
        email=f"ia_a_{uuid.uuid4().hex[:6]}@test.com",
        display_name="AgentA",
        type=EntityType.AGENT,
        is_active=True,
        did_web=f"did:web:agentgraph.io:agents:{eid}",
        framework_source="pydantic_ai",
        framework_trust_modifier=0.90,
    )
    db.add(agent)
    ts = TrustScore(id=uuid.uuid4(), entity_id=eid, score=0.80)
    db.add(ts)
    await db.flush()
    return agent


@pytest_asyncio.fixture
async def agent_b(db: AsyncSession) -> Entity:
    eid = uuid.uuid4()
    agent = Entity(
        id=eid,
        email=f"ia_b_{uuid.uuid4().hex[:6]}@test.com",
        display_name="AgentB",
        type=EntityType.AGENT,
        is_active=True,
        did_web=f"did:web:agentgraph.io:agents:{eid}",
        framework_source="crewai",
        framework_trust_modifier=0.85,
    )
    db.add(agent)
    ts = TrustScore(id=uuid.uuid4(), entity_id=eid, score=0.70)
    db.add(ts)
    await db.flush()
    return agent


@pytest.mark.asyncio
async def test_interaction_logs_event(
    db: AsyncSession, agent_a: Entity, agent_b: Entity
):
    """verify_interaction logs an InteractionEvent."""
    from src.protocol.a2a_middleware import verify_interaction

    verdict = await verify_interaction(
        str(agent_a.id), str(agent_b.id), "delegate", db=db,
    )
    assert verdict.allowed is True

    # Check that an InteractionEvent was created
    result = await db.execute(
        select(InteractionEvent).where(
            InteractionEvent.entity_a_id == agent_a.id,
            InteractionEvent.entity_b_id == agent_b.id,
            InteractionEvent.interaction_type == "a2a.delegate",
        )
    )
    event = result.scalar_one_or_none()
    assert event is not None
    assert event.context["allowed"] is True
    assert event.context["initiator_trust_score"] == 0.80
    assert event.context["trust_threshold"] == 0.6
    assert event.context["correlation_id"] == verdict.context.correlation_id


@pytest.mark.asyncio
async def test_cross_framework_detected(
    db: AsyncSession, agent_a: Entity, agent_b: Entity
):
    """Cross-framework interactions are flagged in context."""
    from src.protocol.a2a_middleware import verify_interaction

    await verify_interaction(
        str(agent_a.id), str(agent_b.id), "collaborate", db=db,
    )

    result = await db.execute(
        select(InteractionEvent).where(
            InteractionEvent.entity_a_id == agent_a.id,
            InteractionEvent.interaction_type == "a2a.collaborate",
        )
    )
    event = result.scalar_one_or_none()
    assert event is not None
    assert event.context["initiator_framework"] == "pydantic_ai"
    assert event.context["target_framework"] == "crewai"
    assert event.context["is_cross_framework"] is True


@pytest.mark.asyncio
async def test_same_framework_not_cross(
    db: AsyncSession, agent_a: Entity
):
    """Same-framework interactions are not flagged as cross-framework."""
    from src.protocol.a2a_middleware import verify_interaction

    # Create another pydantic_ai agent
    eid = uuid.uuid4()
    agent_c = Entity(
        id=eid,
        display_name="AgentC",
        type=EntityType.AGENT,
        is_active=True,
        did_web=f"did:web:agentgraph.io:agents:{eid}",
        framework_source="pydantic_ai",
        framework_trust_modifier=0.90,
    )
    db.add(agent_c)
    ts = TrustScore(id=uuid.uuid4(), entity_id=eid, score=0.70)
    db.add(ts)
    await db.flush()

    await verify_interaction(
        str(agent_a.id), str(agent_c.id), "delegate", db=db,
    )

    result = await db.execute(
        select(InteractionEvent).where(
            InteractionEvent.entity_a_id == agent_a.id,
            InteractionEvent.entity_b_id == agent_c.id,
        )
    )
    event = result.scalar_one_or_none()
    assert event is not None
    assert event.context["is_cross_framework"] is False


@pytest.mark.asyncio
async def test_denied_interaction_logged(
    db: AsyncSession, agent_b: Entity, agent_a: Entity
):
    """Denied interactions are also logged."""
    from src.protocol.a2a_middleware import verify_interaction

    # agent_b has 0.70 * 0.85 = 0.595 < 0.8 threshold for financial
    verdict = await verify_interaction(
        str(agent_b.id), str(agent_a.id), "financial", db=db,
    )
    assert verdict.allowed is False

    result = await db.execute(
        select(InteractionEvent).where(
            InteractionEvent.entity_a_id == agent_b.id,
            InteractionEvent.interaction_type == "a2a.financial",
        )
    )
    event = result.scalar_one_or_none()
    assert event is not None
    assert event.context["allowed"] is False


@pytest.mark.asyncio
async def test_no_db_no_event():
    """Without DB, no interaction event is logged (graceful)."""
    from src.protocol.a2a_middleware import verify_interaction

    verdict = await verify_interaction(
        str(uuid.uuid4()), str(uuid.uuid4()), "discover", db=None,
    )
    # Just verify it doesn't crash — no DB means no event
    assert verdict.allowed is True
