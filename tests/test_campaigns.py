"""Tests for the campaign planning admin router endpoints."""
from __future__ import annotations

import json
import uuid
from datetime import date
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
BASE = "/api/v1/admin/marketing/campaigns"

ADMIN_USER = {
    "email": "camp_admin@example.com",
    "password": "Str0ngP@ss!1",
    "display_name": "CampAdmin",
}

NORMAL_USER = {
    "email": "camp_normal@example.com",
    "password": "Str0ngP@ss!2",
    "display_name": "CampNormal",
}


async def _setup_admin(client: AsyncClient, db) -> str:
    """Register a user, promote to admin, return auth token."""
    await client.post(REGISTER_URL, json=ADMIN_USER)
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


async def _insert_campaign(
    db,
    *,
    campaign_id: uuid.UUID | None = None,
    name: str = "Weekly plan — test",
    topic: str = "weekly_campaign",
    platforms: list[str] | None = None,
    status: str = "proposed",
    schedule_config: dict | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> uuid.UUID:
    """Insert a marketing campaign directly into DB, return its ID."""
    cid = campaign_id or uuid.uuid4()
    plat = platforms or ["bluesky", "reddit"]
    config = schedule_config or {
        "strategy_summary": "Test strategy",
        "posts": [
            {
                "platform": "bluesky",
                "topic": "security",
                "angle": "test angle",
                "content_brief": "Test bluesky post content",
                "day": "monday",
                "value_type": "pure_value",
                "why": "testing",
            },
            {
                "platform": "reddit",
                "topic": "tutorials",
                "angle": "reddit angle",
                "content_brief": "Test reddit post content",
                "day": "wednesday",
                "value_type": "soft_mention",
                "why": "testing reddit",
            },
        ],
        "news_hooks": [],
        "avoid_this_week": [],
        "budget_estimate_usd": 0.10,
    }
    sd = start_date or date.today()
    ed = end_date or date.today()

    # Use text() to avoid needing the ORM model in test context
    await db.execute(text(
        "INSERT INTO marketing_campaigns "
        "(id, name, topic, platforms, status, schedule_config, "
        " start_date, end_date, created_at, updated_at) "
        "VALUES (:id, :name, :topic, :platforms, :status, :config, "
        " :start_date, :end_date, now(), now())"
    ), {
        "id": cid,
        "name": name,
        "topic": topic,
        "platforms": plat,
        "status": status,
        "config": json.dumps(config),
        "start_date": sd,
        "end_date": ed,
    })
    await db.flush()
    return cid


# ---- 403 for non-admin users ----


@pytest.mark.asyncio
async def test_proposed_requires_admin(client, db):
    """GET /proposed returns 403 for non-admin users."""
    token = await _setup_normal_user(client)
    resp = await client.get(f"{BASE}/proposed", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_generate_requires_admin(client, db):
    """POST /generate returns 403 for non-admin users."""
    token = await _setup_normal_user(client)
    resp = await client.post(f"{BASE}/generate", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_approve_requires_admin(client, db):
    """POST /{id}/approve returns 403 for non-admin users."""
    token = await _setup_normal_user(client)
    fake_id = uuid.uuid4()
    resp = await client.post(
        f"{BASE}/{fake_id}/approve", headers=_auth(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reject_requires_admin(client, db):
    """POST /{id}/reject returns 403 for non-admin users."""
    token = await _setup_normal_user(client)
    fake_id = uuid.uuid4()
    resp = await client.post(
        f"{BASE}/{fake_id}/reject",
        json={"feedback": "no"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_campaign_requires_admin(client, db):
    """GET /{id} returns 403 for non-admin users."""
    token = await _setup_normal_user(client)
    fake_id = uuid.uuid4()
    resp = await client.get(
        f"{BASE}/{fake_id}", headers=_auth(token),
    )
    assert resp.status_code == 403


# ---- 401 without auth ----


@pytest.mark.asyncio
async def test_proposed_requires_auth(client):
    """GET /proposed returns 401 without auth."""
    resp = await client.get(f"{BASE}/proposed")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_generate_requires_auth(client):
    """POST /generate returns 401 without auth."""
    resp = await client.post(f"{BASE}/generate")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_approve_requires_auth(client):
    """POST /{id}/approve returns 401 without auth."""
    resp = await client.post(f"{BASE}/{uuid.uuid4()}/approve")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_reject_requires_auth(client):
    """POST /{id}/reject returns 401 without auth."""
    resp = await client.post(
        f"{BASE}/{uuid.uuid4()}/reject",
        json={"feedback": "no"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_campaign_requires_auth(client):
    """GET /{id} returns 401 without auth."""
    resp = await client.get(f"{BASE}/{uuid.uuid4()}")
    assert resp.status_code == 401


# ---- GET /proposed ----


@pytest.mark.asyncio
async def test_proposed_empty(client, db):
    """GET /proposed returns empty list when no campaigns exist."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    resp = await client.get(f"{BASE}/proposed", headers=_auth(token))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_proposed_returns_proposed_campaigns(client, db):
    """GET /proposed returns only campaigns with status='proposed'."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    cid = await _insert_campaign(db, status="proposed", name="Proposed camp")
    await _insert_campaign(db, status="active", name="Active camp")
    await _insert_campaign(db, status="rejected", name="Rejected camp")

    resp = await client.get(f"{BASE}/proposed", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    ids = [c["id"] for c in data]
    assert str(cid) in ids
    # All returned campaigns should have status 'proposed'
    for c in data:
        assert c["status"] == "proposed"


@pytest.mark.asyncio
async def test_proposed_response_shape(client, db):
    """GET /proposed items have expected keys."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    await _insert_campaign(db, status="proposed")

    resp = await client.get(f"{BASE}/proposed", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    item = data[0]
    assert "id" in item
    assert "name" in item
    assert "topic" in item
    assert "platforms" in item
    assert "status" in item
    assert "start_date" in item
    assert "created_at" in item


# ---- POST /generate ----


@pytest.mark.asyncio
async def test_generate_success(client, db):
    """POST /generate creates a campaign plan via mocked LLM."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    plan = {
        "strategy_summary": "Test strategy for the week",
        "posts": [
            {
                "platform": "bluesky",
                "topic": "security",
                "angle": "test angle",
                "content_brief": "Bluesky content",
                "day": "monday",
                "value_type": "pure_value",
                "why": "testing",
            },
        ],
        "news_hooks": [],
        "avoid_this_week": [],
        "budget_estimate_usd": 0.05,
    }

    mock_resp = AsyncMock()
    mock_resp.error = None
    mock_resp.text = json.dumps(plan)
    mock_resp.model = "claude-opus"
    mock_resp.tokens_in = 100
    mock_resp.tokens_out = 200

    with patch(
        "src.marketing.llm.anthropic_client.generate",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ), patch(
        "src.marketing.campaign_planner.gather_news_signals",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "src.marketing.campaign_planner._configured_platforms",
        new_callable=AsyncMock,
        return_value=["bluesky"],
    ), patch(
        "src.marketing.campaign_planner.send_campaign_proposal_email",
        new_callable=AsyncMock,
        return_value=True,
    ):
        resp = await client.post(
            f"{BASE}/generate", headers=_auth(token),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "campaign_id" in data
    assert "strategy_summary" in data
    assert "posts" in data


@pytest.mark.asyncio
async def test_generate_llm_error_returns_502(client, db):
    """POST /generate returns 502 when LLM fails."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    mock_resp = AsyncMock()
    mock_resp.error = "API rate limited"
    mock_resp.text = ""

    with patch(
        "src.marketing.llm.anthropic_client.generate",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ), patch(
        "src.marketing.campaign_planner.gather_news_signals",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "src.marketing.campaign_planner._configured_platforms",
        new_callable=AsyncMock,
        return_value=["bluesky"],
    ):
        resp = await client.post(
            f"{BASE}/generate", headers=_auth(token),
        )

    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_generate_json_parse_failure_returns_502(client, db):
    """POST /generate returns 502 when LLM output is not valid JSON."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    mock_resp = AsyncMock()
    mock_resp.error = None
    mock_resp.text = "This is not JSON at all, just plain text"

    with patch(
        "src.marketing.llm.anthropic_client.generate",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ), patch(
        "src.marketing.campaign_planner.gather_news_signals",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "src.marketing.campaign_planner._configured_platforms",
        new_callable=AsyncMock,
        return_value=["bluesky"],
    ):
        resp = await client.post(
            f"{BASE}/generate", headers=_auth(token),
        )

    assert resp.status_code == 502


# ---- POST /{id}/approve ----


@pytest.mark.asyncio
async def test_approve_campaign_success(client, db):
    """POST /{id}/approve moves campaign to active and creates posts."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    cid = await _insert_campaign(db, status="proposed")

    resp = await client.post(
        f"{BASE}/{cid}/approve",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["campaign_id"] == str(cid)
    assert data["status"] == "active"
    assert "approved_posts" in data
    assert isinstance(data["approved_posts"], list)
    assert len(data["approved_posts"]) >= 1


@pytest.mark.asyncio
async def test_approve_campaign_with_subset(client, db):
    """POST /{id}/approve with approved_post_indices only approves those."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    cid = await _insert_campaign(db, status="proposed")

    resp = await client.post(
        f"{BASE}/{cid}/approve",
        json={"approved_post_indices": [0]},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    # Only 1 post should be approved (index 0)
    assert len(data["approved_posts"]) == 1


@pytest.mark.asyncio
async def test_approve_campaign_not_found(client, db):
    """POST /{id}/approve returns 404 for nonexistent campaign."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    fake_id = uuid.uuid4()
    resp = await client.post(
        f"{BASE}/{fake_id}/approve",
        headers=_auth(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_non_proposed_campaign_returns_404(client, db):
    """POST /{id}/approve returns 404 for campaign not in 'proposed' status."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    cid = await _insert_campaign(db, status="active")

    resp = await client.post(
        f"{BASE}/{cid}/approve",
        headers=_auth(token),
    )
    assert resp.status_code == 404


# ---- POST /{id}/reject ----


@pytest.mark.asyncio
async def test_reject_campaign_success(client, db):
    """POST /{id}/reject moves campaign to rejected with feedback."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    cid = await _insert_campaign(db, status="proposed")

    resp = await client.post(
        f"{BASE}/{cid}/reject",
        json={"feedback": "Too aggressive on Reddit"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["campaign_id"] == str(cid)
    assert data["status"] == "rejected"
    assert data["feedback"] == "Too aggressive on Reddit"


@pytest.mark.asyncio
async def test_reject_campaign_not_found(client, db):
    """POST /{id}/reject returns 404 for nonexistent campaign."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    fake_id = uuid.uuid4()
    resp = await client.post(
        f"{BASE}/{fake_id}/reject",
        json={"feedback": "nope"},
        headers=_auth(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reject_non_proposed_campaign_returns_404(client, db):
    """POST /{id}/reject returns 404 for campaign not in 'proposed' status."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    cid = await _insert_campaign(db, status="active")

    resp = await client.post(
        f"{BASE}/{cid}/reject",
        json={"feedback": "Already active, cannot reject"},
        headers=_auth(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reject_requires_feedback_body(client, db):
    """POST /{id}/reject returns 422 when feedback field is missing."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    cid = await _insert_campaign(db, status="proposed")

    resp = await client.post(
        f"{BASE}/{cid}/reject",
        json={},
        headers=_auth(token),
    )
    assert resp.status_code == 422


# ---- GET /{id} ----


@pytest.mark.asyncio
async def test_get_campaign_detail(client, db):
    """GET /{id} returns campaign details with expected shape."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    cid = await _insert_campaign(db, status="proposed", name="Detail test")

    resp = await client.get(
        f"{BASE}/{cid}", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(cid)
    assert data["name"] == "Detail test"
    assert data["status"] == "proposed"
    assert "topic" in data
    assert "platforms" in data
    assert "schedule_config" in data
    assert "start_date" in data
    assert "end_date" in data
    assert "created_at" in data
    assert "posts" in data
    assert isinstance(data["posts"], list)


@pytest.mark.asyncio
async def test_get_campaign_not_found(client, db):
    """GET /{id} returns 404 for nonexistent campaign."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    fake_id = uuid.uuid4()
    resp = await client.get(
        f"{BASE}/{fake_id}", headers=_auth(token),
    )
    assert resp.status_code == 404
    assert "Campaign not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_campaign_includes_posts_after_approve(client, db):
    """GET /{id} includes posts created by approve."""
    await _ensure_marketing_tables(db)
    token = await _setup_admin(client, db)

    cid = await _insert_campaign(db, status="proposed")

    # Approve the campaign first to create posts
    approve_resp = await client.post(
        f"{BASE}/{cid}/approve",
        headers=_auth(token),
    )
    assert approve_resp.status_code == 200

    # Now fetch the detail
    resp = await client.get(
        f"{BASE}/{cid}", headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert len(data["posts"]) >= 1
    # Each post should have expected fields
    post = data["posts"][0]
    assert "id" in post
    assert "platform" in post
    assert "topic" in post
    assert "status" in post
    assert "content" in post
