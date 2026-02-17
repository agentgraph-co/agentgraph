from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    Entity,
    EntityRelationship,
    EntityType,
    Post,
    RelationshipType,
    TrustScore,
    Vote,
    VoteDirection,
)

# --- Entity tests ---


@pytest.mark.asyncio
async def test_create_human_entity(db: AsyncSession):
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email="test@example.com",
        display_name="Test Human",
        did_web="did:web:agentgraph.dev:user:test",
    )
    db.add(entity)
    await db.flush()

    result = await db.get(Entity, entity.id)
    assert result is not None
    assert result.type == EntityType.HUMAN
    assert result.email == "test@example.com"
    assert result.display_name == "Test Human"
    assert result.is_active is True
    assert result.is_admin is False


@pytest.mark.asyncio
async def test_create_agent_entity(db: AsyncSession):
    operator = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        display_name="Operator",
        did_web="did:web:agentgraph.dev:user:operator",
    )
    db.add(operator)
    await db.flush()

    agent = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="Test Agent",
        did_web="did:web:agentgraph.dev:agent:test",
        capabilities=["text-generation", "code-review"],
        autonomy_level=3,
        operator_id=operator.id,
    )
    db.add(agent)
    await db.flush()

    result = await db.get(Entity, agent.id)
    assert result is not None
    assert result.type == EntityType.AGENT
    assert result.autonomy_level == 3
    assert result.operator_id == operator.id


# --- Post tests ---


@pytest.mark.asyncio
async def test_create_post(db: AsyncSession):
    author = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        display_name="Author",
        did_web="did:web:agentgraph.dev:user:author",
    )
    db.add(author)
    await db.flush()

    post = Post(
        id=uuid.uuid4(),
        author_entity_id=author.id,
        content="Hello AgentGraph!",
    )
    db.add(post)
    await db.flush()

    result = await db.get(Post, post.id)
    assert result is not None
    assert result.content == "Hello AgentGraph!"
    assert result.vote_count == 0
    assert result.is_hidden is False


@pytest.mark.asyncio
async def test_create_reply(db: AsyncSession):
    author = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        display_name="Replier",
        did_web="did:web:agentgraph.dev:user:replier",
    )
    db.add(author)
    await db.flush()

    parent = Post(
        id=uuid.uuid4(),
        author_entity_id=author.id,
        content="Parent post",
    )
    db.add(parent)
    await db.flush()

    reply = Post(
        id=uuid.uuid4(),
        author_entity_id=author.id,
        content="This is a reply",
        parent_post_id=parent.id,
    )
    db.add(reply)
    await db.flush()

    result = await db.get(Post, reply.id)
    assert result is not None
    assert result.parent_post_id == parent.id


# --- Vote tests ---


@pytest.mark.asyncio
async def test_create_vote(db: AsyncSession):
    voter = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        display_name="Voter",
        did_web="did:web:agentgraph.dev:user:voter",
    )
    db.add(voter)
    await db.flush()

    post = Post(
        id=uuid.uuid4(),
        author_entity_id=voter.id,
        content="Voteable post",
    )
    db.add(post)
    await db.flush()

    vote = Vote(
        id=uuid.uuid4(),
        entity_id=voter.id,
        post_id=post.id,
        direction=VoteDirection.UP,
    )
    db.add(vote)
    await db.flush()

    result = await db.get(Vote, vote.id)
    assert result is not None
    assert result.direction == VoteDirection.UP


# --- TrustScore tests ---


@pytest.mark.asyncio
async def test_create_trust_score(db: AsyncSession):
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="Scored Agent",
        did_web="did:web:agentgraph.dev:agent:scored",
    )
    db.add(entity)
    await db.flush()

    score = TrustScore(
        id=uuid.uuid4(),
        entity_id=entity.id,
        score=0.75,
        components={"verification": 0.3, "age": 0.2, "activity": 0.25},
    )
    db.add(score)
    await db.flush()

    result = await db.get(TrustScore, score.id)
    assert result is not None
    assert result.score == 0.75
    assert result.components["verification"] == 0.3


# --- Relationship tests ---


@pytest.mark.asyncio
async def test_create_follow_relationship(db: AsyncSession):
    user_a = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        display_name="User A",
        did_web="did:web:agentgraph.dev:user:a",
    )
    user_b = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        display_name="User B",
        did_web="did:web:agentgraph.dev:user:b",
    )
    db.add_all([user_a, user_b])
    await db.flush()

    rel = EntityRelationship(
        id=uuid.uuid4(),
        source_entity_id=user_a.id,
        target_entity_id=user_b.id,
        type=RelationshipType.FOLLOW,
    )
    db.add(rel)
    await db.flush()

    result = await db.get(EntityRelationship, rel.id)
    assert result is not None
    assert result.type == RelationshipType.FOLLOW


# --- Table count verification ---


@pytest.mark.asyncio
async def test_all_tables_exist(db: AsyncSession):
    result = await db.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        )
    )
    tables = [row[0] for row in result.fetchall()]
    expected = [
        "alembic_version",
        "api_keys",
        "did_documents",
        "entities",
        "entity_relationships",
        "evolution_records",
        "moderation_flags",
        "notifications",
        "posts",
        "trust_scores",
        "votes",
        "webhook_subscriptions",
    ]
    assert tables == expected
