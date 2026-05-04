from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import Entity, EntityType, FrameworkSecurityScan, TrustScoreHistory


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


HISTORY_URL = "/api/v1/public/scan/{owner}/{repo}/history"


async def _make_entity(db, owner: str, repo: str) -> Entity:
    suffix = uuid.uuid4().hex[:8]
    entity = Entity(
        type=EntityType.AGENT,
        display_name=f"{owner}-{repo}-{suffix}",
        did_web=f"did:web:test-{suffix}",
        source_url=f"https://github.com/{owner}/{repo}",
        source_type="github",
        is_active=True,
    )
    db.add(entity)
    await db.flush()
    return entity


@pytest.mark.asyncio
async def test_history_unknown_repo_returns_empty(client):
    """Unknown repo returns 200 with empty arrays — never a 404."""
    resp = await client.get(
        HISTORY_URL.format(owner="never", repo=f"exists-{uuid.uuid4().hex[:6]}")
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["entity_id"] is None
    assert body["score_timeline"] == []
    assert body["framework_scans"] == []
    assert body["repo"].startswith("never/exists-")


@pytest.mark.asyncio
async def test_history_returns_populated_timeline(client, db):
    """Seeded entity with trust history + framework scans returns ordered rows."""
    owner = "agentgraph-co"
    repo = f"history-{uuid.uuid4().hex[:6]}"
    entity = await _make_entity(db, owner, repo)

    base = datetime.now(timezone.utc) - timedelta(days=3)
    db.add_all([
        TrustScoreHistory(entity_id=entity.id, score=0.62, recorded_at=base),
        TrustScoreHistory(
            entity_id=entity.id, score=0.74, recorded_at=base + timedelta(days=1)
        ),
        TrustScoreHistory(
            entity_id=entity.id, score=0.81, recorded_at=base + timedelta(days=2)
        ),
    ])
    db.add_all([
        FrameworkSecurityScan(
            entity_id=entity.id,
            framework="mcp",
            scan_result="clean",
            vulnerabilities=[],
            scanned_at=base + timedelta(hours=1),
        ),
        FrameworkSecurityScan(
            entity_id=entity.id,
            framework="openclaw",
            scan_result="warnings",
            vulnerabilities=[{"id": "OC-1"}, {"id": "OC-2"}],
            scanned_at=base + timedelta(days=1, hours=1),
        ),
    ])
    await db.flush()

    # Bypass cache to ensure DB path runs (avoids cross-test cache hits if Redis is up).
    from src import cache
    await cache.invalidate(f"public_scan_history:{owner}/{repo}")

    resp = await client.get(HISTORY_URL.format(owner=owner, repo=repo))
    assert resp.status_code == 200
    body = resp.json()

    assert body["entity_id"] == str(entity.id)
    assert body["repo"] == f"{owner}/{repo}"

    timeline = body["score_timeline"]
    assert len(timeline) == 3
    assert [p["score"] for p in timeline] == [62, 74, 81]
    # Ordered ascending by recorded_at
    assert timeline[0]["recorded_at"] <= timeline[1]["recorded_at"] <= timeline[2]["recorded_at"]

    scans = body["framework_scans"]
    assert len(scans) == 2
    assert scans[0]["framework"] == "mcp"
    assert scans[0]["scan_result"] == "clean"
    assert scans[0]["vulnerabilities_count"] == 0
    assert scans[1]["framework"] == "openclaw"
    assert scans[1]["scan_result"] == "warnings"
    assert scans[1]["vulnerabilities_count"] == 2

    assert body.get("jws"), "expected a signed JWS attestation"


@pytest.mark.asyncio
async def test_history_is_rate_limited(client):
    """The endpoint is wired to rate_limit_history_reads (tighter than
    generic /reads since each call does live-fetch + JWS sign). Hammer
    it past the configured limit and expect a 429."""
    from src.api.rate_limit import _limiter
    from src.config import settings

    # Tighten the limit just for this test and clear any inherited counters.
    original = settings.rate_limit_history_reads_per_minute
    settings.rate_limit_history_reads_per_minute = 3
    await _limiter.clear_all()
    try:
        url = HISTORY_URL.format(owner="rl", repo=f"check-{uuid.uuid4().hex[:6]}")
        statuses = []
        for _ in range(8):
            r = await client.get(url)
            statuses.append(r.status_code)
        assert 429 in statuses, f"expected a 429 in {statuses}"
    finally:
        settings.rate_limit_history_reads_per_minute = original
        await _limiter.clear_all()
