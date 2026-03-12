"""Tests for the official bot engine."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bots.definitions import BOT_BY_KEY, BOT_DEFINITIONS, BOT_IDS, bot_uuid
from src.bots.engine import (
    _post_as_bot,
    ensure_bots_exist,
    handle_entity_registered,
    handle_post_created,
    register_event_handlers,
    run_scheduled_posts,
    seed_initial_posts,
)
from src.database import get_db
from src.main import app
from src.models import Entity, EntityType, Post, TrustScore


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------


def test_bot_definitions_complete():
    """All 6 bots are defined with required fields."""
    assert len(BOT_DEFINITIONS) == 6
    keys = {b["key"] for b in BOT_DEFINITIONS}
    assert keys == {
        "agentgraph", "bughunter", "featurebot",
        "trustguide", "securitywatch", "welcomebot",
    }
    for bot in BOT_DEFINITIONS:
        assert bot["id"]
        assert bot["display_name"]
        assert bot["bio"]
        assert bot["capabilities"]


def test_deterministic_uuids():
    """Bot UUIDs are stable across calls."""
    assert bot_uuid("agentgraph") == bot_uuid("agentgraph")
    assert bot_uuid("agentgraph") != bot_uuid("bughunter")


def test_bot_ids_set():
    """BOT_IDS set has all 6 bot IDs."""
    assert len(BOT_IDS) == 6


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_bots_exist(db: AsyncSession):
    """Bootstrap creates all 6 bots."""
    result = await ensure_bots_exist(db)
    assert len(result["created"]) == 6
    assert result["total"] == 6

    # Verify entities exist
    for bot_def in BOT_DEFINITIONS:
        entity = await db.get(Entity, bot_def["id"])
        assert entity is not None
        assert entity.display_name == bot_def["display_name"]
        assert entity.type == EntityType.AGENT
        assert entity.is_provisional is False
        assert entity.is_active is True
        assert entity.did_web.startswith("did:web:agentgraph.co:bots:")

    # Verify trust scores
    for bot_def in BOT_DEFINITIONS:
        ts = await db.execute(
            select(TrustScore).where(TrustScore.entity_id == bot_def["id"])
        )
        score = ts.scalar_one_or_none()
        assert score is not None
        assert score.score == 0.85


@pytest.mark.asyncio
async def test_ensure_bots_exist_idempotent(db: AsyncSession):
    """Running bootstrap twice doesn't duplicate bots."""
    result1 = await ensure_bots_exist(db)
    assert len(result1["created"]) == 6

    result2 = await ensure_bots_exist(db)
    assert len(result2["created"]) == 0


# ---------------------------------------------------------------------------
# Seed initial posts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_initial_posts(db: AsyncSession):
    """Seeding creates one post per bot with content pools."""
    await ensure_bots_exist(db)
    result = await seed_initial_posts(db)
    # All bots except welcomebot have content pools
    assert len(result["seeded"]) >= 5

    # Verify posts exist
    for bot_def in BOT_DEFINITIONS:
        count_result = await db.execute(
            select(func.count()).select_from(Post).where(
                Post.author_entity_id == bot_def["id"],
            )
        )
        count = count_result.scalar()
        from src.bots.definitions import SCHEDULED_CONTENT
        if SCHEDULED_CONTENT.get(bot_def["key"]):
            assert count >= 1, f"Bot {bot_def['key']} should have at least 1 post"


@pytest.mark.asyncio
async def test_seed_initial_posts_idempotent(db: AsyncSession):
    """Seeding twice doesn't duplicate posts."""
    await ensure_bots_exist(db)
    await seed_initial_posts(db)
    result2 = await seed_initial_posts(db)
    assert len(result2["seeded"]) == 0


# ---------------------------------------------------------------------------
# Scheduled posts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_scheduled_posts(db: AsyncSession):
    """Scheduled posts create new content for bots."""
    await ensure_bots_exist(db)

    result1 = await run_scheduled_posts(db)
    assert len(result1["posted"]) >= 5  # all bots with content pools

    # Run again — should post different content
    result2 = await run_scheduled_posts(db)
    assert len(result2["posted"]) >= 5


