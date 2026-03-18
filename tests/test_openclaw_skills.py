"""Tests for expanded OpenClaw skill handlers."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.bridges.openclaw.adapter import (
    OpenClawError,
    get_supported_skills,
    translate_skill_call,
)
from src.database import get_db
from src.main import app
from src.models import (
    Entity,
    EntityType,
    Listing,
    Notification,
    Post,
    TrustScore,
)


@pytest_asyncio.fixture
async def agent_entity(db: AsyncSession) -> Entity:
    """Create a test agent entity."""
    agent = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="TestOpenClawBot",
        did_web=f"did:web:agentgraph.co:test:{uuid.uuid4().hex[:8]}",
        is_active=True,
        framework_source="openclaw",
    )
    db.add(agent)
    ts = TrustScore(id=uuid.uuid4(), entity_id=agent.id, score=0.8, components={})
    db.add(ts)
    await db.flush()
    return agent


@pytest_asyncio.fixture
async def target_entity(db: AsyncSession) -> Entity:
    """Create a target entity for interactions."""
    target = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="TargetBot",
        did_web=f"did:web:agentgraph.co:test:{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db.add(target)
    ts = TrustScore(id=uuid.uuid4(), entity_id=target.id, score=0.7, components={})
    db.add(ts)
    await db.flush()
    return target


@pytest_asyncio.fixture
async def sample_post(db: AsyncSession, agent_entity: Entity) -> Post:
    """Create a sample post for reply/vote tests."""
    post = Post(
        id=uuid.uuid4(),
        author_entity_id=agent_entity.id,
        content="Hello from OpenClaw test",
    )
    db.add(post)
    await db.flush()
    return post


@pytest_asyncio.fixture
async def client(db: AsyncSession):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Supported skills
# ---------------------------------------------------------------------------


def test_supported_skills_count():
    """All 12 skills are registered."""
    skills = get_supported_skills()
    assert len(skills) == 12
    assert "reply_to_post" in skills
    assert "vote" in skills
    assert "send_message" in skills
    assert "get_notifications" in skills
    assert "browse_marketplace" in skills
    assert "endorse_capability" in skills
    assert "delegate_task" in skills


# ---------------------------------------------------------------------------
# reply_to_post
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reply_to_post(db: AsyncSession, agent_entity: Entity, sample_post: Post):
    result = await translate_skill_call(
        "reply_to_post",
        {"parent_post_id": str(sample_post.id), "content": "A reply!"},
        agent_entity,
        db,
    )
    assert result["parent_post_id"] == str(sample_post.id)
    assert result["content"] == "A reply!"
    assert result["author_id"] == str(agent_entity.id)


@pytest.mark.asyncio
async def test_reply_to_post_missing_parent(db: AsyncSession, agent_entity: Entity):
    with pytest.raises(OpenClawError) as exc_info:
        await translate_skill_call(
            "reply_to_post", {"content": "No parent"}, agent_entity, db,
        )
    assert exc_info.value.code == "missing_parent_post_id"


@pytest.mark.asyncio
async def test_reply_to_post_not_found(db: AsyncSession, agent_entity: Entity):
    with pytest.raises(OpenClawError) as exc_info:
        await translate_skill_call(
            "reply_to_post",
            {"parent_post_id": str(uuid.uuid4()), "content": "Lost parent"},
            agent_entity,
            db,
        )
    assert exc_info.value.code == "parent_not_found"


# ---------------------------------------------------------------------------
# vote
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vote(db: AsyncSession, agent_entity: Entity, sample_post: Post):
    result = await translate_skill_call(
        "vote", {"post_id": str(sample_post.id), "value": 1}, agent_entity, db,
    )
    assert result["status"] == "voted"

    # Vote again with same value → already_voted
    result2 = await translate_skill_call(
        "vote", {"post_id": str(sample_post.id), "value": 1}, agent_entity, db,
    )
    assert result2["status"] == "already_voted"

    # Change vote direction
    result3 = await translate_skill_call(
        "vote", {"post_id": str(sample_post.id), "value": -1}, agent_entity, db,
    )
    assert result3["status"] == "vote_changed"


@pytest.mark.asyncio
async def test_vote_post_not_found(db: AsyncSession, agent_entity: Entity):
    with pytest.raises(OpenClawError) as exc_info:
        await translate_skill_call(
            "vote", {"post_id": str(uuid.uuid4()), "value": 1}, agent_entity, db,
        )
    assert exc_info.value.code == "post_not_found"


@pytest.mark.asyncio
async def test_vote_invalid_value(db: AsyncSession, agent_entity: Entity, sample_post: Post):
    with pytest.raises(OpenClawError) as exc_info:
        await translate_skill_call(
            "vote", {"post_id": str(sample_post.id), "value": 0}, agent_entity, db,
        )
    assert exc_info.value.code == "invalid_value"


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message(
    db: AsyncSession, agent_entity: Entity, target_entity: Entity,
):
    result = await translate_skill_call(
        "send_message",
        {"recipient_id": str(target_entity.id), "content": "Hello target!"},
        agent_entity,
        db,
    )
    assert result["status"] == "sent"
    assert result["sender_id"] == str(agent_entity.id)
    assert result["recipient_id"] == str(target_entity.id)


@pytest.mark.asyncio
async def test_send_message_self_blocked(db: AsyncSession, agent_entity: Entity):
    with pytest.raises(OpenClawError) as exc_info:
        await translate_skill_call(
            "send_message",
            {"recipient_id": str(agent_entity.id), "content": "Talking to myself"},
            agent_entity,
            db,
        )
    assert exc_info.value.code == "self_message"


# ---------------------------------------------------------------------------
# get_notifications
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_notifications(db: AsyncSession, agent_entity: Entity):
    # Create a notification
    notif = Notification(
        id=uuid.uuid4(),
        entity_id=agent_entity.id,
        kind="test",
        title="Test Notification",
        body="Something happened",
    )
    db.add(notif)
    await db.flush()

    result = await translate_skill_call(
        "get_notifications", {}, agent_entity, db,
    )
    assert result["count"] >= 1
    found = [n for n in result["notifications"] if n["id"] == str(notif.id)]
    assert len(found) == 1
    assert found[0]["kind"] == "test"
    assert found[0]["title"] == "Test Notification"


@pytest.mark.asyncio
async def test_get_notifications_unread_only(db: AsyncSession, agent_entity: Entity):
    read_notif = Notification(
        id=uuid.uuid4(),
        entity_id=agent_entity.id,
        kind="test",
        title="Read",
        body="Already read",
        is_read=True,
    )
    unread_notif = Notification(
        id=uuid.uuid4(),
        entity_id=agent_entity.id,
        kind="test",
        title="Unread",
        body="Not yet read",
        is_read=False,
    )
    db.add(read_notif)
    db.add(unread_notif)
    await db.flush()

    result = await translate_skill_call(
        "get_notifications", {"unread_only": True}, agent_entity, db,
    )
    ids = [n["id"] for n in result["notifications"]]
    assert str(unread_notif.id) in ids
    assert str(read_notif.id) not in ids


# ---------------------------------------------------------------------------
# browse_marketplace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browse_marketplace(db: AsyncSession, agent_entity: Entity):
    listing = Listing(
        id=uuid.uuid4(),
        entity_id=agent_entity.id,
        title="Cool Skill",
        description="Does cool things",
        category="skill",
        pricing_model="free",
        price_cents=0,
        is_active=True,
    )
    db.add(listing)
    await db.flush()

    result = await translate_skill_call(
        "browse_marketplace", {}, agent_entity, db,
    )
    assert result["count"] >= 1
    found = [li for li in result["listings"] if li["id"] == str(listing.id)]
    assert len(found) == 1
    assert found[0]["title"] == "Cool Skill"


@pytest.mark.asyncio
async def test_browse_marketplace_category_filter(
    db: AsyncSession, agent_entity: Entity,
):
    skill = Listing(
        id=uuid.uuid4(),
        entity_id=agent_entity.id,
        title="Skill Listing",
        description="A skill",
        category="skill",
        pricing_model="free",
        is_active=True,
    )
    service = Listing(
        id=uuid.uuid4(),
        entity_id=agent_entity.id,
        title="Service Listing",
        description="A service",
        category="service",
        pricing_model="free",
        is_active=True,
    )
    db.add(skill)
    db.add(service)
    await db.flush()

    result = await translate_skill_call(
        "browse_marketplace", {"category": "skill"}, agent_entity, db,
    )
    categories = {li["category"] for li in result["listings"]}
    assert "service" not in categories


# ---------------------------------------------------------------------------
# endorse_capability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endorse_capability(
    db: AsyncSession, agent_entity: Entity, target_entity: Entity,
):
    result = await translate_skill_call(
        "endorse_capability",
        {"target_id": str(target_entity.id), "capability": "code_review"},
        agent_entity,
        db,
    )
    assert result["status"] == "endorsed"

    # Endorse again → already_endorsed
    result2 = await translate_skill_call(
        "endorse_capability",
        {"target_id": str(target_entity.id), "capability": "code_review"},
        agent_entity,
        db,
    )
    assert result2["status"] == "already_endorsed"


@pytest.mark.asyncio
async def test_endorse_self_blocked(db: AsyncSession, agent_entity: Entity):
    with pytest.raises(OpenClawError) as exc_info:
        await translate_skill_call(
            "endorse_capability",
            {"target_id": str(agent_entity.id), "capability": "test"},
            agent_entity,
            db,
        )
    assert exc_info.value.code == "self_endorse"


# ---------------------------------------------------------------------------
# delegate_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delegate_task(
    db: AsyncSession, agent_entity: Entity, target_entity: Entity,
):
    result = await translate_skill_call(
        "delegate_task",
        {"delegate_id": str(target_entity.id), "description": "Run tests"},
        agent_entity,
        db,
    )
    assert result["status"] == "pending"
    assert result["delegator_id"] == str(agent_entity.id)
    assert result["delegate_id"] == str(target_entity.id)


@pytest.mark.asyncio
async def test_delegate_self_blocked(db: AsyncSession, agent_entity: Entity):
    with pytest.raises(OpenClawError) as exc_info:
        await translate_skill_call(
            "delegate_task",
            {"delegate_id": str(agent_entity.id), "description": "Self task"},
            agent_entity,
            db,
        )
    assert exc_info.value.code == "self_delegate"


# ---------------------------------------------------------------------------
# Unknown skill
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_skill_error(db: AsyncSession, agent_entity: Entity):
    with pytest.raises(OpenClawError) as exc_info:
        await translate_skill_call("nonexistent_skill", {}, agent_entity, db)
    assert exc_info.value.code == "skill_not_found"


# ---------------------------------------------------------------------------
# HTTP endpoint: GET /bridges/openclaw/skills
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_skills_endpoint(client: AsyncClient):
    resp = await client.get("/api/v1/bridges/openclaw/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 12
    assert "reply_to_post" in data["skills"]
    assert "delegate_task" in data["skills"]
