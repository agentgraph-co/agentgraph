"""Tests for A2A trust middleware."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, TrustScore


@pytest_asyncio.fixture
async def agent_high_trust(db: AsyncSession) -> Entity:
    eid = uuid.uuid4()
    agent = Entity(
        id=eid,
        email=f"a2a_high_{uuid.uuid4().hex[:6]}@test.com",
        display_name="HighTrustAgent",
        type="agent",
        is_active=True,
        did_web=f"did:web:agentgraph.co:agents:{eid}",
        framework_source="pydantic_ai",
        framework_trust_modifier=0.90,
    )
    db.add(agent)
    ts = TrustScore(id=uuid.uuid4(), entity_id=eid, score=0.85)
    db.add(ts)
    await db.flush()
    return agent


@pytest_asyncio.fixture
async def agent_low_trust(db: AsyncSession) -> Entity:
    eid = uuid.uuid4()
    agent = Entity(
        id=eid,
        email=f"a2a_low_{uuid.uuid4().hex[:6]}@test.com",
        display_name="LowTrustAgent",
        type="agent",
        is_active=True,
        did_web=f"did:web:agentgraph.co:agents:{eid}",
        framework_source="openclaw",
        framework_trust_modifier=0.65,
    )
    db.add(agent)
    ts = TrustScore(id=uuid.uuid4(), entity_id=eid, score=0.30)
    db.add(ts)
    await db.flush()
    return agent


@pytest.mark.asyncio
async def test_high_trust_delegation_allowed(
    db: AsyncSession, agent_high_trust: Entity, agent_low_trust: Entity,
):
    from src.protocol.a2a_middleware import verify_interaction

    verdict = await verify_interaction(
        str(agent_high_trust.id),
        str(agent_low_trust.id),
        "delegate",
        db=db,
    )
    # 0.85 * 0.90 = 0.765 >= 0.6 threshold
    assert verdict.allowed is True
    assert verdict.context.passes_threshold is True
    assert verdict.context.initiator_trust_score == 0.85
    assert verdict.context.framework_modifier == 0.90


@pytest.mark.asyncio
async def test_low_trust_delegation_denied(
    db: AsyncSession, agent_high_trust: Entity, agent_low_trust: Entity,
):
    from src.protocol.a2a_middleware import verify_interaction

    verdict = await verify_interaction(
        str(agent_low_trust.id),
        str(agent_high_trust.id),
        "delegate",
        db=db,
    )
    # 0.30 * 0.65 = 0.195 < 0.6 threshold
    assert verdict.allowed is False
    assert "failed" in verdict.reason.lower()


@pytest.mark.asyncio
async def test_discovery_always_allowed(
    db: AsyncSession, agent_low_trust: Entity, agent_high_trust: Entity,
):
    from src.protocol.a2a_middleware import verify_interaction

    verdict = await verify_interaction(
        str(agent_low_trust.id),
        str(agent_high_trust.id),
        "discover",
        db=db,
    )
    # Discovery threshold is 0.0 — always passes
    assert verdict.allowed is True


@pytest.mark.asyncio
async def test_financial_needs_highest_trust(
    db: AsyncSession, agent_high_trust: Entity, agent_low_trust: Entity,
):
    from src.protocol.a2a_middleware import verify_interaction

    verdict = await verify_interaction(
        str(agent_high_trust.id),
        str(agent_low_trust.id),
        "financial",
        db=db,
    )
    # 0.85 * 0.90 = 0.765 < 0.8 threshold for financial
    assert verdict.allowed is False


@pytest.mark.asyncio
async def test_custom_threshold_override(
    db: AsyncSession, agent_low_trust: Entity, agent_high_trust: Entity,
):
    from src.protocol.a2a_middleware import verify_interaction

    verdict = await verify_interaction(
        str(agent_low_trust.id),
        str(agent_high_trust.id),
        "delegate",
        db=db,
        custom_threshold=0.1,
    )
    # 0.30 * 0.65 = 0.195 >= 0.1 custom threshold
    assert verdict.allowed is True


@pytest.mark.asyncio
async def test_inject_trust_metadata():
    from src.protocol.a2a_middleware import TrustContext, inject_trust_metadata

    context = TrustContext(
        initiator_entity_id="abc",
        target_entity_id="def",
        initiator_trust_score=0.85,
        target_trust_score=0.50,
        interaction_type="delegate",
        passes_threshold=True,
    )
    envelope = {"type": "delegate_request", "payload": {"task": "summarize"}}
    enriched = await inject_trust_metadata(envelope, context)

    assert "agentgraph_trust" in enriched
    trust_meta = enriched["agentgraph_trust"]
    assert trust_meta["initiator_trust_score"] == 0.85
    assert trust_meta["target_trust_score"] == 0.50
    assert trust_meta["passes_threshold"] is True
    assert trust_meta["correlation_id"] is not None


@pytest.mark.asyncio
async def test_no_db_denies_by_default():
    from src.protocol.a2a_middleware import verify_interaction

    verdict = await verify_interaction(
        str(uuid.uuid4()),
        str(uuid.uuid4()),
        "delegate",
        db=None,
    )
    assert verdict.allowed is False
    assert any("database" in w.lower() for w in verdict.warnings)


@pytest.mark.asyncio
async def test_no_db_allows_discovery():
    from src.protocol.a2a_middleware import verify_interaction

    verdict = await verify_interaction(
        str(uuid.uuid4()),
        str(uuid.uuid4()),
        "discover",
        db=None,
    )
    assert verdict.allowed is True
