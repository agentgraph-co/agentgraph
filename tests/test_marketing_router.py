"""Tests for the marketing admin router endpoints."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text, update

from src.database import get_db
from src.main import app
from src.models import Entity


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
BASE = "/api/v1/admin/marketing"

ADMIN_USER = {
    "email": "mktg_admin@example.com",
    "password": "Str0ngP@ss!1",
    "display_name": "MktgAdmin",
}

NORMAL_USER = {
    "email": "mktg_normal@example.com",
    "password": "Str0ngP@ss!2",
    "display_name": "MktgNormal",
}


async def _setup_admin(client: AsyncClient, db) -> str:
    """Register a user, promote to admin, return auth token."""
    await client.post(REGISTER_URL, json=ADMIN_USER)
    # Promote to admin
    await db.execute(
        update(Entity)
        .where(Entity.email == ADMIN_USER["email"])
        .values(is_admin=True)
    )
    await db.flush()
    resp = await client.post(
        LOGIN_URL,
        json={"email": ADMIN_USER["email"], "password": ADMIN_USER["password"]},
    )
    return resp.json()["access_token"]


async def _setup_normal_user(client: AsyncClient) -> str:
    """Register a non-admin user, return auth token."""
    await client.post(REGISTER_URL, json=NORMAL_USER)
    resp = await client.post(
        LOGIN_URL,
        json={"email": NORMAL_USER["email"], "password": NORMAL_USER["password"]},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _ensure_marketing_tables(db):
    """Ensure marketing tables exist in test DB."""
    await db.execute(text(
        "CREATE TABLE IF NOT EXISTS marketing_campaigns ("
        "  id UUID PRIMARY KEY,"
        "  name VARCHAR(200) NOT NULL,"
        "  topic VARCHAR(100) NOT NULL,"
        "  platforms TEXT[] NOT NULL DEFAULT '{}',"
        "  status VARCHAR(20) NOT NULL DEFAULT 'draft',"
        "  schedule_config JSONB,"
        "  start_date DATE,"
        "  end_date DATE,"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    ))
    await db.execute(text(
        "CREATE TABLE IF NOT EXISTS marketing_posts ("
        "  id UUID PRIMARY KEY,"
        "  campaign_id UUID REFERENCES marketing_campaigns(id) ON DELETE SET NULL,"
        "  platform VARCHAR(50) NOT NULL,"
        "  external_id VARCHAR(255),"
        "  content TEXT NOT NULL,"
        "  content_hash VARCHAR(64) NOT NULL,"
        "  post_type VARCHAR(20) NOT NULL,"
        "  topic VARCHAR(100),"
        "  status VARCHAR(20) NOT NULL DEFAULT 'draft',"
        "  parent_external_id VARCHAR(255),"
        "  llm_model VARCHAR(50),"
        "  llm_tokens_in INTEGER,"
        "  llm_tokens_out INTEGER,"
        "  llm_cost_usd FLOAT,"
        "  metrics_json JSONB,"
        "  utm_params JSONB,"
        "  error_message TEXT,"
        "  retry_count INTEGER NOT NULL DEFAULT 0,"
        "  posted_at TIMESTAMPTZ,"
        "  metrics_updated_at TIMESTAMPTZ,"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    ))
    await db.flush()


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


async def _insert_marketing_post(
    db,
    *,
    platform: str = "bluesky",
    content: str = "Test post",
    post_type: str = "proactive",
    topic: str = "security",
    status: str = "human_review",
    llm_model: str | None = "haiku",
    llm_cost_usd: float = 0.001,
    posted_at: datetime | None = None,
    metrics_json: dict | None = None,
) -> uuid.UUID:
    """Insert a marketing post directly into DB, return its ID."""
    post_id = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO marketing_posts "
        "(id, platform, content, content_hash, post_type, topic, status, "
        " llm_model, llm_cost_usd, posted_at, metrics_json, created_at, updated_at) "
        "VALUES (:id, :platform, :content, :hash, :post_type, :topic, :status, "
        " :llm_model, :llm_cost_usd, :posted_at, :metrics_json, now(), now())"
    ), {
        "id": post_id,
        "platform": platform,
        "content": content,
        "hash": _content_hash(content),
        "post_type": post_type,
        "topic": topic,
        "status": status,
        "llm_model": llm_model,
        "llm_cost_usd": llm_cost_usd,
        "posted_at": posted_at,
        "metrics_json": None if metrics_json is None else str(metrics_json).replace("'", '"'),
    })
    await db.flush()
    return post_id


# ---- Auth / access tests ----


@pytest.mark.asyncio
async def test_dashboard_requires_auth(client):
    """Dashboard returns 401 without auth."""
    resp = await client.get(f"{BASE}/dashboard")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_requires_admin(client, db):
    """Dashboard returns 403 for non-admin users."""
    token = await _setup_normal_user(client)
    resp = await client.get(f"{BASE}/dashboard", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_drafts_requires_admin(client, db):
    """Drafts endpoint returns 403 for non-admin."""
    token = await _setup_normal_user(client)
    resp = await client.get(f"{BASE}/drafts", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_health_requires_admin(client, db):
    """Health endpoint returns 403 for non-admin."""
    token = await _setup_normal_user(client)
    resp = await client.get(f"{BASE}/health", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_trigger_requires_admin(client, db):
    """Trigger endpoint returns 403 for non-admin."""
    token = await _setup_normal_user(client)
    resp = await client.post(f"{BASE}/trigger", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_digest_requires_admin(client, db):
    """Digest endpoint returns 403 for non-admin."""
    token = await _setup_normal_user(client)
    resp = await client.get(f"{BASE}/digest", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_activity_requires_admin(client, db):
    """Activity endpoint returns 403 for non-admin."""
    token = await _setup_normal_user(client)
    resp = await client.get(f"{BASE}/activity", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_conversions_requires_admin(client, db):
    """Conversions endpoint returns 403 for non-admin."""
    token = await _setup_normal_user(client)
    resp = await client.get(f"{BASE}/conversions", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_recap_requires_admin(client, db):
    """Recap endpoint returns 403 for non-admin."""
    token = await _setup_normal_user(client)
    resp = await client.post(f"{BASE}/recap", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reddit_threads_requires_admin(client, db):
    """Reddit threads endpoint returns 403 for non-admin."""
    token = await _setup_normal_user(client)
    resp = await client.get(f"{BASE}/reddit/threads", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_hf_discussions_requires_admin(client, db):
    """HuggingFace discussions endpoint returns 403 for non-admin."""
    token = await _setup_normal_user(client)
    resp = await client.get(
        f"{BASE}/huggingface/discussions", headers=_auth(token),
    )
    assert resp.status_code == 403


# ---- Dashboard ----


@pytest.mark.asyncio
async def test_dashboard_returns_structure(client, db):
    """Dashboard returns expected top-level keys."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    # Mock the Redis-dependent cost tracker calls
    with patch(
        "src.marketing.dashboard.get_daily_spend",
        new_callable=AsyncMock,
        return_value=0.05,
    ), patch(
        "src.marketing.dashboard.get_monthly_spend",
        new_callable=AsyncMock,
        return_value=1.25,
    ):
        resp = await client.get(f"{BASE}/dashboard", headers=_auth(token))

    assert resp.status_code == 200
    data = resp.json()
    assert "platform_stats" in data
    assert "topic_stats" in data
    assert "type_stats" in data
    assert "engagement" in data
    assert "cost" in data
    assert "recent_posts" in data
    assert "pending_drafts" in data
    assert "campaigns" in data


