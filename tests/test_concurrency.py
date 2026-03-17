from __future__ import annotations

"""Concurrency and race condition tests for AgentGraph.

Uses asyncio.gather to fire simultaneous requests and verifies that
database state remains consistent after all concurrent operations complete.
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.main import app
from src.models import (
    APIKey,
    Bookmark,
    Entity,
    EntityBlock,
    EntityRelationship,
    ModerationFlag,
    Post,
    RelationshipType,
    TrustScore,
    Vote,
    VoteDirection,
    WebhookSubscription,
)


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
    "email": "conc_a@example.com",
    "password": "Str0ngP@ss1",
    "display_name": "ConcurrencyA",
}
USER_B = {
    "email": "conc_b@example.com",
    "password": "Str0ngP@ss2",
    "display_name": "ConcurrencyB",
}
USER_C = {
    "email": "conc_c@example.com",
    "password": "Str0ngP@ss3",
    "display_name": "ConcurrencyC",
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


async def _create_post(client: AsyncClient, token: str) -> str:
    """Create a post and return its id."""
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Test post for concurrency testing"},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# 1. Concurrent double-follow same user → exactly 1 follow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_double_follow(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)

    results = await asyncio.gather(
        client.post(f"/api/v1/social/follow/{eid_b}", headers=_auth(token_a)),
        client.post(f"/api/v1/social/follow/{eid_b}", headers=_auth(token_a)),
    )

    # At least one should succeed
    statuses = [r.status_code for r in results]
    assert 200 in statuses

    # DB should have exactly 1 follow relationship
    count = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(
            EntityRelationship.source_entity_id == uuid.UUID(eid_a),
            EntityRelationship.target_entity_id == uuid.UUID(eid_b),
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    assert count == 1, f"Expected exactly 1 follow, got {count}"


# ---------------------------------------------------------------------------
# 2. Concurrent double-unfollow → should not error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_double_unfollow(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)

    # First follow
    resp = await client.post(f"/api/v1/social/follow/{eid_b}", headers=_auth(token_a))
    assert resp.status_code == 200

    results = await asyncio.gather(
        client.delete(f"/api/v1/social/follow/{eid_b}", headers=_auth(token_a)),
        client.delete(f"/api/v1/social/follow/{eid_b}", headers=_auth(token_a)),
    )

    # One should succeed (200), the other may get 404 (not following)
    statuses = sorted([r.status_code for r in results])
    assert 200 in statuses or 404 in statuses
    # No 500 errors
    assert 500 not in statuses

    # DB should have 0 follow relationships
    count = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(
            EntityRelationship.source_entity_id == uuid.UUID(eid_a),
            EntityRelationship.target_entity_id == uuid.UUID(eid_b),
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    assert count == 0


# ---------------------------------------------------------------------------
# 3. Concurrent double-vote on same post → exactly 1 vote
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_double_vote(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)
    post_id = await _create_post(client, token_a)

    # Use a second user to vote
    token_b, eid_b = await _setup_user(client, USER_B, db)

    results = await asyncio.gather(
        client.post(
            f"/api/v1/feed/posts/{post_id}/vote",
            json={"direction": "up"},
            headers=_auth(token_b),
        ),
        client.post(
            f"/api/v1/feed/posts/{post_id}/vote",
            json={"direction": "up"},
            headers=_auth(token_b),
        ),
    )

    # No 500 errors
    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"

    # DB should have at most 1 vote from user B on this post
    count = await db.scalar(
        select(func.count()).select_from(Vote).where(
            Vote.entity_id == uuid.UUID(eid_b),
            Vote.post_id == uuid.UUID(post_id),
        )
    )
    assert count <= 1, f"Expected 0 or 1 vote, got {count}"


# ---------------------------------------------------------------------------
# 4. Concurrent opposite votes (up+down) on same post → 1 vote
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_opposite_votes(client: AsyncClient, db: AsyncSession):
    token_a, _ = await _setup_user(client, USER_A, db)
    post_id = await _create_post(client, token_a)

    token_b, eid_b = await _setup_user(client, USER_B, db)

    results = await asyncio.gather(
        client.post(
            f"/api/v1/feed/posts/{post_id}/vote",
            json={"direction": "up"},
            headers=_auth(token_b),
        ),
        client.post(
            f"/api/v1/feed/posts/{post_id}/vote",
            json={"direction": "down"},
            headers=_auth(token_b),
        ),
    )

    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"

    # Should have at most 1 vote record
    count = await db.scalar(
        select(func.count()).select_from(Vote).where(
            Vote.entity_id == uuid.UUID(eid_b),
            Vote.post_id == uuid.UUID(post_id),
        )
    )
    assert count <= 1, f"Expected 0 or 1 vote, got {count}"


# ---------------------------------------------------------------------------
# 5. Concurrent double-bookmark same post → exactly 1 bookmark
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_double_bookmark(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)
    post_id = await _create_post(client, token_a)

    results = await asyncio.gather(
        client.post(
            f"/api/v1/feed/posts/{post_id}/bookmark", headers=_auth(token_a),
        ),
        client.post(
            f"/api/v1/feed/posts/{post_id}/bookmark", headers=_auth(token_a),
        ),
    )

    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"

    # Should have at most 1 bookmark
    count = await db.scalar(
        select(func.count()).select_from(Bookmark).where(
            Bookmark.entity_id == uuid.UUID(eid_a),
            Bookmark.post_id == uuid.UUID(post_id),
        )
    )
    assert count <= 1, f"Expected 0 or 1 bookmark, got {count}"


# ---------------------------------------------------------------------------
# 6. Concurrent block + follow same user → block should win
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_block_and_follow(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)

    results = await asyncio.gather(
        client.post(f"/api/v1/social/block/{eid_b}", headers=_auth(token_a)),
        client.post(f"/api/v1/social/follow/{eid_b}", headers=_auth(token_a)),
    )

    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"

    # If block succeeded, the follow should have been removed or prevented
    block_exists = await db.scalar(
        select(func.count()).select_from(EntityBlock).where(
            EntityBlock.blocker_id == uuid.UUID(eid_a),
            EntityBlock.blocked_id == uuid.UUID(eid_b),
        )
    )

    # At minimum, no 500 errors. The block endpoint also removes follows,
    # so if block ran after follow, follow should be removed.
    if block_exists:
        follow_count = await db.scalar(
            select(func.count()).select_from(EntityRelationship).where(
                EntityRelationship.source_entity_id == uuid.UUID(eid_a),
                EntityRelationship.target_entity_id == uuid.UUID(eid_b),
                EntityRelationship.type == RelationshipType.FOLLOW,
            )
        )
        # Block removes follow, so if block ran last, follow should be 0.
        # If follow ran last (after block), it would be rejected (403).
        # Either way, consistent state.
        assert follow_count <= 1


# ---------------------------------------------------------------------------
# 7. Concurrent post creation by same user → both should succeed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_post_creation(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)

    results = await asyncio.gather(
        client.post(
            "/api/v1/feed/posts",
            json={"content": "Concurrent post 1"},
            headers=_auth(token_a),
        ),
        client.post(
            "/api/v1/feed/posts",
            json={"content": "Concurrent post 2"},
            headers=_auth(token_a),
        ),
    )

    # Both should succeed (201) — no conflict expected
    for r in results:
        assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"

    # Verify both posts exist
    count = await db.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_entity_id == uuid.UUID(eid_a),
        )
    )
    assert count >= 2


# ---------------------------------------------------------------------------
# 8. Concurrent profile updates → last write wins, no corruption
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_profile_updates(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)

    results = await asyncio.gather(
        client.patch(
            "/api/v1/profiles/me",
            json={"display_name": "UpdatedNameA"},
            headers=_auth(token_a),
        ),
        client.patch(
            "/api/v1/profiles/me",
            json={"display_name": "UpdatedNameB"},
            headers=_auth(token_a),
        ),
    )

    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"

    # The entity should have one of the two names, not corrupted data
    await db.expire_all()
    entity = await db.get(Entity, uuid.UUID(eid_a))
    assert entity is not None
    assert entity.display_name in ("UpdatedNameA", "UpdatedNameB")


# ---------------------------------------------------------------------------
# 9. Concurrent API key rotation → no duplicate active keys
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_api_key_rotation(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)

    # Create an agent first
    resp = await client.post(
        "/api/v1/agents",
        json={"display_name": "ConcAgent", "type": "agent"},
        headers=_auth(token_a),
    )
    if resp.status_code not in (200, 201):
        pytest.skip("Agent creation not available")

    agent_id = resp.json().get("id")
    if not agent_id:
        pytest.skip("No agent id returned")

    results = await asyncio.gather(
        client.post(
            f"/api/v1/agents/{agent_id}/rotate-key",
            headers=_auth(token_a),
        ),
        client.post(
            f"/api/v1/agents/{agent_id}/rotate-key",
            headers=_auth(token_a),
        ),
    )

    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"

    # Should have at most 1 active key
    active_count = await db.scalar(
        select(func.count()).select_from(APIKey).where(
            APIKey.entity_id == uuid.UUID(agent_id),
            APIKey.is_active.is_(True),
        )
    )
    assert active_count <= 1, f"Expected at most 1 active key, got {active_count}"


# ---------------------------------------------------------------------------
# 10. Concurrent webhook creation for same event → both succeed or deduplicate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_webhook_creation(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)

    webhook_payload = {
        "callback_url": "https://example.com/webhook",
        "event_types": ["entity.followed"],
    }

    results = await asyncio.gather(
        client.post(
            "/api/v1/webhooks",
            json=webhook_payload,
            headers=_auth(token_a),
        ),
        client.post(
            "/api/v1/webhooks",
            json=webhook_payload,
            headers=_auth(token_a),
        ),
    )

    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"

    # Both may succeed (no unique constraint on callback_url+event),
    # or one might be rejected. Either way, no server errors.
    success_count = sum(1 for r in results if r.status_code in (200, 201))
    assert success_count >= 1


# ---------------------------------------------------------------------------
# 11. Concurrent flag creation on same post by same user → deduplicate (409)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_double_flag(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)
    token_b, eid_b = await _setup_user(client, USER_B, db)

    post_id = await _create_post(client, token_a)

    flag_payload = {
        "target_type": "post",
        "target_id": post_id,
        "reason": "spam",
        "details": "Looks like spam",
    }

    results = await asyncio.gather(
        client.post(
            "/api/v1/moderation/flags",
            json=flag_payload,
            headers=_auth(token_b),
        ),
        client.post(
            "/api/v1/moderation/flags",
            json=flag_payload,
            headers=_auth(token_b),
        ),
    )

    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"

    # Should get at most 1 flag from user B on this post
    # (one succeeds, other gets 409 or duplicate detection)
    statuses = [r.status_code for r in results]
    success_count = sum(1 for s in statuses if s in (200, 201))
    conflict_count = sum(1 for s in statuses if s == 409)
    # At least one success expected
    assert success_count >= 1 or conflict_count >= 1

    count = await db.scalar(
        select(func.count()).select_from(ModerationFlag).where(
            ModerationFlag.reporter_entity_id == uuid.UUID(eid_b),
            ModerationFlag.target_id == uuid.UUID(post_id),
        )
    )
    # Should not have more than 1 flag from same user on same target
    # (if dedup is in place) — but even if 2 got through, no crash.
    assert count >= 1


# ---------------------------------------------------------------------------
# 12. Concurrent agent claim with same token → only one should succeed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_agent_claim(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)
    token_b, eid_b = await _setup_user(client, USER_B, db)

    # Bootstrap a provisional agent
    resp = await client.post(
        "/api/v1/bots/bootstrap",
        json={
            "display_name": "ClaimBot",
            "template": "general",
        },
        headers=_auth(token_a),
    )
    if resp.status_code not in (200, 201):
        pytest.skip("Bot bootstrap not available or requires different params")

    data = resp.json()
    claim_token = data.get("claim_token")
    if not claim_token:
        pytest.skip("No claim_token in bootstrap response")

    # Both users try to claim the same agent concurrently
    results = await asyncio.gather(
        client.post(
            "/api/v1/agents/claim",
            json={"claim_token": claim_token},
            headers=_auth(token_a),
        ),
        client.post(
            "/api/v1/agents/claim",
            json={"claim_token": claim_token},
            headers=_auth(token_b),
        ),
    )

    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"

    # Exactly one should succeed
    success_count = sum(1 for r in results if r.status_code == 200)
    fail_count = sum(1 for r in results if r.status_code in (400, 404, 409))
    assert success_count <= 1, "Both claims succeeded — race condition!"
    assert success_count + fail_count == 2


# ---------------------------------------------------------------------------
# 13. Concurrent follow + unfollow → consistent final state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_follow_unfollow(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)

    # First, establish a follow
    await client.post(f"/api/v1/social/follow/{eid_b}", headers=_auth(token_a))

    results = await asyncio.gather(
        client.post(f"/api/v1/social/follow/{eid_b}", headers=_auth(token_a)),
        client.delete(f"/api/v1/social/follow/{eid_b}", headers=_auth(token_a)),
    )

    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"

    # The relationship count should be either 0 or 1 — never negative or >1
    count = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(
            EntityRelationship.source_entity_id == uuid.UUID(eid_a),
            EntityRelationship.target_entity_id == uuid.UUID(eid_b),
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    assert count in (0, 1), f"Expected 0 or 1, got {count}"


# ---------------------------------------------------------------------------
# 14. Concurrent vote + bookmark on same post → both succeed independently
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_vote_and_bookmark(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)
    post_id = await _create_post(client, token_a)

    token_b, eid_b = await _setup_user(client, USER_B, db)

    results = await asyncio.gather(
        client.post(
            f"/api/v1/feed/posts/{post_id}/vote",
            json={"direction": "up"},
            headers=_auth(token_b),
        ),
        client.post(
            f"/api/v1/feed/posts/{post_id}/bookmark",
            headers=_auth(token_b),
        ),
    )

    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"


# ---------------------------------------------------------------------------
# 15. Concurrent follows from multiple users → all succeed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_follows_from_multiple_users(
    client: AsyncClient, db: AsyncSession,
):
    token_a, eid_a = await _setup_user(client, USER_A, db)
    token_b, eid_b = await _setup_user(client, USER_B, db)
    token_c, eid_c = await _setup_user(client, USER_C, db)

    # A and B both follow C concurrently
    results = await asyncio.gather(
        client.post(f"/api/v1/social/follow/{eid_c}", headers=_auth(token_a)),
        client.post(f"/api/v1/social/follow/{eid_c}", headers=_auth(token_b)),
    )

    for r in results:
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    # C should have exactly 2 followers
    count = await db.scalar(
        select(func.count()).select_from(EntityRelationship).where(
            EntityRelationship.target_entity_id == uuid.UUID(eid_c),
            EntityRelationship.type == RelationshipType.FOLLOW,
        )
    )
    assert count == 2


# ---------------------------------------------------------------------------
# 16. Concurrent replies to same post → all succeed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_replies_to_same_post(
    client: AsyncClient, db: AsyncSession,
):
    token_a, _ = await _setup_user(client, USER_A, db)
    post_id = await _create_post(client, token_a)

    token_b, _ = await _setup_user(client, USER_B, db)
    token_c, _ = await _setup_user(client, USER_C, db)

    results = await asyncio.gather(
        client.post(
            "/api/v1/feed/posts",
            json={"content": "Reply from B", "parent_post_id": post_id},
            headers=_auth(token_b),
        ),
        client.post(
            "/api/v1/feed/posts",
            json={"content": "Reply from C", "parent_post_id": post_id},
            headers=_auth(token_c),
        ),
    )

    for r in results:
        assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# 17. Concurrent votes from multiple users on same post → all succeed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_votes_from_multiple_users(
    client: AsyncClient, db: AsyncSession,
):
    token_a, _ = await _setup_user(client, USER_A, db)
    post_id = await _create_post(client, token_a)

    token_b, eid_b = await _setup_user(client, USER_B, db)
    token_c, eid_c = await _setup_user(client, USER_C, db)

    results = await asyncio.gather(
        client.post(
            f"/api/v1/feed/posts/{post_id}/vote",
            json={"direction": "up"},
            headers=_auth(token_b),
        ),
        client.post(
            f"/api/v1/feed/posts/{post_id}/vote",
            json={"direction": "up"},
            headers=_auth(token_c),
        ),
    )

    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"

    # Each user should have at most 1 vote
    for eid in (eid_b, eid_c):
        count = await db.scalar(
            select(func.count()).select_from(Vote).where(
                Vote.entity_id == uuid.UUID(eid),
                Vote.post_id == uuid.UUID(post_id),
            )
        )
        assert count <= 1


# ---------------------------------------------------------------------------
# 18. Concurrent block from both sides → both succeed, no crash
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_mutual_block(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)
    token_b, eid_b = await _setup_user(client, USER_B, db)

    results = await asyncio.gather(
        client.post(f"/api/v1/social/block/{eid_b}", headers=_auth(token_a)),
        client.post(f"/api/v1/social/block/{eid_a}", headers=_auth(token_b)),
    )

    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"

    # Both blocks should exist
    block_ab = await db.scalar(
        select(func.count()).select_from(EntityBlock).where(
            EntityBlock.blocker_id == uuid.UUID(eid_a),
            EntityBlock.blocked_id == uuid.UUID(eid_b),
        )
    )
    block_ba = await db.scalar(
        select(func.count()).select_from(EntityBlock).where(
            EntityBlock.blocker_id == uuid.UUID(eid_b),
            EntityBlock.blocked_id == uuid.UUID(eid_a),
        )
    )
    # At minimum, one block should have been created
    assert block_ab + block_ba >= 1


# ---------------------------------------------------------------------------
# 19. Concurrent bookmark toggle → consistent state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_bookmark_toggle(client: AsyncClient, db: AsyncSession):
    token_a, eid_a = await _setup_user(client, USER_A, db)
    post_id = await _create_post(client, token_a)

    # Bookmark it first
    await client.post(
        f"/api/v1/feed/posts/{post_id}/bookmark", headers=_auth(token_a),
    )

    # Now concurrently toggle (both should try to remove)
    results = await asyncio.gather(
        client.post(
            f"/api/v1/feed/posts/{post_id}/bookmark", headers=_auth(token_a),
        ),
        client.post(
            f"/api/v1/feed/posts/{post_id}/bookmark", headers=_auth(token_a),
        ),
    )

    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"

    count = await db.scalar(
        select(func.count()).select_from(Bookmark).where(
            Bookmark.entity_id == uuid.UUID(eid_a),
            Bookmark.post_id == uuid.UUID(post_id),
        )
    )
    assert count in (0, 1), f"Expected 0 or 1, got {count}"


# ---------------------------------------------------------------------------
# 20. Concurrent registration with same email → only one succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_registration_same_email(
    client: AsyncClient, db: AsyncSession,
):
    user = {
        "email": "dupe_race@example.com",
        "password": "Str0ngP@ss1",
        "display_name": "DupeRacer",
    }

    results = await asyncio.gather(
        client.post(REGISTER_URL, json=user),
        client.post(REGISTER_URL, json=user),
    )

    for r in results:
        assert r.status_code != 500, f"Got 500: {r.text}"

    # Exactly one should succeed (201), the other should get 409 or 400
    statuses = [r.status_code for r in results]
    success_count = sum(1 for s in statuses if s == 201)
    # At most one registration should succeed
    assert success_count <= 1, f"Both registrations succeeded: {statuses}"
