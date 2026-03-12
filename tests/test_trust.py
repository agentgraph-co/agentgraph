from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, EntityType, Post
from src.trust.score import (
    _age_factor,
    _verification_factor,
    compute_trust_score,
)


def _make_entity(**kwargs) -> Entity:
    defaults = {
        "id": uuid.uuid4(),
        "type": EntityType.HUMAN,
        "display_name": "Test",
        "did_web": f"did:web:agentgraph.co:users:{uuid.uuid4()}",
        "email_verified": False,
        "bio_markdown": "",
        "operator_id": None,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return Entity(**defaults)


# --- Verification factor ---


def test_verification_unverified():
    entity = _make_entity()
    assert _verification_factor(entity) == 0.0


def test_verification_email_verified():
    entity = _make_entity(email_verified=True)
    assert _verification_factor(entity) == 0.3


def test_verification_profile_complete():
    entity = _make_entity(bio_markdown="I am a developer")
    assert _verification_factor(entity) == 0.5


def test_verification_operator_linked():
    entity = _make_entity(operator_id=uuid.uuid4())
    assert _verification_factor(entity) == 0.7


# --- Age factor ---


def test_age_brand_new():
    entity = _make_entity(created_at=datetime.now(timezone.utc))
    assert _age_factor(entity) == 0.0


def test_age_one_year():
    entity = _make_entity(
        created_at=datetime.now(timezone.utc) - timedelta(days=365)
    )
    assert _age_factor(entity) == 1.0


def test_age_half_year():
    entity = _make_entity(
        created_at=datetime.now(timezone.utc) - timedelta(days=182)
    )
    factor = _age_factor(entity)
    assert 0.49 < factor < 0.51


def test_age_caps_at_one():
    entity = _make_entity(
        created_at=datetime.now(timezone.utc) - timedelta(days=730)
    )
    assert _age_factor(entity) == 1.0


# --- Full score computation ---


@pytest.mark.asyncio
async def test_compute_trust_score_new_entity(db: AsyncSession):
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        display_name="New User",
        did_web=f"did:web:agentgraph.co:users:{uuid.uuid4()}",
    )
    db.add(entity)
    await db.flush()

    ts = await compute_trust_score(db, entity.id)
    assert ts.score >= 0.0
    assert ts.score <= 1.0
    assert "verification" in ts.components
    assert "age" in ts.components
    assert "activity" in ts.components
    assert "reputation" in ts.components


@pytest.mark.asyncio
async def test_compute_trust_score_active_entity(db: AsyncSession):
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email_verified=True,
        display_name="Active User",
        bio_markdown="I post a lot",
        did_web=f"did:web:agentgraph.co:users:{uuid.uuid4()}",
    )
    db.add(entity)
    await db.flush()

    # Create some posts
    for i in range(10):
        db.add(Post(
            id=uuid.uuid4(),
            author_entity_id=entity.id,
            content=f"Post {i}",
        ))
    await db.flush()

    ts = await compute_trust_score(db, entity.id)
    assert ts.score > 0.0
    assert ts.components["activity"] > 0.0
    assert ts.components["verification"] == 0.5  # bio filled


@pytest.mark.asyncio
async def test_compute_trust_score_upserts(db: AsyncSession):
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        display_name="Upsert User",
        did_web=f"did:web:agentgraph.co:users:{uuid.uuid4()}",
    )
    db.add(entity)
    await db.flush()

    ts1 = await compute_trust_score(db, entity.id)
    score1 = ts1.score

    # Add activity and recompute
    db.add(Post(
        id=uuid.uuid4(),
        author_entity_id=entity.id,
        content="New post",
    ))
    await db.flush()

    ts2 = await compute_trust_score(db, entity.id)
    assert ts2.score >= score1  # score should stay same or increase


@pytest.mark.asyncio
async def test_activity_log_scale_diminishing_returns(db: AsyncSession):
    """Verify that 100 posts don't give 10x more score than 10 posts."""
    entity_few = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        display_name="Few Posts",
        did_web=f"did:web:agentgraph.co:users:{uuid.uuid4()}",
    )
    entity_many = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        display_name="Many Posts",
        did_web=f"did:web:agentgraph.co:users:{uuid.uuid4()}",
    )
    db.add_all([entity_few, entity_many])
    await db.flush()

    for i in range(10):
        db.add(Post(
            id=uuid.uuid4(),
            author_entity_id=entity_few.id,
            content=f"Post {i}",
        ))
    for i in range(100):
        db.add(Post(
            id=uuid.uuid4(),
            author_entity_id=entity_many.id,
            content=f"Post {i}",
        ))
    await db.flush()

    ts_few = await compute_trust_score(db, entity_few.id)
    ts_many = await compute_trust_score(db, entity_many.id)

    # 100 posts should NOT give 10x the activity score of 10 posts
    ratio = ts_many.components["activity"] / ts_few.components["activity"]
    assert ratio < 2.0  # log scale ensures diminishing returns
