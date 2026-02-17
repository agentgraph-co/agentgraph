from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app


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
FEED_URL = "/api/v1/feed/posts"
FLAG_URL = "/api/v1/moderation/flag"
FLAGS_URL = "/api/v1/moderation/flags"
STATS_URL = "/api/v1/moderation/stats"

USER_A = {
    "email": "reporter@mod.com",
    "password": "Str0ngP@ss",
    "display_name": "Reporter",
}
USER_B = {
    "email": "offender@mod.com",
    "password": "Str0ngP@ss",
    "display_name": "Offender",
}
ADMIN = {
    "email": "admin@mod.com",
    "password": "Str0ngP@ss",
    "display_name": "Admin",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register + login, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


async def _make_admin(db, entity_id: str):
    """Promote entity to admin directly in DB."""
    import uuid

    from src.models import Entity

    entity = await db.get(Entity, uuid.UUID(entity_id))
    entity.is_admin = True
    await db.flush()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Flag creation tests ---


@pytest.mark.asyncio
async def test_flag_post(client: AsyncClient, db):
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # User B creates a post
    post_resp = await client.post(
        FEED_URL, json={"content": "Bad content"}, headers=_auth(token_b)
    )
    post_id = post_resp.json()["id"]

    # User A flags it
    resp = await client.post(
        FLAG_URL,
        json={
            "target_type": "post",
            "target_id": post_id,
            "reason": "spam",
            "details": "This is spam",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"
    assert resp.json()["reason"] == "spam"


@pytest.mark.asyncio
async def test_flag_entity(client: AsyncClient, db):
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    resp = await client.post(
        FLAG_URL,
        json={
            "target_type": "entity",
            "target_id": id_b,
            "reason": "harassment",
        },
        headers=_auth(token_a),
    )
    assert resp.status_code == 201
    assert resp.json()["reason"] == "harassment"


@pytest.mark.asyncio
async def test_flag_own_post_fails(client: AsyncClient, db):
    token_a, _ = await _setup_user(client, USER_A)

    post_resp = await client.post(
        FEED_URL, json={"content": "My post"}, headers=_auth(token_a)
    )
    post_id = post_resp.json()["id"]

    resp = await client.post(
        FLAG_URL,
        json={"target_type": "post", "target_id": post_id, "reason": "spam"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_flag_self_fails(client: AsyncClient, db):
    token_a, id_a = await _setup_user(client, USER_A)

    resp = await client.post(
        FLAG_URL,
        json={"target_type": "entity", "target_id": id_a, "reason": "spam"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_pending_flag_fails(client: AsyncClient, db):
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)

    await client.post(
        FLAG_URL,
        json={"target_type": "entity", "target_id": id_b, "reason": "spam"},
        headers=_auth(token_a),
    )
    resp = await client.post(
        FLAG_URL,
        json={"target_type": "entity", "target_id": id_b, "reason": "spam"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 409


# --- Admin flag management tests ---


@pytest.mark.asyncio
async def test_list_flags_non_admin_fails(client: AsyncClient, db):
    token_a, _ = await _setup_user(client, USER_A)

    resp = await client.get(FLAGS_URL, headers=_auth(token_a))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_flags_admin(client: AsyncClient, db):
    token_a, _ = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)

    # Create a flag
    await client.post(
        FLAG_URL,
        json={"target_type": "entity", "target_id": id_b, "reason": "spam"},
        headers=_auth(token_a),
    )

    resp = await client.get(FLAGS_URL, headers=_auth(admin_token))
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


@pytest.mark.asyncio
async def test_resolve_flag_dismiss(client: AsyncClient, db):
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)

    flag_resp = await client.post(
        FLAG_URL,
        json={"target_type": "entity", "target_id": id_b, "reason": "spam"},
        headers=_auth(token_a),
    )
    flag_id = flag_resp.json()["id"]

    resp = await client.patch(
        f"{FLAGS_URL}/{flag_id}/resolve",
        json={"status": "dismissed", "resolution_note": "Not spam"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "dismissed"


@pytest.mark.asyncio
async def test_resolve_flag_removes_post(client: AsyncClient, db):
    token_a, _ = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)

    # User B creates a post
    post_resp = await client.post(
        FEED_URL, json={"content": "Bad post"}, headers=_auth(token_b)
    )
    post_id = post_resp.json()["id"]

    # User A flags it
    flag_resp = await client.post(
        FLAG_URL,
        json={"target_type": "post", "target_id": post_id, "reason": "spam"},
        headers=_auth(token_a),
    )
    flag_id = flag_resp.json()["id"]

    # Admin resolves as removed
    resp = await client.patch(
        f"{FLAGS_URL}/{flag_id}/resolve",
        json={"status": "removed"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200

    # Post should now be hidden (not in feed)
    feed_resp = await client.get(FEED_URL)
    posts = feed_resp.json()["posts"]
    post_ids = [p["id"] for p in posts]
    assert post_id not in post_ids


@pytest.mark.asyncio
async def test_resolve_flag_suspends_entity(client: AsyncClient, db):
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)

    flag_resp = await client.post(
        FLAG_URL,
        json={"target_type": "entity", "target_id": id_b, "reason": "harassment"},
        headers=_auth(token_a),
    )
    flag_id = flag_resp.json()["id"]

    resp = await client.patch(
        f"{FLAGS_URL}/{flag_id}/resolve",
        json={"status": "suspended"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_moderation_stats(client: AsyncClient, db):
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)

    # Create a flag
    await client.post(
        FLAG_URL,
        json={"target_type": "entity", "target_id": id_b, "reason": "spam"},
        headers=_auth(token_a),
    )

    resp = await client.get(STATS_URL, headers=_auth(admin_token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_flags"] == 1
    assert data["pending_flags"] == 1
    assert data["resolved_flags"] == 0


@pytest.mark.asyncio
async def test_resolve_already_resolved_fails(client: AsyncClient, db):
    token_a, _ = await _setup_user(client, USER_A)
    _, id_b = await _setup_user(client, USER_B)
    admin_token, admin_id = await _setup_user(client, ADMIN)
    await _make_admin(db, admin_id)

    flag_resp = await client.post(
        FLAG_URL,
        json={"target_type": "entity", "target_id": id_b, "reason": "spam"},
        headers=_auth(token_a),
    )
    flag_id = flag_resp.json()["id"]

    await client.patch(
        f"{FLAGS_URL}/{flag_id}/resolve",
        json={"status": "dismissed"},
        headers=_auth(admin_token),
    )

    # Second resolve should fail
    resp = await client.patch(
        f"{FLAGS_URL}/{flag_id}/resolve",
        json={"status": "warned"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 409
