"""Tests for medium-priority backend tasks #184, #185, #186, #187, #141, #212, #213, #214."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.main import app
from src.models import (
    AnalyticsEvent,
    Entity,
    EntityType,
    Listing,
)


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
AGENTS_URL = "/api/v1/agents"

OPERATOR = {
    "email": "op_medium@example.com",
    "password": "Str0ngP@ss1",
    "display_name": "MediumOperator",
}

OPERATOR2 = {
    "email": "op_medium2@example.com",
    "password": "Str0ngP@ss2",
    "display_name": "MediumOperator2",
}

AGENT_DATA = {
    "display_name": "MediumBot",
    "capabilities": ["code-review", "text-generation"],
    "autonomy_level": 3,
}


async def _get_token(client: AsyncClient, user: dict) -> str:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL,
        json={"email": user["email"], "password": user["password"]},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_agent(client: AsyncClient, token: str, data: dict | None = None) -> dict:
    resp = await client.post(
        AGENTS_URL, json=data or AGENT_DATA, headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()


# =====================================================================
# Task #184: Operator Approval Flow
# =====================================================================


class TestOperatorApproval:
    """Test Task #184: operator_approved field and approve-operator endpoint."""

    @pytest.mark.asyncio
    async def test_new_agent_has_operator_approved_false(self, client: AsyncClient):
        token = await _get_token(client, OPERATOR)
        result = await _create_agent(client, token)
        assert result["agent"]["operator_approved"] is False

    @pytest.mark.asyncio
    async def test_approve_operator_success(self, client: AsyncClient):
        token = await _get_token(client, OPERATOR)
        result = await _create_agent(client, token)
        agent_id = result["agent"]["id"]

        resp = await client.post(
            f"{AGENTS_URL}/{agent_id}/approve-operator",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert "approved" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_approve_operator_already_approved(self, client: AsyncClient):
        token = await _get_token(client, OPERATOR)
        result = await _create_agent(client, token)
        agent_id = result["agent"]["id"]

        # First approval
        resp = await client.post(
            f"{AGENTS_URL}/{agent_id}/approve-operator",
            headers=_auth(token),
        )
        assert resp.status_code == 200

        # Second approval should be 409
        resp = await client.post(
            f"{AGENTS_URL}/{agent_id}/approve-operator",
            headers=_auth(token),
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_approve_operator_wrong_operator(self, client: AsyncClient):
        token1 = await _get_token(client, OPERATOR)
        token2 = await _get_token(client, OPERATOR2)
        result = await _create_agent(client, token1)
        agent_id = result["agent"]["id"]

        # Operator2 tries to approve — should be 403
        resp = await client.post(
            f"{AGENTS_URL}/{agent_id}/approve-operator",
            headers=_auth(token2),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_approve_operator_not_found(self, client: AsyncClient):
        token = await _get_token(client, OPERATOR)
        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"{AGENTS_URL}/{fake_id}/approve-operator",
            headers=_auth(token),
        )
        assert resp.status_code == 404


# =====================================================================
# Task #185: Agent API Key Recovery via Operator
# =====================================================================


class TestApiKeyRecovery:
    """Test Task #185: API key recovery via approved operator."""

    @pytest.mark.asyncio
    async def test_recover_key_requires_approval(self, client: AsyncClient):
        token = await _get_token(client, OPERATOR)
        result = await _create_agent(client, token)
        agent_id = result["agent"]["id"]

        # Try recover without approval — should be 403
        resp = await client.post(
            f"{AGENTS_URL}/{agent_id}/recover-key",
            headers=_auth(token),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_recover_key_success(self, client: AsyncClient):
        token = await _get_token(client, OPERATOR)
        result = await _create_agent(client, token)
        agent_id = result["agent"]["id"]
        old_key = result["api_key"]

        # Approve first
        resp = await client.post(
            f"{AGENTS_URL}/{agent_id}/approve-operator",
            headers=_auth(token),
        )
        assert resp.status_code == 200

        # Now recover
        resp = await client.post(
            f"{AGENTS_URL}/{agent_id}/recover-key",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "api_key" in data
        assert len(data["api_key"]) == 64
        assert data["api_key"] != old_key

    @pytest.mark.asyncio
    async def test_recover_key_wrong_operator(self, client: AsyncClient):
        token1 = await _get_token(client, OPERATOR)
        token2 = await _get_token(client, OPERATOR2)
        result = await _create_agent(client, token1)
        agent_id = result["agent"]["id"]

        # Approve with the real operator
        await client.post(
            f"{AGENTS_URL}/{agent_id}/approve-operator",
            headers=_auth(token1),
        )

        # Wrong operator tries to recover — should be 403
        resp = await client.post(
            f"{AGENTS_URL}/{agent_id}/recover-key",
            headers=_auth(token2),
        )
        assert resp.status_code == 403


# =====================================================================
# Task #186: Badge Inheritance — Operator Verification Propagates to Agents
# =====================================================================


class TestBadgeInheritance:
    """Test Task #186: badge propagation from operator to agents."""

    @pytest.mark.asyncio
    async def test_propagate_operator_badges(self, client: AsyncClient, db: AsyncSession):
        from src.api.badges_router import propagate_operator_badges

        # Create operator + agent
        token = await _get_token(client, OPERATOR)
        result = await _create_agent(client, token)
        agent_id = result["agent"]["id"]

        # Get operator entity
        me_resp = await client.get("/api/v1/auth/me", headers=_auth(token))
        operator_id = uuid.UUID(me_resp.json()["id"])

        # Propagate identity_verified badge
        created = await propagate_operator_badges(
            db, operator_id, "identity_verified", issued_by=operator_id,
        )
        assert len(created) == 1
        assert str(created[0].entity_id) == agent_id
        assert created[0].badge_type == "operated_by_verified"

    @pytest.mark.asyncio
    async def test_propagate_skip_non_verification_badge(
        self, client: AsyncClient, db: AsyncSession,
    ):
        from src.api.badges_router import propagate_operator_badges

        token = await _get_token(client, OPERATOR)
        await _create_agent(client, token)

        me_resp = await client.get("/api/v1/auth/me", headers=_auth(token))
        operator_id = uuid.UUID(me_resp.json()["id"])

        # email_verified does NOT propagate
        created = await propagate_operator_badges(
            db, operator_id, "email_verified",
        )
        assert len(created) == 0

    @pytest.mark.asyncio
    async def test_propagate_no_duplicate_badges(self, client: AsyncClient, db: AsyncSession):
        from src.api.badges_router import propagate_operator_badges

        token = await _get_token(client, OPERATOR)
        await _create_agent(client, token)

        me_resp = await client.get("/api/v1/auth/me", headers=_auth(token))
        operator_id = uuid.UUID(me_resp.json()["id"])

        # First propagation
        created1 = await propagate_operator_badges(
            db, operator_id, "identity_verified", issued_by=operator_id,
        )
        assert len(created1) == 1

        # Second propagation — should skip (duplicate)
        created2 = await propagate_operator_badges(
            db, operator_id, "agentgraph_verified", issued_by=operator_id,
        )
        assert len(created2) == 0


# =====================================================================
# Task #187: Auto-List Agent Capabilities in Marketplace on Bridge Import
# =====================================================================


class TestAutoListCapabilities:
    """Test Task #187: auto-listing capabilities on bridge import."""

    @pytest.mark.asyncio
    async def test_auto_list_capabilities(self, db: AsyncSession):
        from src.bridges.registry_base import auto_list_capabilities

        # Create a test agent entity
        agent_id = uuid.uuid4()
        agent = Entity(
            id=agent_id,
            type=EntityType.AGENT,
            display_name="AutoListBot",
            did_web=f"did:web:agentgraph.co:test:{agent_id}",
            capabilities=["data-analysis", "nlp-processing", "summarization"],
            framework_source="langchain",
            is_active=True,
        )
        db.add(agent)
        await db.flush()

        listings = await auto_list_capabilities(db, agent)
        assert len(listings) == 3

        # Verify listings are in the DB
        result = await db.execute(
            select(Listing).where(Listing.entity_id == agent_id)
        )
        db_listings = result.scalars().all()
        assert len(db_listings) == 3

        titles = {listing.title for listing in db_listings}
        assert "data-analysis" in titles
        assert "nlp-processing" in titles

    @pytest.mark.asyncio
    async def test_auto_list_no_duplicates(self, db: AsyncSession):
        from src.bridges.registry_base import auto_list_capabilities

        agent_id = uuid.uuid4()
        agent = Entity(
            id=agent_id,
            type=EntityType.AGENT,
            display_name="NoDupBot",
            did_web=f"did:web:agentgraph.co:test:{agent_id}",
            capabilities=["data-analysis"],
            framework_source="crewai",
            is_active=True,
        )
        db.add(agent)
        await db.flush()

        # First call
        listings1 = await auto_list_capabilities(db, agent)
        assert len(listings1) == 1

        # Second call — no duplicates
        listings2 = await auto_list_capabilities(db, agent)
        assert len(listings2) == 0

    @pytest.mark.asyncio
    async def test_auto_list_no_capabilities(self, db: AsyncSession):
        from src.bridges.registry_base import auto_list_capabilities

        agent_id = uuid.uuid4()
        agent = Entity(
            id=agent_id,
            type=EntityType.AGENT,
            display_name="EmptyBot",
            did_web=f"did:web:agentgraph.co:test:{agent_id}",
            capabilities=[],
            framework_source="openclaw",
            is_active=True,
        )
        db.add(agent)
        await db.flush()

        listings = await auto_list_capabilities(db, agent)
        assert len(listings) == 0


# =====================================================================
# Task #141: Scheduled Trust Recomputation — Scheduler
# =====================================================================


class TestScheduler:
    """Test Task #141: scheduler start/stop logic."""

    def test_start_stop_scheduler(self):
        import asyncio

        from src.jobs.scheduler import start_scheduler, stop_scheduler

        # Create a temporary event loop for testing
        loop = asyncio.new_event_loop()

        async def _test():
            task = start_scheduler(interval=999999)  # long interval so it doesn't fire
            assert task is not None
            assert not task.done()

            # Start again — should return same task
            task2 = start_scheduler(interval=999999)
            assert task2 is task

            stop_scheduler()
            # Give it a moment to cancel
            await asyncio.sleep(0.01)
            assert task.cancelled() or task.done()

        loop.run_until_complete(_test())
        loop.close()

    def test_scheduler_module_imports(self):
        from src.jobs.scheduler import SCHEDULER_INTERVAL

        assert SCHEDULER_INTERVAL == 6 * 60 * 60


# =====================================================================
# Task #212: Instrument Trust Scores at Interaction Time
# =====================================================================


class TestTrustScoreInstrumentation:
    """Test Task #212: analytics events for trust score queries."""

    @pytest.mark.asyncio
    async def test_trust_query_creates_analytics_event(self, client: AsyncClient, db: AsyncSession):
        token = await _get_token(client, OPERATOR)
        me_resp = await client.get("/api/v1/auth/me", headers=_auth(token))
        entity_id = me_resp.json()["id"]

        # Query trust score
        resp = await client.get(
            f"/api/v1/entities/{entity_id}/trust",
            headers=_auth(token),
        )
        assert resp.status_code == 200

        # Check analytics event was created
        result = await db.execute(
            select(AnalyticsEvent).where(
                AnalyticsEvent.event_type == "trust_score_query",
                AnalyticsEvent.session_id == entity_id,
            )
        )
        events = result.scalars().all()
        assert len(events) >= 1
        event = events[-1]
        assert event.extra_metadata["target_entity_id"] == entity_id
        assert event.extra_metadata["purpose"] == "query"

    @pytest.mark.asyncio
    async def test_trust_refresh_creates_analytics_event(
        self, client: AsyncClient, db: AsyncSession,
    ):
        token = await _get_token(client, OPERATOR)
        me_resp = await client.get("/api/v1/auth/me", headers=_auth(token))
        entity_id = me_resp.json()["id"]

        # Refresh trust score
        resp = await client.post(
            f"/api/v1/entities/{entity_id}/trust/refresh",
            headers=_auth(token),
        )
        assert resp.status_code == 200

        # Check analytics event was created
        result = await db.execute(
            select(AnalyticsEvent).where(
                AnalyticsEvent.event_type == "trust_score_compute",
                AnalyticsEvent.session_id == entity_id,
            )
        )
        events = result.scalars().all()
        assert len(events) >= 1
        event = events[-1]
        assert event.extra_metadata["purpose"] == "refresh"


# =====================================================================
# Task #213: Framework-Pair Tracking
# =====================================================================


class TestFrameworkPairTracking:
    """Test Task #213: framework pair enrichment in interactions."""

    @pytest.mark.asyncio
    async def test_enrich_framework_pair(self, db: AsyncSession):
        from src.interactions import _enrich_framework_pair

        # Create two agents with different frameworks
        a_id = uuid.uuid4()
        b_id = uuid.uuid4()
        agent_a = Entity(
            id=a_id, type=EntityType.AGENT,
            display_name="AgentA",
            did_web=f"did:web:agentgraph.co:test:{a_id}",
            framework_source="openclaw", is_active=True,
        )
        agent_b = Entity(
            id=b_id, type=EntityType.AGENT,
            display_name="AgentB",
            did_web=f"did:web:agentgraph.co:test:{b_id}",
            framework_source="langchain", is_active=True,
        )
        db.add(agent_a)
        db.add(agent_b)
        await db.flush()

        enriched = await _enrich_framework_pair(db, a_id, b_id, {"foo": "bar"})
        assert enriched["initiator_framework"] == "openclaw"
        assert enriched["target_framework"] == "langchain"
        assert enriched["is_cross_framework"] is True
        assert enriched["foo"] == "bar"

    @pytest.mark.asyncio
    async def test_enrich_same_framework(self, db: AsyncSession):
        from src.interactions import _enrich_framework_pair

        a_id = uuid.uuid4()
        b_id = uuid.uuid4()
        agent_a = Entity(
            id=a_id, type=EntityType.AGENT,
            display_name="SameA",
            did_web=f"did:web:agentgraph.co:test:{a_id}",
            framework_source="crewai", is_active=True,
        )
        agent_b = Entity(
            id=b_id, type=EntityType.AGENT,
            display_name="SameB",
            did_web=f"did:web:agentgraph.co:test:{b_id}",
            framework_source="crewai", is_active=True,
        )
        db.add(agent_a)
        db.add(agent_b)
        await db.flush()

        enriched = await _enrich_framework_pair(db, a_id, b_id, None)
        assert enriched["is_cross_framework"] is False

    @pytest.mark.asyncio
    async def test_record_interaction_enriches_context(self, db: AsyncSession):
        from src.interactions import record_interaction

        a_id = uuid.uuid4()
        b_id = uuid.uuid4()
        agent_a = Entity(
            id=a_id, type=EntityType.AGENT,
            display_name="InterA",
            did_web=f"did:web:agentgraph.co:test:{a_id}",
            framework_source="autogen", is_active=True,
        )
        agent_b = Entity(
            id=b_id, type=EntityType.AGENT,
            display_name="InterB",
            did_web=f"did:web:agentgraph.co:test:{b_id}",
            framework_source="langchain", is_active=True,
        )
        db.add(agent_a)
        db.add(agent_b)
        await db.flush()

        event = await record_interaction(
            db, a_id, b_id, "follow",
            context={"reason": "test"},
        )
        assert event.context["initiator_framework"] == "autogen"
        assert event.context["target_framework"] == "langchain"
        assert event.context["is_cross_framework"] is True
        assert event.context["reason"] == "test"


# =====================================================================
# Task #214: Social Feature Usage Tracking
# =====================================================================


class TestSocialFeatureTracking:
    """Test Task #214: analytics events for social features."""

    @pytest.mark.asyncio
    async def test_follow_creates_analytics_event(self, client: AsyncClient, db: AsyncSession):
        token1 = await _get_token(client, OPERATOR)
        token2 = await _get_token(client, OPERATOR2)

        me_resp2 = await client.get("/api/v1/auth/me", headers=_auth(token2))
        target_id = me_resp2.json()["id"]

        resp = await client.post(
            f"/api/v1/social/follow/{target_id}",
            headers=_auth(token1),
        )
        assert resp.status_code == 200

        result = await db.execute(
            select(AnalyticsEvent).where(
                AnalyticsEvent.event_type == "social_follow",
            )
        )
        events = result.scalars().all()
        assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_post_creates_analytics_event(self, client: AsyncClient, db: AsyncSession):
        token = await _get_token(client, OPERATOR)

        resp = await client.post(
            "/api/v1/feed/posts",
            json={"content": "Test post for analytics tracking"},
            headers=_auth(token),
        )
        assert resp.status_code == 201

        result = await db.execute(
            select(AnalyticsEvent).where(
                AnalyticsEvent.event_type == "social_post",
            )
        )
        events = result.scalars().all()
        assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_vote_creates_analytics_event(self, client: AsyncClient, db: AsyncSession):
        token = await _get_token(client, OPERATOR)

        # Create a post first
        post_resp = await client.post(
            "/api/v1/feed/posts",
            json={"content": "Post for vote test"},
            headers=_auth(token),
        )
        assert post_resp.status_code == 201
        post_id = post_resp.json()["id"]

        # Vote on it
        resp = await client.post(
            f"/api/v1/feed/posts/{post_id}/vote",
            json={"direction": "up"},
            headers=_auth(token),
        )
        assert resp.status_code == 200

        result = await db.execute(
            select(AnalyticsEvent).where(
                AnalyticsEvent.event_type == "social_vote",
            )
        )
        events = result.scalars().all()
        assert len(events) >= 1


# =====================================================================
# Config / model-level tests
# =====================================================================


class TestConfigExtensions:
    """Test that config has the new scheduler fields."""

    def test_config_has_scheduler_fields(self):
        from src.config import Settings

        s = Settings(
            enable_scheduler=True,
            trust_recompute_interval_seconds=3600,
        )
        assert s.enable_scheduler is True
        assert s.trust_recompute_interval_seconds == 3600

    def test_config_defaults(self):
        from src.config import settings

        assert settings.enable_scheduler is False
        assert settings.trust_recompute_interval_seconds == 6 * 60 * 60


class TestOperatorApprovedField:
    """Test the operator_approved field on the Entity model."""

    @pytest.mark.asyncio
    async def test_entity_has_operator_approved_field(self, db: AsyncSession):
        entity_id = uuid.uuid4()
        entity = Entity(
            id=entity_id,
            type=EntityType.AGENT,
            display_name="FieldTest",
            did_web=f"did:web:agentgraph.co:test:{entity_id}",
            is_active=True,
        )
        db.add(entity)
        await db.flush()
        await db.refresh(entity)
        assert entity.operator_approved is False

    @pytest.mark.asyncio
    async def test_operator_approved_can_be_set(self, db: AsyncSession):
        entity_id = uuid.uuid4()
        entity = Entity(
            id=entity_id,
            type=EntityType.AGENT,
            display_name="SetTest",
            did_web=f"did:web:agentgraph.co:test:{entity_id}",
            operator_approved=True,
            is_active=True,
        )
        db.add(entity)
        await db.flush()
        await db.refresh(entity)
        assert entity.operator_approved is True
