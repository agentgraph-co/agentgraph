from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.models import Entity, TrustScore


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

USER_REPORTER = {
    "email": "tw-reporter@test.com",
    "password": "Str0ngP@ss",
    "display_name": "TrustReporter",
}
USER_TARGET = {
    "email": "tw-target@test.com",
    "password": "Str0ngP@ss",
    "display_name": "TrustTarget",
}
ADMIN_USER = {
    "email": "tw-admin@test.com",
    "password": "Str0ngP@ss",
    "display_name": "TrustAdmin",
}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]}
    )
    token = resp.json()["access_token"]
    me = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    return token, me.json()["id"]


async def _make_admin(db, entity_id: str):
    entity = await db.get(Entity, uuid.UUID(entity_id))
    entity.is_admin = True
    await db.flush()


@pytest.mark.asyncio
async def test_flag_stores_reporter_trust_score(client, db):
    """When a user creates a flag, their trust score should be stored on it."""
    reporter_token, reporter_id = await _setup_user(client, USER_REPORTER)
    target_token, target_id = await _setup_user(client, USER_TARGET)

    # Set reporter's trust score
    ts = TrustScore(
        id=uuid.uuid4(),
        entity_id=uuid.UUID(reporter_id),
        score=0.85,
    )
    db.add(ts)
    await db.flush()

    # Target creates a post to flag
    post_resp = await client.post(
        FEED_URL,
        json={"content": "Flaggable content here"},
        headers={"Authorization": f"Bearer {target_token}"},
    )
    post_id = post_resp.json()["id"]

    # Reporter flags the post
    flag_resp = await client.post(
        FLAG_URL,
        json={
            "target_type": "post",
            "target_id": post_id,
            "reason": "spam",
            "details": "This is spam",
        },
        headers={"Authorization": f"Bearer {reporter_token}"},
    )
    assert flag_resp.status_code == 201
    data = flag_resp.json()
    assert data["reporter_trust_score"] == pytest.approx(0.85, abs=0.01)


@pytest.mark.asyncio
async def test_flag_without_trust_score_defaults_zero(client, db):
    """Reporter without a TrustScore record should get 0.0."""
    reporter_token, reporter_id = await _setup_user(client, {
        "email": "tw-nots@test.com",
        "password": "Str0ngP@ss",
        "display_name": "NoTrustReporter",
    })
    target_token, target_id = await _setup_user(client, {
        "email": "tw-notst@test.com",
        "password": "Str0ngP@ss",
        "display_name": "NoTrustTarget",
    })

    post_resp = await client.post(
        FEED_URL,
        json={"content": "More flaggable content"},
        headers={"Authorization": f"Bearer {target_token}"},
    )
    post_id = post_resp.json()["id"]

    flag_resp = await client.post(
        FLAG_URL,
        json={
            "target_type": "post",
            "target_id": post_id,
            "reason": "spam",
        },
        headers={"Authorization": f"Bearer {reporter_token}"},
    )
    assert flag_resp.status_code == 201
    assert flag_resp.json()["reporter_trust_score"] == 0.0


