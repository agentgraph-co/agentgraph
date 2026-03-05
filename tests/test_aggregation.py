from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.aggregation import AggregationResult, import_content_batch
from src.database import get_db
from src.main import app
from src.models import Entity, EntityType, Post


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
ME_URL = "/api/v1/auth/me"
INGEST_URL = "/api/v1/aggregation/ingest"
SOURCES_URL = "/api/v1/aggregation/sources"

USER = {
    "email": "agguser@example.com",
    "password": "Str0ngP@ss",
    "display_name": "AggUser",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Unit tests for import_content_batch ---


@pytest.mark.asyncio
async def test_import_batch_basic(db):
    """Import a batch of items and verify posts are created."""
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="AggBot",
        did_web=f"did:web:agg-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db.add(entity)
    await db.flush()

    items = [
        {"content": "Post one", "external_id": "ext-1"},
        {"content": "Post two", "external_id": "ext-2"},
        {"content": "Post three"},
    ]
    result = await import_content_batch(db, entity.id, items, source_type="api")

    assert result.imported == 3
    assert result.skipped == 0
    assert result.errors == []
    assert result.total == 3


@pytest.mark.asyncio
async def test_deduplication(db):
    """Items with duplicate external_id should be skipped on second import."""
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="DedupBot",
        did_web=f"did:web:dedup-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db.add(entity)
    await db.flush()

    items = [
        {"content": "First post", "external_id": "dup-1"},
        {"content": "Second post", "external_id": "dup-2"},
    ]

    # First import
    r1 = await import_content_batch(db, entity.id, items, source_type="api")
    assert r1.imported == 2
    assert r1.skipped == 0

    # Refresh to pick up onboarding_data changes
    await db.refresh(entity)

    # Second import with same external_ids
    r2 = await import_content_batch(db, entity.id, items, source_type="api")
    assert r2.imported == 0
    assert r2.skipped == 2


@pytest.mark.asyncio
async def test_empty_content_skipped(db):
    """Items with empty content should be skipped."""
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="EmptyBot",
        did_web=f"did:web:empty-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db.add(entity)
    await db.flush()

    items = [
        {"content": ""},
        {"content": "   "},
        {"content": "Valid post"},
    ]
    result = await import_content_batch(db, entity.id, items, source_type="api")

    assert result.imported == 1
    assert result.skipped == 2


@pytest.mark.asyncio
async def test_invalid_source_type(db):
    """Invalid source_type should return an error immediately."""
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="BadSrcBot",
        did_web=f"did:web:badsrc-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db.add(entity)
    await db.flush()

    items = [{"content": "Hello"}]
    result = await import_content_batch(
        db, entity.id, items, source_type="unknown_source"
    )

    assert result.imported == 0
    assert len(result.errors) == 1
    assert "Invalid source_type" in result.errors[0]


@pytest.mark.asyncio
async def test_content_truncation(db):
    """Content longer than 10000 chars should be truncated."""
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="LongBot",
        did_web=f"did:web:long-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db.add(entity)
    await db.flush()

    long_content = "x" * 15000
    items = [{"content": long_content, "external_id": "long-1"}]
    result = await import_content_batch(db, entity.id, items, source_type="rss")

    assert result.imported == 1

    # Verify the post was truncated
    from sqlalchemy import select

    stmt = select(Post).where(Post.author_entity_id == entity.id)
    row = (await db.execute(stmt)).scalars().first()
    assert row is not None
    assert len(row.content) == 10000


@pytest.mark.asyncio
async def test_media_fields_carried_through(db):
    """media_url, media_type, and flair should persist on created posts."""
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="MediaBot",
        did_web=f"did:web:media-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db.add(entity)
    await db.flush()

    items = [
        {
            "content": "Check this image",
            "external_id": "media-1",
            "media_url": "https://example.com/img.png",
            "media_type": "image",
            "flair": "showcase",
        }
    ]
    result = await import_content_batch(db, entity.id, items, source_type="api")
    assert result.imported == 1

    from sqlalchemy import select

    stmt = select(Post).where(Post.author_entity_id == entity.id)
    post = (await db.execute(stmt)).scalars().first()
    assert post is not None
    assert post.media_url == "https://example.com/img.png"
    assert post.media_type == "image"
    assert post.flair == "showcase"


@pytest.mark.asyncio
async def test_inactive_entity_rejected(db):
    """Inactive entity should be rejected."""
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="InactiveBot",
        did_web=f"did:web:inactive-{uuid.uuid4().hex[:8]}",
        is_active=False,
    )
    db.add(entity)
    await db.flush()

    items = [{"content": "Should fail"}]
    result = await import_content_batch(db, entity.id, items, source_type="api")

    assert result.imported == 0
    assert "not found or inactive" in result.errors[0]


@pytest.mark.asyncio
async def test_nonexistent_entity_rejected(db):
    """Non-existent entity ID should be rejected."""
    fake_id = uuid.uuid4()
    items = [{"content": "Should fail"}]
    result = await import_content_batch(db, fake_id, items, source_type="api")

    assert result.imported == 0
    assert "not found or inactive" in result.errors[0]


# --- API endpoint tests ---


@pytest.mark.asyncio
async def test_sources_endpoint(client: AsyncClient):
    """GET /aggregation/sources returns supported source types."""
    resp = await client.get(SOURCES_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert "source_types" in data
    assert set(data["source_types"]) == {"rss", "api", "webhook_ingest"}


@pytest.mark.asyncio
async def test_ingest_requires_auth(client: AsyncClient):
    """POST /aggregation/ingest should require authentication."""
    resp = await client.post(INGEST_URL, json={
        "agent_entity_id": str(uuid.uuid4()),
        "items": [{"content": "Hello"}],
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ingest_self(client: AsyncClient, db):
    """Authenticated user can ingest content for themselves."""
    token, entity_id = await _setup_user(client, USER)

    resp = await client.post(
        INGEST_URL,
        json={
            "agent_entity_id": entity_id,
            "items": [
                {"content": "Imported post 1", "external_id": "api-1"},
                {"content": "Imported post 2", "external_id": "api-2"},
            ],
            "source_type": "api",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 2
    assert data["skipped"] == 0
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_ingest_unauthorized_entity(client: AsyncClient, db):
    """User cannot ingest content for another entity they don't operate."""
    token, _ = await _setup_user(client, USER)

    # Create a separate entity not operated by the user
    other = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        display_name="OtherBot",
        did_web=f"did:web:other-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    db.add(other)
    await db.flush()

    resp = await client.post(
        INGEST_URL,
        json={
            "agent_entity_id": str(other.id),
            "items": [{"content": "Should fail"}],
        },
        headers=_auth(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_aggregation_result_to_dict():
    """AggregationResult.to_dict works correctly."""
    r = AggregationResult()
    r.imported = 5
    r.skipped = 2
    r.errors = ["err1", "err2"]

    d = r.to_dict()
    assert d["imported"] == 5
    assert d["skipped"] == 2
    assert d["total"] == 9
    assert d["errors"] == ["err1", "err2"]
