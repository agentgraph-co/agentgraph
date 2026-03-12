"""Tests for automated moderation (auto-flag, auto-hide)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, ModerationFlag, Post


@pytest_asyncio.fixture
async def author(db: AsyncSession) -> Entity:
    eid = uuid.uuid4()
    entity = Entity(
        id=eid,
        email=f"author_{uuid.uuid4().hex[:6]}@test.com",
        display_name="Test Author",
        type="human",
        is_active=True,
        email_verified=True,
        did_web=f"did:web:agentgraph.co:users:{eid}",
    )
    db.add(entity)
    await db.flush()
    return entity


@pytest_asyncio.fixture
async def post_obj(db: AsyncSession, author: Entity) -> Post:
    post = Post(
        id=uuid.uuid4(),
        author_entity_id=author.id,
        content="Some content for testing",
    )
    db.add(post)
    await db.flush()
    return post


@dataclass
class FakeToxResult:
    available: bool = True
    toxicity: float = 0.75
    severe_toxicity: float = 0.1
    identity_attack: float = 0.6
    insult: float = 0.3
    profanity: float = 0.2
    threat: float = 0.1
    should_flag: bool = True
    should_block: bool = False


@pytest.mark.asyncio
async def test_auto_flag_post_creates_flag(db: AsyncSession, post_obj: Post):
    from src.api.auto_moderation import auto_flag_post

    tox = FakeToxResult()
    await auto_flag_post(db, post_obj, tox)

    flags = (await db.execute(
        select(ModerationFlag).where(
            ModerationFlag.target_id == post_obj.id,
            ModerationFlag.target_type == "post",
        )
    )).scalars().all()

    assert len(flags) >= 1
    flag = flags[0]
    assert flag.reporter_entity_id is None  # System-generated
    assert "toxicity" in flag.details.lower()


@pytest.mark.asyncio
async def test_auto_flag_includes_scores(db: AsyncSession, post_obj: Post):
    from src.api.auto_moderation import auto_flag_post

    tox = FakeToxResult(toxicity=0.82, identity_attack=0.71)
    await auto_flag_post(db, post_obj, tox)

    flag = (await db.execute(
        select(ModerationFlag).where(
            ModerationFlag.target_id == post_obj.id,
        )
    )).scalar_one()

    assert "0.82" in flag.details
    assert "0.71" in flag.details


@pytest.mark.asyncio
async def test_auto_hide_at_threshold(db: AsyncSession, post_obj: Post, author: Entity):
    from src.api.auto_moderation import check_flag_threshold

    # Create 4 flags (below default threshold of 5)
    for i in range(4):
        flag = ModerationFlag(
            id=uuid.uuid4(),
            reporter_entity_id=None,
            target_type="post",
            target_id=post_obj.id,
            reason="harassment",
            details=f"Flag {i}",
        )
        db.add(flag)
    await db.flush()

    await check_flag_threshold(db, post_obj.id)
    await db.refresh(post_obj)
    assert post_obj.is_hidden is False  # 4 < 5

    # Add 5th flag — should trigger auto-hide
    flag5 = ModerationFlag(
        id=uuid.uuid4(),
        reporter_entity_id=None,
        target_type="post",
        target_id=post_obj.id,
        reason="spam",
        details="Flag 5",
    )
    db.add(flag5)
    await db.flush()

    await check_flag_threshold(db, post_obj.id)
    await db.refresh(post_obj)
    assert post_obj.is_hidden is True


@pytest.mark.asyncio
async def test_auto_hide_custom_threshold(db: AsyncSession, post_obj: Post):
    from src.api.auto_moderation import check_flag_threshold
    from src.config import settings

    original = settings.auto_hide_flag_threshold
    settings.auto_hide_flag_threshold = 2

    try:
        # Add 2 flags
        for i in range(2):
            flag = ModerationFlag(
                id=uuid.uuid4(),
                reporter_entity_id=None,
                target_type="post",
                target_id=post_obj.id,
                reason="spam",
                details=f"Flag {i}",
            )
            db.add(flag)
        await db.flush()

        await check_flag_threshold(db, post_obj.id)
        await db.refresh(post_obj)
        assert post_obj.is_hidden is True
    finally:
        settings.auto_hide_flag_threshold = original


@pytest.mark.asyncio
async def test_already_hidden_post_stays_hidden(db: AsyncSession, author: Entity):
    from src.api.auto_moderation import check_flag_threshold

    post = Post(
        id=uuid.uuid4(),
        author_entity_id=author.id,
        content="Already hidden",
        is_hidden=True,
    )
    db.add(post)
    await db.flush()

    # Should not error even with 0 flags
    await check_flag_threshold(db, post.id)
    await db.refresh(post)
    assert post.is_hidden is True


@pytest.mark.asyncio
async def test_nonexistent_post_does_not_error(db: AsyncSession):
    from src.api.auto_moderation import check_flag_threshold

    # Should not raise
    await check_flag_threshold(db, uuid.uuid4())
