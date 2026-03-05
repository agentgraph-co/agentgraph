"""Tests for framework trust modifiers in agent registration."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


AGENT_REGISTER_URL = "/api/v1/agents/register"


@pytest.mark.asyncio
async def test_register_with_framework_source(client: AsyncClient, db):
    """Registering with framework_source sets the modifier."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={
            "display_name": "PydanticBot",
            "capabilities": ["chat"],
            "framework_source": "pydantic_ai",
        },
    )
    assert resp.status_code == 201
    agent_id = resp.json()["agent"]["id"]

    # Verify framework_source is set in DB
    from src.models import Entity

    agent = await db.get(Entity, __import__("uuid").UUID(agent_id))
    assert agent.framework_source == "pydantic_ai"
    assert agent.framework_trust_modifier == 0.90


@pytest.mark.asyncio
async def test_register_openclaw_gets_lower_modifier(client: AsyncClient, db):
    """OpenClaw agents get a lower trust modifier due to security concerns."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={
            "display_name": "OpenClawBot",
            "capabilities": ["skills"],
            "framework_source": "openclaw",
        },
    )
    assert resp.status_code == 201
    agent_id = resp.json()["agent"]["id"]

    from src.models import Entity

    agent = await db.get(Entity, __import__("uuid").UUID(agent_id))
    assert agent.framework_source == "openclaw"
    assert agent.framework_trust_modifier == 0.65


@pytest.mark.asyncio
async def test_register_without_framework_no_modifier(client: AsyncClient, db):
    """Agent without framework_source gets no modifier."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={"display_name": "NativeBot", "capabilities": ["chat"]},
    )
    assert resp.status_code == 201
    agent_id = resp.json()["agent"]["id"]

    from src.models import Entity

    agent = await db.get(Entity, __import__("uuid").UUID(agent_id))
    assert agent.framework_source is None
    # No framework specified — modifier defaults to 1.0 (neutral)
    assert agent.framework_trust_modifier == 1.0


@pytest.mark.asyncio
async def test_unknown_framework_gets_default_modifier(client: AsyncClient, db):
    """Unknown framework gets default modifier of 1.0."""
    resp = await client.post(
        AGENT_REGISTER_URL,
        json={
            "display_name": "UnknownBot",
            "capabilities": ["chat"],
            "framework_source": "totally_unknown",
        },
    )
    assert resp.status_code == 201
    agent_id = resp.json()["agent"]["id"]

    from src.models import Entity

    agent = await db.get(Entity, __import__("uuid").UUID(agent_id))
    assert agent.framework_source == "totally_unknown"
    assert agent.framework_trust_modifier == 1.0


@pytest.mark.asyncio
async def test_config_has_all_tier1_frameworks():
    """Config includes all Tier 1 framework modifiers."""
    from src.config import settings

    assert "pydantic_ai" in settings.framework_trust_modifiers
    assert "crewai" in settings.framework_trust_modifiers
    assert "langchain" in settings.framework_trust_modifiers
    assert "openclaw" in settings.framework_trust_modifiers
    assert "autogen" in settings.framework_trust_modifiers

    # Verify ordering: higher-quality frameworks have higher modifiers
    mods = settings.framework_trust_modifiers
    assert mods["pydantic_ai"] > mods["crewai"]
    assert mods["crewai"] > mods["openclaw"]