@pytest.mark.asyncio
async def test_flags_sorted_by_trust_score(client, db):
    """Admin flag list with sort=trust should show high-trust reporters first."""
    admin_token, admin_id = await _setup_user(client, ADMIN_USER)
    await _make_admin(db, admin_id)

    reporter_token, reporter_id = await _setup_user(client, {
        "email": "tw-hir@test.com",
        "password": "Str0ngP@ss",
        "display_name": "HighTrustReporter",
    })
    low_token, low_id = await _setup_user(client, {
        "email": "tw-lor@test.com",
        "password": "Str0ngP@ss",
        "display_name": "LowTrustReporter",
    })
    target_token, target_id = await _setup_user(client, {
        "email": "tw-targ2@test.com",
        "password": "Str0ngP@ss",
        "display_name": "TargetUser",
    })

    # Set trust scores
    db.add(TrustScore(id=uuid.uuid4(), entity_id=uuid.UUID(reporter_id), score=0.9))
    db.add(TrustScore(id=uuid.uuid4(), entity_id=uuid.UUID(low_id), score=0.2))
    await db.flush()

    # Create two posts and flag them
    post1_resp = await client.post(
        FEED_URL,
        json={"content": "First post"},
        headers={"Authorization": f"Bearer {target_token}"},
    )
    post2_resp = await client.post(
        FEED_URL,
        json={"content": "Second post"},
        headers={"Authorization": f"Bearer {target_token}"},
    )

    # Low trust reporter flags first (created earlier)
    await client.post(
        FLAG_URL,
        json={"target_type": "post", "target_id": post1_resp.json()["id"], "reason": "spam"},
        headers={"Authorization": f"Bearer {low_token}"},
    )
    # High trust reporter flags second
    await client.post(
        FLAG_URL,
        json={"target_type": "post", "target_id": post2_resp.json()["id"], "reason": "spam"},
        headers={"Authorization": f"Bearer {reporter_token}"},
    )

    # Get flags sorted by trust
    resp = await client.get(
        f"{FLAGS_URL}?sort=trust",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    flags = resp.json()["flags"]
    assert len(flags) >= 2

    # High trust should be first
    trust_scores = [
        f["reporter_trust_score"] for f in flags
        if f["reporter_trust_score"] is not None
    ]
    assert trust_scores == sorted(trust_scores, reverse=True)


@pytest.mark.asyncio
async def test_warn_action_sends_notification(client, db):
    """Resolving a flag as 'warned' should notify the target without suspending."""
    admin_token, admin_id = await _setup_user(client, {
        "email": "tw-wadmin@test.com",
        "password": "Str0ngP@ss",
        "display_name": "WarnAdmin",
    })
    await _make_admin(db, admin_id)

    reporter_token, _ = await _setup_user(client, {
        "email": "tw-wreporter@test.com",
        "password": "Str0ngP@ss",
        "display_name": "WarnReporter",
    })
    target_token, target_id = await _setup_user(client, {
        "email": "tw-wtarget@test.com",
        "password": "Str0ngP@ss",
        "display_name": "WarnTarget",
    })

    # Create a post and flag it
    post_resp = await client.post(
        FEED_URL,
        json={"content": "Warning-worthy content"},
        headers={"Authorization": f"Bearer {target_token}"},
    )
    flag_resp = await client.post(
        FLAG_URL,
        json={"target_type": "post", "target_id": post_resp.json()["id"], "reason": "harassment"},
        headers={"Authorization": f"Bearer {reporter_token}"},
    )
    flag_id = flag_resp.json()["id"]

    # Admin resolves as warned
    resolve_resp = await client.patch(
        f"{FLAGS_URL}/{flag_id}/resolve",
        json={"status": "warned", "resolution_note": "First warning"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["status"] == "warned"

    # Target should still be active
    target = await db.get(Entity, uuid.UUID(target_id))
    await db.refresh(target)
    assert target.is_active is True

    # Target should have a notification
    notif_resp = await client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {target_token}"},
    )
    assert notif_resp.status_code == 200
    notifs = notif_resp.json()["notifications"]
    warn_notifs = [n for n in notifs if "warning" in n.get("title", "").lower()]
    assert len(warn_notifs) >= 1


@pytest.mark.asyncio
async def test_flag_entity_with_trust_score(client, db):
    """Flagging an entity should store the reporter's trust score."""
    reporter_token, reporter_id = await _setup_user(client, {
        "email": "tw-er@test.com",
        "password": "Str0ngP@ss",
        "display_name": "EntityReporter",
    })
    target_token, target_id = await _setup_user(client, {
        "email": "tw-et@test.com",
        "password": "Str0ngP@ss",
        "display_name": "EntityTarget",
    })

    db.add(TrustScore(id=uuid.uuid4(), entity_id=uuid.UUID(reporter_id), score=0.7))
    await db.flush()

    flag_resp = await client.post(
        FLAG_URL,
        json={
            "target_type": "entity",
            "target_id": target_id,
            "reason": "other",
        },
        headers={"Authorization": f"Bearer {reporter_token}"},
    )
    assert flag_resp.status_code == 201
    assert flag_resp.json()["reporter_trust_score"] == pytest.approx(0.7, abs=0.01)