@pytest.mark.asyncio
async def test_dashboard_with_posts(client, db):
    """Dashboard aggregates marketing post data correctly."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    now = datetime.now(timezone.utc)
    await _insert_marketing_post(
        db,
        platform="bluesky",
        content="Test bluesky post",
        status="posted",
        posted_at=now,
    )
    await _insert_marketing_post(
        db,
        platform="bluesky",
        content="Draft bluesky post",
        status="human_review",
    )

    with patch(
        "src.marketing.dashboard.get_daily_spend",
        new_callable=AsyncMock,
        return_value=0.0,
    ), patch(
        "src.marketing.dashboard.get_monthly_spend",
        new_callable=AsyncMock,
        return_value=0.0,
    ):
        resp = await client.get(f"{BASE}/dashboard", headers=_auth(token))

    assert resp.status_code == 200
    data = resp.json()
    assert data["pending_drafts"] >= 1


# ---- Drafts ----


@pytest.mark.asyncio
async def test_get_drafts_empty(client, db):
    """Drafts endpoint returns empty list when no drafts exist."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    resp = await client.get(f"{BASE}/drafts", headers=_auth(token))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_drafts_returns_pending(client, db):
    """Drafts endpoint returns posts in human_review status."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    post_id = await _insert_marketing_post(
        db,
        platform="hackernews",
        content="HN draft content",
        status="human_review",
        topic="security",
    )

    resp = await client.get(f"{BASE}/drafts", headers=_auth(token))
    assert resp.status_code == 200
    drafts = resp.json()
    assert len(drafts) >= 1
    ids = [d["id"] for d in drafts]
    assert str(post_id) in ids


@pytest.mark.asyncio
async def test_get_drafts_filter_by_platform(client, db):
    """Drafts can be filtered by platform."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    await _insert_marketing_post(
        db, platform="hackernews", content="HN post for filter",
        status="human_review",
    )
    await _insert_marketing_post(
        db, platform="reddit", content="Reddit post for filter",
        status="human_review",
    )

    resp = await client.get(
        f"{BASE}/drafts?platform=hackernews", headers=_auth(token),
    )
    assert resp.status_code == 200
    drafts = resp.json()
    for d in drafts:
        assert d["platform"] == "hackernews"