@pytest.mark.asyncio
async def test_scheduled_posts_skip_when_pool_exhausted(db: AsyncSession):
    """Once all content is posted, bots skip their cycle."""
    await ensure_bots_exist(db)

    # Post many times to exhaust smaller pools
    for _ in range(5):
        await run_scheduled_posts(db)

    # The bots with small pools (bughunter=3, featurebot=3) should now
    # be skipped since all content is in their recent posts
    result = await run_scheduled_posts(db)
    # At least one bot should have exhausted its pool
    assert len(result["posted"]) < 6


# ---------------------------------------------------------------------------
# Post as bot helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_as_bot(db: AsyncSession):
    """_post_as_bot creates a post with correct fields."""
    await ensure_bots_exist(db)
    ag_bot = BOT_BY_KEY["agentgraph"]

    post = await _post_as_bot(db, ag_bot["id"], "Test post content", flair="announcement")
    assert post is not None
    assert post.author_entity_id == ag_bot["id"]
    assert "Test post content" in post.content
    assert post.flair == "announcement"


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_welcome_bot_greets_new_user(db: AsyncSession):
    """WelcomeBot posts a welcome when a new entity registers."""
    await ensure_bots_exist(db)

    # Create a human entity for the welcome
    human = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email="newuser@test.com",
        display_name="NewUser",
        did_web=f"did:web:agentgraph.co:u:{uuid.uuid4().hex[:8]}",
    )
    db.add(human)
    await db.flush()

    # Simulate the entity.registered event
    await handle_entity_registered("entity.registered", {
        "entity_id": str(human.id),
        "display_name": "NewUser",
        "entity_type": "human",
    }, _test_db=db)

    # Check WelcomeBot posted
    welcome_bot = BOT_BY_KEY["welcomebot"]
    posts = await db.execute(
        select(Post).where(Post.author_entity_id == welcome_bot["id"])
    )
    welcome_posts = posts.scalars().all()
    assert len(welcome_posts) >= 1
    assert "NewUser" in welcome_posts[-1].content


@pytest.mark.asyncio
async def test_welcome_bot_ignores_own_bots(db: AsyncSession):
    """WelcomeBot doesn't greet other official bots."""
    await ensure_bots_exist(db)
    ag_bot = BOT_BY_KEY["agentgraph"]

    await handle_entity_registered("entity.registered", {
        "entity_id": str(ag_bot["id"]),
        "display_name": "AgentGraph",
        "entity_type": "agent",
    }, _test_db=db)

    welcome_bot = BOT_BY_KEY["welcomebot"]
    posts = await db.execute(
        select(Post).where(Post.author_entity_id == welcome_bot["id"])
    )
    assert len(posts.scalars().all()) == 0


@pytest.mark.asyncio
async def test_bughunter_reacts_to_bug_posts(db: AsyncSession):
    """BugHunter replies to posts mentioning bugs."""
    await ensure_bots_exist(db)

    # Create a human and their bug report post
    human = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email="bugreporter@test.com",
        display_name="BugReporter",
        did_web=f"did:web:agentgraph.co:u:{uuid.uuid4().hex[:8]}",
    )
    db.add(human)
    await db.flush()

    bug_post = Post(
        id=uuid.uuid4(),
        author_entity_id=human.id,
        content="I found a bug — the search page crashes when I type special characters",
    )
    db.add(bug_post)
    await db.flush()

    # Simulate the post.created event
    await handle_post_created("post.created", {
        "post_id": str(bug_post.id),
        "author_entity_id": str(human.id),
        "content": bug_post.content,
    }, _test_db=db)

    # Check BugHunter replied
    bughunter = BOT_BY_KEY["bughunter"]
    replies = await db.execute(
        select(Post).where(
            Post.author_entity_id == bughunter["id"],
            Post.parent_post_id == bug_post.id,
        )
    )
    reply_list = replies.scalars().all()
    assert len(reply_list) == 1
    assert "investigate" in reply_list[0].content.lower()


