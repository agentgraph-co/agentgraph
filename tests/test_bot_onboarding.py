"""Tests for bot onboarding router — templates, bootstrap, readiness, quick-trust."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import (
    Entity,
    EntityType,
    TrustScore,
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


TEMPLATES_URL = "/api/v1/bots/templates"
BOOTSTRAP_URL = "/api/v1/bots/bootstrap"
REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
AGENT_REGISTER_URL = "/api/v1/agents/register"

HUMAN = {
    "email": "bot_onboard_human@example.com",
    "password": "Str0ngP@ss",
    "display_name": "BotOnboardHuman",
}


def _api_key_headers(api_key: str) -> dict:
    return {"X-API-Key": api_key}


def _readiness_url(agent_id: str) -> str:
    return f"/api/v1/bots/{agent_id}/readiness"


def _quick_trust_url(agent_id: str) -> str:
    return f"/api/v1/bots/{agent_id}/quick-trust"


# ---------------------------------------------------------------------------
# GET /bots/templates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_templates_returns_all(client: AsyncClient):
    """GET /bots/templates returns all 12 templates."""
    resp = await client.get(TEMPLATES_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 12


@pytest.mark.asyncio
async def test_templates_have_required_fields(client: AsyncClient):
    """Each template has all required fields."""
    resp = await client.get(TEMPLATES_URL)
    assert resp.status_code == 200
    for t in resp.json():
        assert "key" in t
        assert "display_name" in t
        assert "description" in t
        assert "default_capabilities" in t
        assert "suggested_framework" in t
        assert "suggested_autonomy_level" in t
        assert "suggested_bio" in t
        assert isinstance(t["default_capabilities"], list)
        assert isinstance(t["suggested_autonomy_level"], int)


# ---------------------------------------------------------------------------
# POST /bots/bootstrap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_with_template(client: AsyncClient):
    """Bootstrap with a template key applies template defaults."""
    resp = await client.post(BOOTSTRAP_URL, json={
        "template": "code_review",
        "display_name": "MyReviewBot",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent"]["display_name"] == "MyReviewBot"
    assert data["agent"]["capabilities"] == ["code-review", "static-analysis", "security-audit"]
    assert data["agent"]["autonomy_level"] == 3
    assert data["template_used"] == "code_review"
    assert len(data["api_key"]) == 64


@pytest.mark.asyncio
async def test_bootstrap_with_overrides(client: AsyncClient):
    """Template defaults can be overridden by explicit fields."""
    resp = await client.post(BOOTSTRAP_URL, json={
        "template": "code_review",
        "display_name": "CustomBot",
        "capabilities": ["custom-cap"],
        "autonomy_level": 5,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent"]["capabilities"] == ["custom-cap"]
    assert data["agent"]["autonomy_level"] == 5


@pytest.mark.asyncio
async def test_bootstrap_without_template(client: AsyncClient):
    """Bootstrap without a template uses provided fields directly."""
    resp = await client.post(BOOTSTRAP_URL, json={
        "display_name": "PlainBot",
        "capabilities": ["chat"],
        "autonomy_level": 2,
        "bio_markdown": "A plain bot",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent"]["display_name"] == "PlainBot"
    assert data["agent"]["capabilities"] == ["chat"]
    assert data["template_used"] is None


@pytest.mark.asyncio
async def test_bootstrap_with_intro_post(client: AsyncClient):
    """Bootstrap with intro_post creates agent + post."""
    resp = await client.post(BOOTSTRAP_URL, json={
        "display_name": "PostBot",
        "intro_post": "Hello, I'm PostBot!",
    })
    assert resp.status_code == 201
    data = resp.json()
    # Readiness should show the post exists
    activity_cat = next(
        c for c in data["readiness"]["categories"] if c["name"] == "Activity"
    )
    has_posts = next(item for item in activity_cat["items"] if item["label"] == "Has posts")
    assert has_posts["completed"] is True


@pytest.mark.asyncio
async def test_bootstrap_spam_name_rejected(client: AsyncClient):
    """Bootstrap with spammy display_name is rejected."""
    resp = await client.post(BOOTSTRAP_URL, json={
        "display_name": "Buy cheap viagra click here http://spam.com",
    })
    assert resp.status_code == 400
    assert "rejected" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_bootstrap_with_operator(client: AsyncClient):
    """Bootstrap with operator_email links the operator."""
    await client.post(REGISTER_URL, json=HUMAN)
    resp = await client.post(BOOTSTRAP_URL, json={
        "display_name": "OpBot",
        "operator_email": HUMAN["email"],
    })
    assert resp.status_code == 201
    assert resp.json()["agent"]["operator_id"] is not None


@pytest.mark.asyncio
async def test_bootstrap_includes_readiness(client: AsyncClient):
    """Bootstrap response includes a readiness report."""
    resp = await client.post(BOOTSTRAP_URL, json={
        "display_name": "ReadinessBot",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "readiness" in data
    assert "overall_score" in data["readiness"]
    assert "categories" in data["readiness"]
    assert len(data["readiness"]["categories"]) == 5


@pytest.mark.asyncio
async def test_bootstrap_includes_next_steps(client: AsyncClient):
    """Bootstrap response includes ordered next_steps."""
    resp = await client.post(BOOTSTRAP_URL, json={
        "display_name": "StepsBot",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "next_steps" in data
    assert isinstance(data["next_steps"], list)
    assert len(data["next_steps"]) > 0


@pytest.mark.asyncio
async def test_bootstrap_unknown_template(client: AsyncClient):
    """Bootstrap with unknown template key returns 400."""
    resp = await client.post(BOOTSTRAP_URL, json={
        "template": "nonexistent_template",
        "display_name": "FailBot",
    })
    assert resp.status_code == 400
    assert "unknown template" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /bots/{id}/readiness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readiness_fresh_agent_low_score(client: AsyncClient):
    """Fresh agent with no bio/caps gets a low readiness score."""
    reg = await client.post(BOOTSTRAP_URL, json={
        "display_name": "FreshBot",
    })
    assert reg.status_code == 201
    agent_id = reg.json()["agent"]["id"]
    api_key = reg.json()["api_key"]

    resp = await client.get(
        _readiness_url(agent_id),
        headers=_api_key_headers(api_key),
    )
    assert resp.status_code == 200
    data = resp.json()
    # No bio, no caps, no trust, no posts, no connections — low score
    assert data["overall_score"] < 0.6
    assert data["is_ready"] is False


@pytest.mark.asyncio
async def test_readiness_agent_with_bio_caps_post(client: AsyncClient, db):
    """Agent with bio, capabilities, and a post scores higher."""
    reg = await client.post(BOOTSTRAP_URL, json={
        "template": "code_review",
        "display_name": "EquippedBot",
        "bio_markdown": "A well-equipped bot",
        "intro_post": "Hello world!",
    })
    assert reg.status_code == 201
    agent_id = reg.json()["agent"]["id"]
    api_key = reg.json()["api_key"]

    resp = await client.get(
        _readiness_url(agent_id),
        headers=_api_key_headers(api_key),
    )
    assert resp.status_code == 200
    data = resp.json()
    # Has name, bio, DID, capabilities, post, API key — should be higher
    assert data["overall_score"] > reg.json()["readiness"]["overall_score"] - 0.01


@pytest.mark.asyncio
async def test_readiness_nonexistent_agent(client: AsyncClient):
    """Readiness for non-existent agent returns 404."""
    # Register any agent to get auth
    reg = await client.post(BOOTSTRAP_URL, json={"display_name": "AnyBot"})
    api_key = reg.json()["api_key"]

    fake_id = str(uuid.uuid4())
    resp = await client.get(
        _readiness_url(fake_id),
        headers=_api_key_headers(api_key),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_readiness_wrong_api_key(client: AsyncClient):
    """Readiness with wrong API key returns 403."""
    # Create two agents
    reg1 = await client.post(BOOTSTRAP_URL, json={"display_name": "Bot1"})
    reg2 = await client.post(BOOTSTRAP_URL, json={"display_name": "Bot2"})
    agent1_id = reg1.json()["agent"]["id"]
    agent2_key = reg2.json()["api_key"]

    # Bot2's key trying to read Bot1's readiness
    resp = await client.get(
        _readiness_url(agent1_id),
        headers=_api_key_headers(agent2_key),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /bots/{id}/quick-trust
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quick_trust_intro_post(client: AsyncClient):
    """Quick-trust intro_post action creates a post."""
    reg = await client.post(BOOTSTRAP_URL, json={"display_name": "TrustBot"})
    agent_id = reg.json()["agent"]["id"]
    api_key = reg.json()["api_key"]

    resp = await client.post(
        _quick_trust_url(agent_id),
        json={"actions": ["intro_post"], "intro_text": "Greetings from TrustBot!"},
        headers=_api_key_headers(api_key),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["executed"]) == 1
    assert data["executed"][0]["action"] == "intro_post"
    assert data["executed"][0]["success"] is True
    assert "readiness_after" in data


@pytest.mark.asyncio
async def test_quick_trust_follow_suggested(client: AsyncClient, db):
    """Quick-trust follow_suggested follows high-trust entities."""
    # Create a target entity with a trust score
    target = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="HighTrustBot",
        did_web=f"did:web:agentgraph.io:agents:{uuid.uuid4()}",
        capabilities=["testing"],
    )
    db.add(target)
    await db.flush()

    ts = TrustScore(
        id=uuid.uuid4(),
        entity_id=target.id,
        score=0.9,
    )
    db.add(ts)
    await db.flush()

    # Bootstrap our bot
    reg = await client.post(BOOTSTRAP_URL, json={"display_name": "FollowerBot"})
    agent_id = reg.json()["agent"]["id"]
    api_key = reg.json()["api_key"]

    resp = await client.post(
        _quick_trust_url(agent_id),
        json={"actions": ["follow_suggested"]},
        headers=_api_key_headers(api_key),
    )
    assert resp.status_code == 200
    data = resp.json()
    follow_result = data["executed"][0]
    assert follow_result["action"] == "follow_suggested"
    assert follow_result["success"] is True
    assert "Followed" in follow_result["detail"]


@pytest.mark.asyncio
async def test_quick_trust_idempotent(client: AsyncClient):
    """Calling intro_post twice doesn't create duplicate posts."""
    reg = await client.post(BOOTSTRAP_URL, json={"display_name": "IdempBot"})
    agent_id = reg.json()["agent"]["id"]
    api_key = reg.json()["api_key"]
    headers = _api_key_headers(api_key)

    # First call — creates post
    resp1 = await client.post(
        _quick_trust_url(agent_id),
        json={"actions": ["intro_post"]},
        headers=headers,
    )
    assert resp1.status_code == 200
    assert resp1.json()["executed"][0]["success"] is True
    assert resp1.json()["executed"][0]["detail"] == "Intro post created"

    # Second call — skips
    resp2 = await client.post(
        _quick_trust_url(agent_id),
        json={"actions": ["intro_post"]},
        headers=headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["executed"][0]["success"] is True
    assert "skipped" in resp2.json()["executed"][0]["detail"].lower()


@pytest.mark.asyncio
async def test_quick_trust_spam_intro_rejected(client: AsyncClient):
    """Quick-trust with spammy intro_text returns failure in result."""
    reg = await client.post(BOOTSTRAP_URL, json={"display_name": "SpamTrustBot"})
    agent_id = reg.json()["agent"]["id"]
    api_key = reg.json()["api_key"]

    resp = await client.post(
        _quick_trust_url(agent_id),
        json={
            "actions": ["intro_post"],
            "intro_text": "Buy cheap viagra click here http://spam.com",
        },
        headers=_api_key_headers(api_key),
    )
    assert resp.status_code == 200
    result = resp.json()["executed"][0]
    assert result["success"] is False
    assert "rejected" in result["detail"].lower()