@pytest.mark.asyncio
async def test_get_drafts_filter_by_status(client, db):
    """Drafts can be filtered by custom status values."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    await _insert_marketing_post(
        db, platform="bluesky", content="Draft status post",
        status="draft",
    )

    resp = await client.get(
        f"{BASE}/drafts?status=draft", headers=_auth(token),
    )
    assert resp.status_code == 200
    drafts = resp.json()
    for d in drafts:
        assert d["status"] == "draft"


@pytest.mark.asyncio
async def test_action_draft_approve(client, db):
    """Approving a draft moves it to queued (then attempts to post)."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    post_id = await _insert_marketing_post(
        db, platform="bluesky", content="Approve me",
        status="human_review",
    )

    # Mock the orchestrator's _get_adapters to avoid real posting
    mock_adapter = AsyncMock()
    mock_adapter.is_configured = AsyncMock(return_value=False)

    with patch(
        "src.marketing.orchestrator._get_adapters",
        return_value={"bluesky": mock_adapter},
    ):
        resp = await client.post(
            f"{BASE}/drafts/{post_id}",
            json={"action": "approve"},
            headers=_auth(token),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(post_id)
    # Status should be "queued" since adapter was not configured
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_action_draft_reject(client, db):
    """Rejecting a draft marks it as failed."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    post_id = await _insert_marketing_post(
        db, platform="hackernews", content="Reject me",
        status="human_review",
    )

    resp = await client.post(
        f"{BASE}/drafts/{post_id}",
        json={"action": "reject", "reason": "Not good enough"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"


@pytest.mark.asyncio
async def test_action_draft_edit_approve(client, db):
    """Edit+approve changes content and moves to queued."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    post_id = await _insert_marketing_post(
        db, platform="bluesky", content="Edit me",
        status="human_review",
    )

    mock_adapter = AsyncMock()
    mock_adapter.is_configured = AsyncMock(return_value=False)

    with patch(
        "src.marketing.orchestrator._get_adapters",
        return_value={"bluesky": mock_adapter},
    ):
        resp = await client.post(
            f"{BASE}/drafts/{post_id}",
            json={"action": "edit_approve", "content": "Edited content"},
            headers=_auth(token),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "Edited content"
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_action_draft_edit_approve_requires_content(client, db):
    """Edit+approve without content returns 400."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    post_id = await _insert_marketing_post(
        db, platform="bluesky", content="Edit me no content",
        status="human_review",
    )

    resp = await client.post(
        f"{BASE}/drafts/{post_id}",
        json={"action": "edit_approve"},
        headers=_auth(token),
    )
    assert resp.status_code == 400
    assert "content required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_action_draft_not_found(client, db):
    """Acting on a nonexistent draft returns 404."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    fake_id = uuid.uuid4()
    resp = await client.post(
        f"{BASE}/drafts/{fake_id}",
        json={"action": "approve"},
        headers=_auth(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_action_draft_invalid_action(client, db):
    """An invalid action value returns 422 (validation error)."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    post_id = await _insert_marketing_post(
        db, platform="bluesky", content="Invalid action test",
        status="human_review",
    )

    resp = await client.post(
        f"{BASE}/drafts/{post_id}",
        json={"action": "invalid_action"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


# ---- Digest ----


@pytest.mark.asyncio
async def test_digest_returns_structure(client, db):
    """Digest endpoint returns expected weekly digest fields."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    # Mock the failure summary and Reddit scout to avoid external deps
    with patch(
        "src.marketing.alerts.get_failure_summary",
        new_callable=AsyncMock,
        return_value={
            "total_failed": 0,
            "total_permanently_failed": 0,
            "by_platform": {},
            "recent_errors": [],
        },
    ), patch(
        "src.marketing.reddit_scout.scan_subreddits",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "src.marketing.reddit_scout.get_cached_threads",
        new_callable=AsyncMock,
        return_value=[],
    ):
        resp = await client.get(f"{BASE}/digest", headers=_auth(token))

    assert resp.status_code == 200
    data = resp.json()
    assert "week_start" in data
    assert "week_end" in data
    assert "platforms" in data
    assert "total_posts" in data
    assert "cost_breakdown" in data
    assert "total_cost_usd" in data
    assert "top_posts" in data


@pytest.mark.asyncio
async def test_digest_send_success(client, db):
    """Sending digest email returns success when email sends."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    with patch(
        "src.marketing.digest.send_weekly_digest_email",
        new_callable=AsyncMock,
        return_value=True,
    ):
        resp = await client.post(
            f"{BASE}/digest/send", headers=_auth(token),
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"


@pytest.mark.asyncio
async def test_digest_send_failure(client, db):
    """Sending digest email returns 500 when email fails."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    with patch(
        "src.marketing.digest.send_weekly_digest_email",
        new_callable=AsyncMock,
        return_value=False,
    ):
        resp = await client.post(
            f"{BASE}/digest/send", headers=_auth(token),
        )

    assert resp.status_code == 500


# ---- Trigger ----


@pytest.mark.asyncio
async def test_trigger_marketing_tick(client, db):
    """Trigger endpoint calls run_marketing_tick and returns results."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    with patch(
        "src.marketing.orchestrator.run_marketing_tick",
        new_callable=AsyncMock,
        return_value={"status": "ok", "posts_created": 0},
    ):
        resp = await client.post(f"{BASE}/trigger", headers=_auth(token))

    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_trigger_platform_tick(client, db):
    """Trigger platform-specific endpoint returns result."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    with patch(
        "src.marketing.orchestrator.generate_and_post_for_platform",
        new_callable=AsyncMock,
        return_value={"status": "ok", "platform": "bluesky"},
    ):
        resp = await client.post(
            f"{BASE}/trigger/bluesky", headers=_auth(token),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["platform"] == "bluesky"


# ---- Activity ----


@pytest.mark.asyncio
async def test_activity_returns_structure(client, db):
    """Activity endpoint returns grouped post lists."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    resp = await client.get(f"{BASE}/activity", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "posted" in data
    assert "pending_review" in data
    assert "failed" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_activity_groups_by_status(client, db):
    """Activity groups posts by status correctly."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    now = datetime.now(timezone.utc)
    await _insert_marketing_post(
        db, platform="bluesky", content="Posted activity",
        status="posted", posted_at=now,
    )
    await _insert_marketing_post(
        db, platform="hackernews", content="Review activity",
        status="human_review",
    )
    await _insert_marketing_post(
        db, platform="reddit", content="Failed activity",
        status="failed",
    )

    resp = await client.get(f"{BASE}/activity", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 3
    assert len(data["posted"]) >= 1
    assert len(data["pending_review"]) >= 1
    assert len(data["failed"]) >= 1


@pytest.mark.asyncio
async def test_activity_limit_param(client, db):
    """Activity respects the limit query parameter."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    for i in range(5):
        await _insert_marketing_post(
            db, platform="bluesky", content=f"Limit test {i}",
            status="posted", posted_at=datetime.now(timezone.utc),
        )

    resp = await client.get(
        f"{BASE}/activity?limit=2", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] <= 2


# ---- Health ----


@pytest.mark.asyncio
async def test_health_returns_structure(client, db):
    """Health endpoint returns adapter status and cost info."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    # Mock all the external dependencies
    with patch(
        "src.marketing.llm.cost_tracker.get_daily_spend",
        new_callable=AsyncMock,
        return_value=0.02,
    ), patch(
        "src.marketing.llm.cost_tracker.get_monthly_spend",
        new_callable=AsyncMock,
        return_value=0.50,
    ), patch(
        "src.marketing.llm.ollama_client.is_available",
        new_callable=AsyncMock,
        return_value=False,
    ), patch(
        "src.marketing.alerts.get_failure_summary",
        new_callable=AsyncMock,
        return_value={
            "total_failed": 0,
            "total_permanently_failed": 0,
            "by_platform": {},
            "recent_errors": [],
        },
    ):
        # Mock each adapter's is_configured and health_check
        with patch(
            "src.marketing.adapters.twitter.TwitterAdapter.is_configured",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "src.marketing.adapters.reddit.RedditAdapter.is_configured",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "src.marketing.adapters.bluesky.BlueskyAdapter.is_configured",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "src.marketing.adapters.discord_bot.DiscordAdapter.is_configured",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "src.marketing.adapters.linkedin.LinkedInAdapter.is_configured",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "src.marketing.adapters.telegram_bot.TelegramAdapter.is_configured",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "src.marketing.adapters.devto.DevtoAdapter.is_configured",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "src.marketing.adapters.hashnode.HashnodeAdapter.is_configured",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "src.marketing.adapters.github_discussions.GitHubDiscussionsAdapter.is_configured",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "src.marketing.adapters.huggingface.HuggingFaceAdapter.is_configured",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "src.marketing.adapters.hackernews.HackerNewsAdapter.is_configured",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = await client.get(
                f"{BASE}/health", headers=_auth(token),
            )

    assert resp.status_code == 200
    data = resp.json()
    assert "marketing_enabled" in data
    assert "ollama_available" in data
    assert "anthropic_configured" in data
    assert "adapters" in data
    assert "failures_24h" in data
    assert isinstance(data["adapters"], dict)


# ---- Conversions ----


@pytest.mark.asyncio
async def test_conversions_returns_structure(client, db):
    """Conversions endpoint returns expected fields."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    resp = await client.get(f"{BASE}/conversions", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "platforms" in data
    assert "total_clicks" in data
    assert "total_signups" in data
    assert "total_cost_usd" in data
    assert isinstance(data["platforms"], list)


@pytest.mark.asyncio
async def test_conversions_with_days_param(client, db):
    """Conversions endpoint accepts days query param."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    resp = await client.get(
        f"{BASE}/conversions?days=7", headers=_auth(token),
    )
    assert resp.status_code == 200


# ---- Recap ----


@pytest.mark.asyncio
async def test_recap_trigger(client, db):
    """Recap endpoint calls trigger_recap and returns result."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    with patch(
        "src.marketing.recap.trigger_recap",
        new_callable=AsyncMock,
        return_value={"status": "ok", "post_id": str(uuid.uuid4())},
    ):
        resp = await client.post(f"{BASE}/recap", headers=_auth(token))

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---- Reddit Scout ----


@pytest.mark.asyncio
async def test_reddit_threads(client, db):
    """Reddit threads endpoint returns list (mocked)."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    with patch(
        "src.marketing.reddit_scout.scan_subreddits",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "src.marketing.reddit_scout.get_cached_threads",
        new_callable=AsyncMock,
        return_value=[],
    ):
        resp = await client.get(
            f"{BASE}/reddit/threads", headers=_auth(token),
        )

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_reddit_generate_draft_bad_url(client, db):
    """Reddit generate-draft returns 400 when thread can't be fetched."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    with patch(
        "src.marketing.reddit_scout.fetch_thread_detail",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.post(
            f"{BASE}/reddit/generate-draft",
            json={"thread_url": "https://reddit.com/r/test/comments/abc"},
            headers=_auth(token),
        )

    assert resp.status_code == 400
    assert "Could not fetch thread" in resp.json()["detail"]


# ---- HuggingFace Scout ----


@pytest.mark.asyncio
async def test_hf_discussions_returns_list(client, db):
    """HuggingFace discussions endpoint returns a list."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    with patch(
        "src.redis_client.get_redis",
        side_effect=Exception("no redis"),
    ), patch(
        "src.marketing.hf_scout.scan_hf_discussions",
        new_callable=AsyncMock,
        return_value=[],
    ):
        resp = await client.get(
            f"{BASE}/huggingface/discussions?refresh=true",
            headers=_auth(token),
        )

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_hf_generate_draft_llm_failure(client, db):
    """HF generate-draft returns 500 when LLM fails."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    mock_result = AsyncMock()
    mock_result.error = "LLM unavailable"
    mock_result.text = ""
    mock_result.model = None
    mock_result.tokens_in = 0
    mock_result.tokens_out = 0

    with patch(
        "src.marketing.llm.router.generate",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        resp = await client.post(
            f"{BASE}/huggingface/generate-draft",
            json={
                "repo_id": "meta-llama/Llama-3.3-70B",
                "discussion_num": 42,
                "discussion_title": "Test discussion",
            },
            headers=_auth(token),
        )

    assert resp.status_code == 500
    assert "LLM generation failed" in resp.json()["detail"]