@pytest.mark.asyncio
async def test_featurebot_reacts_to_feature_requests(db: AsyncSession):
    """FeatureBot replies to posts with feature request keywords."""
    await ensure_bots_exist(db)

    human = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email="featurereq@test.com",
        display_name="FeatureRequester",
        did_web=f"did:web:agentgraph.co:u:{uuid.uuid4().hex[:8]}",
    )
    db.add(human)
    await db.flush()

    feature_post = Post(
        id=uuid.uuid4(),
        author_entity_id=human.id,
        content="Feature request: it would be great to have dark mode in the graph view",
    )
    db.add(feature_post)
    await db.flush()

    await handle_post_created("post.created", {
        "post_id": str(feature_post.id),
        "author_entity_id": str(human.id),
        "content": feature_post.content,
    }, _test_db=db)

    featurebot = BOT_BY_KEY["featurebot"]
    replies = await db.execute(
        select(Post).where(
            Post.author_entity_id == featurebot["id"],
            Post.parent_post_id == feature_post.id,
        )
    )
    reply_list = replies.scalars().all()
    assert len(reply_list) == 1
    assert "prioritize" in reply_list[0].content.lower()


@pytest.mark.asyncio
async def test_bots_dont_react_to_own_posts(db: AsyncSession):
    """Bots don't reply to posts from other official bots."""
    await ensure_bots_exist(db)
    ag_bot = BOT_BY_KEY["agentgraph"]

    bot_post = Post(
        id=uuid.uuid4(),
        author_entity_id=ag_bot["id"],
        content="This is a bug report from the platform itself",
    )
    db.add(bot_post)
    await db.flush()

    await handle_post_created("post.created", {
        "post_id": str(bot_post.id),
        "author_entity_id": str(ag_bot["id"]),
        "content": bot_post.content,
    }, _test_db=db)

    # BugHunter should not have replied
    bughunter = BOT_BY_KEY["bughunter"]
    replies = await db.execute(
        select(Post).where(
            Post.author_entity_id == bughunter["id"],
            Post.parent_post_id == bot_post.id,
        )
    )
    assert len(replies.scalars().all()) == 0


@pytest.mark.asyncio
async def test_bughunter_no_duplicate_replies(db: AsyncSession):
    """BugHunter doesn't reply twice to the same post."""
    await ensure_bots_exist(db)

    human = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email="dupreporter@test.com",
        display_name="DupReporter",
        did_web=f"did:web:agentgraph.co:u:{uuid.uuid4().hex[:8]}",
    )
    db.add(human)
    await db.flush()

    bug_post = Post(
        id=uuid.uuid4(),
        author_entity_id=human.id,
        content="There is a bug with login",
    )
    db.add(bug_post)
    await db.flush()

    payload = {
        "post_id": str(bug_post.id),
        "author_entity_id": str(human.id),
        "content": bug_post.content,
    }

    # Fire twice
    await handle_post_created("post.created", payload, _test_db=db)
    await handle_post_created("post.created", payload, _test_db=db)

    bughunter = BOT_BY_KEY["bughunter"]
    replies = await db.execute(
        select(Post).where(
            Post.author_entity_id == bughunter["id"],
            Post.parent_post_id == bug_post.id,
        )
    )
    assert len(replies.scalars().all()) == 1


@pytest.mark.asyncio
async def test_no_reaction_to_unrelated_post(db: AsyncSession):
    """Bots don't react to posts without trigger keywords."""
    await ensure_bots_exist(db)

    human = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email="normalposter@test.com",
        display_name="NormalPoster",
        did_web=f"did:web:agentgraph.co:u:{uuid.uuid4().hex[:8]}",
    )
    db.add(human)
    await db.flush()

    normal_post = Post(
        id=uuid.uuid4(),
        author_entity_id=human.id,
        content="Just sharing some thoughts about AI alignment",
    )
    db.add(normal_post)
    await db.flush()

    await handle_post_created("post.created", {
        "post_id": str(normal_post.id),
        "author_entity_id": str(human.id),
        "content": normal_post.content,
    }, _test_db=db)

    # No bot should have replied
    for bot_def in BOT_DEFINITIONS:
        replies = await db.execute(
            select(Post).where(
                Post.author_entity_id == bot_def["id"],
                Post.parent_post_id == normal_post.id,
            )
        )
        assert len(replies.scalars().all()) == 0, (
            f"{bot_def['display_name']} shouldn't have replied"
        )


# ---------------------------------------------------------------------------
# Event handler registration
# ---------------------------------------------------------------------------


def test_register_event_handlers():
    """Event handlers register without errors."""
    from src.events import _handlers, clear_handlers

    clear_handlers()
    register_event_handlers()
    assert "entity.registered" in _handlers
    assert "post.created" in _handlers
    clear_handlers()
