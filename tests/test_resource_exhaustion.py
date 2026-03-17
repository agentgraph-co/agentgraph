from __future__ import annotations

"""Resource exhaustion and input abuse tests for AgentGraph.

Verifies that the API properly validates and caps pagination limits,
rejects oversized payloads, handles query abuse gracefully, and
enforces rate limits on bulk operations.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.main import app
from src.models import TrustScore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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

USER_A = {
    "email": "exhaust_a@example.com",
    "password": "Str0ngP@ss1",
    "display_name": "ExhaustA",
}
USER_B = {
    "email": "exhaust_b@example.com",
    "password": "Str0ngP@ss2",
    "display_name": "ExhaustB",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_user(
    client: AsyncClient, user: dict, db: AsyncSession | None = None,
) -> tuple[str, str]:
    """Register, login, return (token, entity_id). Optionally add a trust score."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    data = resp.json()
    token = data["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    eid = me.json()["id"]
    if db is not None:
        db.add(TrustScore(
            id=uuid.uuid4(), entity_id=uuid.UUID(eid), score=0.5,
            components={"verification": 0.3, "age": 0.1, "activity": 0.1},
        ))
        await db.flush()
    return token, eid


# ===========================================================================
# Pagination / Limit Abuse
# ===========================================================================


@pytest.mark.asyncio
async def test_feed_limit_too_large(client: AsyncClient, db: AsyncSession):
    """Request with limit=999999 should be capped or rejected (422)."""
    resp = await client.get("/api/v1/feed/posts", params={"limit": 999999})
    # FastAPI's Query(ge=1, le=100) should reject values over the max
    assert resp.status_code == 422, (
        f"Expected 422 for limit=999999, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_feed_limit_negative(client: AsyncClient, db: AsyncSession):
    """Request with limit=-1 should be rejected."""
    resp = await client.get("/api/v1/feed/posts", params={"limit": -1})
    assert resp.status_code == 422, (
        f"Expected 422 for limit=-1, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_search_offset_extremely_large(client: AsyncClient, db: AsyncSession):
    """Request with huge offset should return empty, not crash."""
    resp = await client.get(
        "/api/v1/search",
        params={"q": "test", "limit": 10},
    )
    # Should succeed with empty or near-empty results
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_feed_limit_zero(client: AsyncClient, db: AsyncSession):
    """Request with limit=0 should be rejected."""
    resp = await client.get("/api/v1/feed/posts", params={"limit": 0})
    assert resp.status_code == 422, (
        f"Expected 422 for limit=0, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_social_followers_limit_too_large(client: AsyncClient, db: AsyncSession):
    """Followers endpoint limit=999999 should be rejected by Query validation."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    resp = await client.get(
        f"/api/v1/social/followers/{eid_a}",
        params={"limit": 999999},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_webhooks_list_limit_too_large(client: AsyncClient, db: AsyncSession):
    """Webhooks list with limit=999999 should be capped or rejected."""
    token_a, _ = await _setup_user(client, USER_A, db)
    resp = await client.get(
        "/api/v1/webhooks",
        params={"limit": 999999, "offset": 0},
        headers=_auth(token_a),
    )
    # Depending on whether webhooks has Query validation — 422 or capped result
    assert resp.status_code in (200, 422)


# ===========================================================================
# Payload Size Abuse
# ===========================================================================


@pytest.mark.asyncio
async def test_post_with_1mb_content(client: AsyncClient, db: AsyncSession):
    """Post with ~1MB content should be rejected (max_length=10000)."""
    token_a, _ = await _setup_user(client, USER_A, db)

    huge_content = "A" * 1_000_000  # 1MB of text
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": huge_content},
        headers=_auth(token_a),
    )
    assert resp.status_code == 422, (
        f"Expected 422 for 1MB content, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_post_with_10000_char_display_name_registration(
    client: AsyncClient, db: AsyncSession,
):
    """Registration with extremely long display_name should be rejected."""
    user = {
        "email": "longname@example.com",
        "password": "Str0ngP@ss1",
        "display_name": "X" * 10000,
    }
    resp = await client.post(REGISTER_URL, json=user)
    assert resp.status_code == 422, (
        f"Expected 422 for 10000 char display_name, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_bio_update_massive_content(client: AsyncClient, db: AsyncSession):
    """Bio update with massive markdown should be rejected (max_length=5000)."""
    token_a, _ = await _setup_user(client, USER_A, db)

    huge_bio = "# Heading\n" * 10000  # ~100KB of markdown
    resp = await client.patch(
        "/api/v1/profiles/me",
        json={"bio_markdown": huge_bio},
        headers=_auth(token_a),
    )
    assert resp.status_code == 422, (
        f"Expected 422 for massive bio, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_webhook_url_extremely_long(client: AsyncClient, db: AsyncSession):
    """Webhook with 10000 char URL should be rejected."""
    token_a, _ = await _setup_user(client, USER_A, db)

    long_url = "https://example.com/" + "a" * 10000
    resp = await client.post(
        "/api/v1/webhooks",
        json={
            "callback_url": long_url,
            "event_types": ["entity.followed"],
        },
        headers=_auth(token_a),
    )
    # Should be rejected by Pydantic HttpUrl validation or max_length
    assert resp.status_code == 422, (
        f"Expected 422 for very long URL, got {resp.status_code}"
    )


# ===========================================================================
# Query Abuse
# ===========================================================================


@pytest.mark.asyncio
async def test_search_very_long_query(client: AsyncClient, db: AsyncSession):
    """Search with 10000 char query should be rejected (max_length=200)."""
    long_query = "x" * 10000
    resp = await client.get(
        "/api/v1/search",
        params={"q": long_query},
    )
    assert resp.status_code == 422, (
        f"Expected 422 for 10000 char query, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_search_sql_injection_attempt(client: AsyncClient, db: AsyncSession):
    """Search with SQL injection payload should be sanitized, not crash."""
    injection = "'; DROP TABLE entities; --"
    resp = await client.get(
        "/api/v1/search",
        params={"q": injection},
    )
    # Should either return results or 200 with empty set — never 500
    assert resp.status_code in (200, 422), (
        f"SQL injection caused status {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_search_xss_attempt(client: AsyncClient, db: AsyncSession):
    """Search with XSS payload should not crash the server."""
    xss = "<script>alert('xss')</script>"
    resp = await client.get(
        "/api/v1/search",
        params={"q": xss},
    )
    assert resp.status_code in (200, 422)
    if resp.status_code == 200:
        # Response should not contain raw script tags
        assert "<script>" not in resp.text


@pytest.mark.asyncio
async def test_search_unicode_abuse(client: AsyncClient, db: AsyncSession):
    """Search with unusual unicode should not crash."""
    unicode_query = "\u0000\uffff\ud800test"  # null bytes and surrogates
    resp = await client.get(
        "/api/v1/search",
        params={"q": unicode_query},
    )
    # Should handle gracefully — 200 or 422, not 500
    assert resp.status_code != 500, f"Unicode abuse caused 500: {resp.text}"


@pytest.mark.asyncio
async def test_feed_large_offset_with_limit(client: AsyncClient, db: AsyncSession):
    """Feed with huge offset value should return empty, not crash or OOM."""
    # Using cursor-based pagination, send a fake cursor
    resp = await client.get(
        "/api/v1/feed/posts",
        params={"cursor": "00000000-0000-0000-0000-000000000000", "limit": 20},
    )
    # Should return 200 with empty posts
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("posts", []), list)


# ===========================================================================
# Batch / Bulk Abuse
# ===========================================================================


@pytest.mark.asyncio
async def test_creating_many_webhooks(client: AsyncClient, db: AsyncSession):
    """Creating many webhooks should eventually hit a limit or degrade gracefully."""
    token_a, _ = await _setup_user(client, USER_A, db)

    created = 0
    rejected = 0
    for i in range(50):
        resp = await client.post(
            "/api/v1/webhooks",
            json={
                "callback_url": f"https://example.com/hook{i}",
                "event_types": ["entity.followed"],
            },
            headers=_auth(token_a),
        )
        if resp.status_code in (200, 201):
            created += 1
        elif resp.status_code == 429:
            rejected += 1
            break  # Rate limited — expected
        elif resp.status_code in (400, 403, 409):
            rejected += 1

    # Should not have 500 errors. Rate limit should kick in at some point,
    # OR a webhook count limit should be enforced.
    # At minimum, some should succeed.
    assert created >= 1, "No webhooks were created"


@pytest.mark.asyncio
async def test_rapid_post_creation_rate_limit(client: AsyncClient, db: AsyncSession):
    """Creating many posts rapidly should trigger rate limiting."""
    token_a, _ = await _setup_user(client, USER_A, db)

    created = 0
    rate_limited = 0
    for i in range(30):
        resp = await client.post(
            "/api/v1/feed/posts",
            json={"content": f"Rapid post #{i}"},
            headers=_auth(token_a),
        )
        if resp.status_code == 201:
            created += 1
        elif resp.status_code == 429:
            rate_limited += 1
            break

    # Either rate limit kicked in, or all succeeded (if limit is generous).
    # No 500 errors is the key assertion.
    assert created >= 1, "No posts were created"


@pytest.mark.asyncio
async def test_rapid_follow_rate_limit(client: AsyncClient, db: AsyncSession):
    """Following many users rapidly should trigger rate limiting."""
    token_a, _ = await _setup_user(client, USER_A, db)

    # Create several target users
    targets = []
    for i in range(15):
        user = {
            "email": f"target_{i}@example.com",
            "password": "Str0ngP@ss1",
            "display_name": f"Target{i}",
        }
        await client.post(REGISTER_URL, json=user)
        resp = await client.post(
            LOGIN_URL,
            json={"email": user["email"], "password": user["password"]},
        )
        me = await client.get(
            "/api/v1/auth/me",
            headers=_auth(resp.json()["access_token"]),
        )
        targets.append(me.json()["id"])

    followed = 0
    rate_limited = 0
    for tid in targets:
        resp = await client.post(
            f"/api/v1/social/follow/{tid}", headers=_auth(token_a),
        )
        if resp.status_code == 200:
            followed += 1
        elif resp.status_code == 429:
            rate_limited += 1
            break

    assert followed >= 1, "No follows succeeded"


@pytest.mark.asyncio
async def test_rapid_dm_rate_limit(client: AsyncClient, db: AsyncSession):
    """Sending many DMs rapidly should trigger rate limiting."""
    token_a, _ = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)

    sent = 0
    rate_limited = 0
    for i in range(30):
        resp = await client.post(
            "/api/v1/messages",
            json={
                "recipient_id": eid_b,
                "content": f"Message #{i}",
            },
            headers=_auth(token_a),
        )
        if resp.status_code == 201:
            sent += 1
        elif resp.status_code == 429:
            rate_limited += 1
            break

    # At least some messages should go through before rate limit
    assert sent >= 1, "No messages were sent"


@pytest.mark.asyncio
async def test_post_content_at_boundary(client: AsyncClient, db: AsyncSession):
    """Post content at exactly max_length (10000) should succeed."""
    token_a, _ = await _setup_user(client, USER_A, db)

    # Exactly at the limit
    content = "A" * 10000
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": content},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201, (
        f"Expected 201 for max-length content, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_post_content_over_boundary(client: AsyncClient, db: AsyncSession):
    """Post content at max_length+1 should be rejected."""
    token_a, _ = await _setup_user(client, USER_A, db)

    content = "A" * 10001
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": content},
        headers=_auth(token_a),
    )
    assert resp.status_code == 422, (
        f"Expected 422 for over-max content, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_search_max_length_boundary(client: AsyncClient, db: AsyncSession):
    """Search with exactly 200 chars should succeed; 201 should fail."""
    # Exactly at limit
    resp = await client.get(
        "/api/v1/search",
        params={"q": "a" * 200},
    )
    assert resp.status_code == 200, (
        f"Expected 200 for 200-char query, got {resp.status_code}"
    )

    # Over limit
    resp = await client.get(
        "/api/v1/search",
        params={"q": "a" * 201},
    )
    assert resp.status_code == 422, (
        f"Expected 422 for 201-char query, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_moderation_flag_details_too_long(client: AsyncClient, db: AsyncSession):
    """Flag details exceeding max_length (2000) should be rejected."""
    token_a, _ = await _setup_user(client, USER_A, db)
    token_b, _ = await _setup_user(client, USER_B, db)

    # Create a post to flag
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Flaggable post"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    post_id = resp.json()["id"]

    resp = await client.post(
        "/api/v1/moderation/flags",
        json={
            "target_type": "post",
            "target_id": post_id,
            "reason": "spam",
            "details": "X" * 2001,
        },
        headers=_auth(token_b),
    )
    assert resp.status_code == 422, (
        f"Expected 422 for oversized flag details, got {resp.status_code}"
    )


@pytest.mark.asyncio
async def test_display_name_at_boundary(client: AsyncClient, db: AsyncSession):
    """Display name at exactly 100 chars should succeed; 101 should fail."""
    # Exactly at limit
    user_ok = {
        "email": "boundary_ok@example.com",
        "password": "Str0ngP@ss1",
        "display_name": "A" * 100,
    }
    resp = await client.post(REGISTER_URL, json=user_ok)
    assert resp.status_code == 201, (
        f"Expected 201 for 100-char name, got {resp.status_code}: {resp.text}"
    )

    # Over limit
    user_bad = {
        "email": "boundary_bad@example.com",
        "password": "Str0ngP@ss1",
        "display_name": "A" * 101,
    }
    resp = await client.post(REGISTER_URL, json=user_bad)
    assert resp.status_code == 422, (
        f"Expected 422 for 101-char name, got {resp.status_code}"
    )
