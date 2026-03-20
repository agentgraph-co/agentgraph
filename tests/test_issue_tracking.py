"""Tests for bot issue tracking and resolution lifecycle."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_service import hash_password
from src.bots.definitions import BOT_BY_KEY
from src.bots.engine import ensure_bots_exist, handle_post_created
from src.database import get_db
from src.main import app
from src.models import Entity, EntityType, IssueReport, Post


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _create_admin(db: AsyncSession) -> tuple[Entity, str]:
    """Create an admin entity and return (entity, password)."""
    password = "AdminPass123!"
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email=f"admin-{uuid.uuid4().hex[:6]}@test.com",
        display_name="AdminUser",
        did_web=f"did:web:agentgraph.co:u:{uuid.uuid4().hex[:8]}",
        password_hash=hash_password(password),
        email_verified=True,
        is_active=True,
        is_admin=True,
    )
    db.add(entity)
    await db.flush()
    return entity, password


async def _login(client: AsyncClient, email: str, password: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_bughunter_creates_issue_report(db: AsyncSession):
    """BugHunter creates an IssueReport when replying to a bug post."""
    await ensure_bots_exist(db)

    human = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email="bug-reporter@test.com",
        display_name="BugReporter",
        did_web=f"did:web:agentgraph.co:u:{uuid.uuid4().hex[:8]}",
    )
    db.add(human)
    await db.flush()

    bug_post = Post(
        id=uuid.uuid4(),
        author_entity_id=human.id,
        content="I found a bug — the search page crashes on special characters",
    )
    db.add(bug_post)
    await db.flush()

    await handle_post_created("post.created", {
        "post_id": str(bug_post.id),
        "author_entity_id": str(human.id),
        "content": bug_post.content,
    }, _test_db=db)

    # Verify issue report was created
    result = await db.execute(
        select(IssueReport).where(IssueReport.post_id == bug_post.id)
    )
    issue = result.scalar_one_or_none()
    assert issue is not None
    assert issue.issue_type == "bug"
    assert issue.status == "open"
    assert issue.reporter_entity_id == human.id
    assert issue.bot_entity_id == BOT_BY_KEY["bughunter"]["id"]
    assert issue.bot_reply_id is not None
    assert "bug" in issue.title.lower() or "crash" in issue.title.lower()


@pytest.mark.asyncio
async def test_featurebot_creates_issue_report(db: AsyncSession):
    """FeatureBot creates an IssueReport when replying to a feature request."""
    await ensure_bots_exist(db)

    human = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email="feature-req@test.com",
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

    result = await db.execute(
        select(IssueReport).where(IssueReport.post_id == feature_post.id)
    )
    issue = result.scalar_one_or_none()
    assert issue is not None
    assert issue.issue_type == "feature"
    assert issue.status == "open"


@pytest.mark.asyncio
async def test_admin_list_issues(client: AsyncClient, db: AsyncSession):
    """Admin can list issue reports."""
    await ensure_bots_exist(db)
    admin, password = await _create_admin(db)
    token = await _login(client, admin.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    # Create a bug issue directly
    human = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email="lister@test.com",
        display_name="Lister",
        did_web=f"did:web:agentgraph.co:u:{uuid.uuid4().hex[:8]}",
    )
    db.add(human)
    await db.flush()

    post = Post(id=uuid.uuid4(), author_entity_id=human.id, content="Bug: something broke")
    db.add(post)
    await db.flush()

    issue = IssueReport(
        id=uuid.uuid4(),
        post_id=post.id,
        reporter_entity_id=human.id,
        bot_entity_id=BOT_BY_KEY["bughunter"]["id"],
        issue_type="bug",
        title="Bug: something broke",
        status="open",
    )
    db.add(issue)
    await db.flush()

    r = await client.get("/api/v1/admin/issues", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert any(i["id"] == str(issue.id) for i in data["issues"])


@pytest.mark.asyncio
async def test_admin_list_issues_filter_by_status(client: AsyncClient, db: AsyncSession):
    """Admin can filter issues by status."""
    await ensure_bots_exist(db)
    admin, password = await _create_admin(db)
    token = await _login(client, admin.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/v1/admin/issues", headers=headers, params={"status": "open"})
    assert r.status_code == 200
    for iss in r.json()["issues"]:
        assert iss["status"] == "open"


@pytest.mark.asyncio
async def test_admin_resolve_issue(client: AsyncClient, db: AsyncSession):
    """Admin can resolve an issue, triggering bot follow-up reply."""
    await ensure_bots_exist(db)
    admin, password = await _create_admin(db)
    token = await _login(client, admin.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    # Create issue
    human = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email="resolver-test@test.com",
        display_name="ResolverTest",
        did_web=f"did:web:agentgraph.co:u:{uuid.uuid4().hex[:8]}",
        email_verified=True,
        is_active=True,
    )
    db.add(human)
    await db.flush()

    post = Post(id=uuid.uuid4(), author_entity_id=human.id, content="Bug: fix this please")
    db.add(post)
    await db.flush()

    issue = IssueReport(
        id=uuid.uuid4(),
        post_id=post.id,
        reporter_entity_id=human.id,
        bot_entity_id=BOT_BY_KEY["bughunter"]["id"],
        issue_type="bug",
        title="Bug: fix this please",
        status="open",
    )
    db.add(issue)
    await db.flush()

    # Resolve the issue
    r = await client.patch(
        f"/api/v1/admin/issues/{issue.id}/resolve",
        headers=headers,
        json={"status": "resolved", "resolution_note": "Fixed in latest update"},
    )
    assert r.status_code == 200
    assert r.json()["message"] == "Issue resolved"

    # Verify issue updated
    await db.refresh(issue)
    assert issue.status == "resolved"
    assert issue.resolution_note == "Fixed in latest update"
    assert issue.resolved_by == admin.id
    assert issue.resolved_at is not None

    # Verify bot posted a follow-up reply
    bughunter = BOT_BY_KEY["bughunter"]
    replies = await db.execute(
        select(Post).where(
            Post.author_entity_id == bughunter["id"],
            Post.parent_post_id == post.id,
        )
    )
    reply_list = replies.scalars().all()
    assert len(reply_list) >= 1
    latest = reply_list[-1]
    assert "resolved" in latest.content.lower()
    assert "Fixed in latest update" in latest.content


@pytest.mark.asyncio
async def test_resolve_already_resolved_issue_fails(client: AsyncClient, db: AsyncSession):
    """Resolving an already resolved issue returns 409."""
    await ensure_bots_exist(db)
    admin, password = await _create_admin(db)
    token = await _login(client, admin.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    human = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email="double-resolve@test.com",
        display_name="DoubleResolve",
        did_web=f"did:web:agentgraph.co:u:{uuid.uuid4().hex[:8]}",
    )
    db.add(human)
    await db.flush()

    post = Post(id=uuid.uuid4(), author_entity_id=human.id, content="Bug: already fixed")
    db.add(post)
    await db.flush()

    issue = IssueReport(
        id=uuid.uuid4(),
        post_id=post.id,
        reporter_entity_id=human.id,
        bot_entity_id=BOT_BY_KEY["bughunter"]["id"],
        issue_type="bug",
        title="Bug: already fixed",
        status="resolved",
    )
    db.add(issue)
    await db.flush()

    r = await client.patch(
        f"/api/v1/admin/issues/{issue.id}/resolve",
        headers=headers,
        json={"status": "resolved", "resolution_note": "Try again"},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_non_admin_cannot_list_issues(client: AsyncClient, db: AsyncSession):
    """Non-admin cannot access issue endpoints."""
    human = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email=f"nonadmin-{uuid.uuid4().hex[:6]}@test.com",
        display_name="NonAdmin",
        did_web=f"did:web:agentgraph.co:u:{uuid.uuid4().hex[:8]}",
        password_hash=hash_password("TestPass123!"),
        email_verified=True,
        is_active=True,
        is_admin=False,
    )
    db.add(human)
    await db.flush()

    token = await _login(client, human.email, "TestPass123!")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/v1/admin/issues", headers=headers)
    assert r.status_code == 403
