"""Privilege escalation security tests.

Comprehensive tests for horizontal (user-to-user), vertical (user-to-admin),
bot-level, and token/auth privilege escalation attacks.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.agent_service import create_agent
from src.api.auth_service import create_refresh_token
from src.config import settings
from src.database import get_db
from src.main import app
from src.models import (
    APIKey,
    AuditLog,
    Conversation,
    DirectMessage,
    Entity,
    NotificationPreference,
    TrustScore,
    WebhookSubscription,
)


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"

USER_A = {
    "email": "priv_user_a@example.com",
    "password": "Str0ngP@ss1",
    "display_name": "PrivUserA",
}
USER_B = {
    "email": "priv_user_b@example.com",
    "password": "Str0ngP@ss2",
    "display_name": "PrivUserB",
}
ADMIN_USER = {
    "email": "priv_admin@example.com",
    "password": "Str0ngP@ss3",
    "display_name": "PrivAdmin",
}


async def _setup_user(
    client: AsyncClient, user: dict, db: AsyncSession | None = None,
) -> tuple[str, str]:
    """Register a user and return (access_token, entity_id)."""
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


async def _setup_admin(
    client: AsyncClient, db: AsyncSession,
) -> tuple[str, str]:
    """Register a user and promote to admin, return (token, entity_id)."""
    await client.post(REGISTER_URL, json=ADMIN_USER)
    resp = await client.post(
        LOGIN_URL, json={
            "email": ADMIN_USER["email"],
            "password": ADMIN_USER["password"],
        },
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    eid = me.json()["id"]
    # Promote to admin directly in DB
    entity = await db.get(Entity, uuid.UUID(eid))
    entity.is_admin = True
    await db.flush()
    return token, eid


async def _create_agent_for_user(
    db: AsyncSession, operator_id: str,
) -> tuple[Entity, str]:
    """Create an agent owned by operator_id, return (agent, api_key_plaintext)."""
    operator = await db.get(Entity, uuid.UUID(operator_id))
    agent, api_key = await create_agent(
        db, operator=operator, display_name="TestAgent",
        capabilities=["chat"],
    )
    await db.flush()
    return agent, api_key


# =====================================================================
# HORIZONTAL PRIVILEGE ESCALATION (User A accessing User B's resources)
# =====================================================================


@pytest.mark.asyncio
async def test_user_a_cannot_read_user_b_api_keys(client: AsyncClient, db):
    """1. User A cannot list API keys belonging to User B's agent."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)
    agent_b, _ = await _create_agent_for_user(db, eid_b)

    resp = await client.get(
        f"/api/v1/agents/{agent_b.id}/api-keys",
        headers=_auth(token_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_user_a_cannot_rotate_user_b_api_key(client: AsyncClient, db):
    """2. User A cannot rotate an API key for User B's agent."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)
    agent_b, _ = await _create_agent_for_user(db, eid_b)

    resp = await client.post(
        f"/api/v1/agents/{agent_b.id}/rotate-key",
        headers=_auth(token_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_user_a_cannot_revoke_user_b_api_key(client: AsyncClient, db):
    """3. User A cannot revoke (delete) User B's agent's API key."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)
    agent_b, _ = await _create_agent_for_user(db, eid_b)

    # Get the API key ID
    keys = await db.execute(
        select(APIKey).where(APIKey.entity_id == agent_b.id),
    )
    key = keys.scalars().first()
    assert key is not None

    resp = await client.delete(
        f"/api/v1/agents/{agent_b.id}/api-keys/{key.id}",
        headers=_auth(token_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_user_a_cannot_read_user_b_dms(client: AsyncClient, db):
    """4. User A cannot read User B's DM conversations."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    token_b, eid_b = await _setup_user(client, USER_B, db)

    # User B sends a DM to create a conversation (to themselves or a third party)
    # First create a conversation by sending a message from B
    convo = Conversation(
        id=uuid.uuid4(),
        participant_a_id=uuid.UUID(eid_b),
        participant_b_id=uuid.UUID(eid_a),
    )
    db.add(convo)
    dm = DirectMessage(
        id=uuid.uuid4(),
        conversation_id=convo.id,
        sender_id=uuid.UUID(eid_b),
        content="Private message from B",
    )
    db.add(dm)
    await db.flush()

    # User A tries to list their conversations — should only see their own
    resp = await client.get(
        "/api/v1/messages",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    # The conversation should be visible to A since they're a participant,
    # but verify B's separate conversations aren't accessible
    # Create a second conversation that A is NOT part of
    third_user_email = f"priv_third_{uuid.uuid4().hex[:8]}@example.com"
    await client.post(REGISTER_URL, json={
        "email": third_user_email,
        "password": "Str0ngP@ss4",
        "display_name": "ThirdUser",
    })
    login_resp = await client.post(
        LOGIN_URL, json={"email": third_user_email, "password": "Str0ngP@ss4"},
    )
    third_token = login_resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(third_token))
    third_id = me.json()["id"]

    convo2 = Conversation(
        id=uuid.uuid4(),
        participant_a_id=uuid.UUID(eid_b),
        participant_b_id=uuid.UUID(third_id),
    )
    db.add(convo2)
    dm2 = DirectMessage(
        id=uuid.uuid4(),
        conversation_id=convo2.id,
        sender_id=uuid.UUID(eid_b),
        content="Secret between B and third",
    )
    db.add(dm2)
    await db.flush()

    # User A should NOT be able to read convo2
    resp = await client.get(
        f"/api/v1/messages/{convo2.id}",
        headers=_auth(token_a),
    )
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_user_a_cannot_claim_user_b_agent(client: AsyncClient, db):
    """5. User A cannot claim an agent that belongs to User B."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)
    agent_b, _ = await _create_agent_for_user(db, eid_b)

    # User A tries to set themselves as operator of B's agent
    resp = await client.patch(
        f"/api/v1/agents/{agent_b.id}/set-operator",
        json={"operator_id": eid_a},
        headers=_auth(token_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_user_a_cannot_update_user_b_profile(client: AsyncClient, db):
    """6. User A cannot update User B's profile."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)

    resp = await client.patch(
        f"/api/v1/profiles/{eid_b}",
        json={"display_name": "Hacked by A"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_user_a_cannot_change_user_b_password(client: AsyncClient, db):
    """7. User A cannot change User B's password (the endpoint is self-only)."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)

    # The change-password endpoint operates on current_entity only
    # So even if A tries, it would change A's password (not B's)
    # The security property is that there's no way to specify a target user
    await client.post(
        "/api/v1/account/change-password",
        json={
            "current_password": USER_A["password"],
            "new_password": "NewHackedP@ss1",
        },
        headers=_auth(token_a),
    )
    # This changes A's own password, not B's — verify B can still login
    resp_b = await client.post(
        LOGIN_URL,
        json={"email": USER_B["email"], "password": USER_B["password"]},
    )
    assert resp_b.status_code == 200, "User B's password must be unchanged"


@pytest.mark.asyncio
async def test_user_a_cannot_deactivate_user_b_account(client: AsyncClient, db):
    """8. User A cannot deactivate User B's account."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)

    # The /account/deactivate endpoint is self-only (uses current_entity)
    # Verify that deactivating via A's token only affects A
    await client.post(
        "/api/v1/account/deactivate",
        json={"password": USER_A["password"]},
        headers=_auth(token_a),
    )
    # Whether it succeeds or not, B must still be active
    resp_b = await client.post(
        LOGIN_URL,
        json={"email": USER_B["email"], "password": USER_B["password"]},
    )
    assert resp_b.status_code == 200, "User B's account must still be active"


@pytest.mark.asyncio
async def test_user_a_cannot_read_user_b_audit_log(client: AsyncClient, db):
    """9. User A cannot read User B's personal audit log."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)

    # Create an audit log entry for B
    db.add(AuditLog(
        id=uuid.uuid4(),
        entity_id=uuid.UUID(eid_b),
        action="test_action",
        details={"test": True},
    ))
    await db.flush()

    # User A reads their own audit log
    resp = await client.get(
        "/api/v1/account/audit-log",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    # Ensure none of B's audit entries are returned
    items = resp.json().get("items", resp.json().get("logs", []))
    for item in items:
        assert item.get("entity_id") != eid_b, \
            "User A must not see User B's audit log entries"


@pytest.mark.asyncio
async def test_user_a_cannot_modify_user_b_notification_prefs(
    client: AsyncClient, db,
):
    """10. User A cannot modify User B's notification preferences."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)

    # Notification preferences are per-current_entity — no way to target B
    # But verify the endpoint only returns/modifies the caller's own prefs
    await client.patch(
        "/api/v1/notifications/preferences",
        json={"follow_enabled": False},
        headers=_auth(token_a),
    )
    # A's prefs changed, but B's should be unaffected
    # Check B's prefs directly
    pref = await db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.entity_id == uuid.UUID(eid_b),
        )
    )
    # If B has prefs, follow_enabled should still be default (True)
    if pref is not None:
        assert pref.follow_enabled is True, \
            "User B's notification prefs must be unaffected"


@pytest.mark.asyncio
async def test_user_a_cannot_modify_user_b_webhooks(client: AsyncClient, db):
    """11. User A cannot modify User B's webhook subscriptions."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    token_b, eid_b = await _setup_user(client, USER_B, db)

    # Create a webhook for B
    wh = WebhookSubscription(
        id=uuid.uuid4(),
        entity_id=uuid.UUID(eid_b),
        callback_url="https://example.com/hook",
        event_types=["post.created"],
        secret=secrets.token_hex(32),
    )
    db.add(wh)
    await db.flush()

    # User A tries to update B's webhook
    resp = await client.patch(
        f"/api/v1/webhooks/{wh.id}",
        json={"callback_url": "https://evil.com/steal"},
        headers=_auth(token_a),
    )
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_user_a_cannot_read_user_b_webhooks(client: AsyncClient, db):
    """12. User A cannot read User B's webhook subscriptions."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    token_b, eid_b = await _setup_user(client, USER_B, db)

    # Create a webhook for B
    wh = WebhookSubscription(
        id=uuid.uuid4(),
        entity_id=uuid.UUID(eid_b),
        callback_url="https://example.com/b-hook",
        event_types=["post.created"],
        secret=secrets.token_hex(32),
    )
    db.add(wh)
    await db.flush()

    # User A lists their own webhooks
    resp = await client.get(
        "/api/v1/webhooks",
        headers=_auth(token_a),
    )
    assert resp.status_code == 200
    webhooks = resp.json().get("webhooks", resp.json().get("items", []))
    for hook in webhooks:
        assert hook.get("entity_id") != eid_b, \
            "User A must not see User B's webhooks"


# =====================================================================
# VERTICAL PRIVILEGE ESCALATION (Regular user -> admin)
# =====================================================================


@pytest.mark.asyncio
async def test_regular_user_cannot_access_admin_stats(client: AsyncClient, db):
    """13. Regular user cannot access admin stats endpoint."""
    token_a, _ = await _setup_user(client, USER_A, db)

    resp = await client.get(
        "/api/v1/admin/stats",
        headers=_auth(token_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_regular_user_cannot_promote_entities(client: AsyncClient, db):
    """14. Regular user cannot promote entities to admin."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)

    resp = await client.patch(
        f"/api/v1/admin/entities/{eid_b}/promote",
        headers=_auth(token_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_regular_user_cannot_resolve_moderation_flags(
    client: AsyncClient, db,
):
    """15. Regular user cannot resolve moderation flags."""
    token_a, eid_a = await _setup_user(client, USER_A, db)

    # Try to resolve a nonexistent flag — should still get 403 before 404
    resp = await client.patch(
        f"/api/v1/moderation/flags/{uuid.uuid4()}/resolve",
        json={"resolution": "dismissed", "note": "test"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_regular_user_cannot_recompute_trust_scores(
    client: AsyncClient, db,
):
    """16. Regular user cannot trigger admin batch trust recomputation."""
    token_a, _ = await _setup_user(client, USER_A, db)

    resp = await client.post(
        "/api/v1/admin/trust/recompute",
        headers=_auth(token_a),
    )
    assert resp.status_code == 403

    resp2 = await client.post(
        "/api/v1/admin/trust/recompute-all",
        headers=_auth(token_a),
    )
    assert resp2.status_code == 403


@pytest.mark.asyncio
async def test_regular_user_cannot_quarantine_entities(client: AsyncClient, db):
    """17. Regular user cannot quarantine entities."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)

    resp = await client.post(
        f"/api/v1/admin/safety/quarantine/{eid_b}",
        json={"reason": "malicious attempt"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_regular_user_cannot_activate_propagation_freeze(
    client: AsyncClient, db,
):
    """18. Regular user cannot activate propagation freeze."""
    token_a, _ = await _setup_user(client, USER_A, db)

    resp = await client.post(
        "/api/v1/admin/safety/freeze",
        json={"active": True, "reason": "unauthorized freeze"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_regular_user_cannot_view_admin_entity_list(
    client: AsyncClient, db,
):
    """19. Regular user cannot view admin entity list."""
    token_a, _ = await _setup_user(client, USER_A, db)

    resp = await client.get(
        "/api/v1/admin/entities",
        headers=_auth(token_a),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_regular_user_cannot_suspend_entities(client: AsyncClient, db):
    """20. Regular user cannot suspend/ban entities."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)

    resp = await client.patch(
        f"/api/v1/admin/entities/{eid_b}/suspend",
        json={"reason": "unauthorized"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 403

    # Also cannot deactivate other users via admin endpoint
    resp2 = await client.patch(
        f"/api/v1/admin/entities/{eid_b}/deactivate",
        headers=_auth(token_a),
    )
    assert resp2.status_code == 403


# =====================================================================
# BOT PRIVILEGE ESCALATION
# =====================================================================


@pytest.mark.asyncio
async def test_provisional_bot_cannot_create_posts(client: AsyncClient, db):
    """21. Provisional bot cannot create posts (should get 403)."""
    _, eid_a = await _setup_user(client, USER_A, db)
    operator = await db.get(Entity, uuid.UUID(eid_a))
    agent, api_key = await create_agent(
        db, operator=operator, display_name="ProvisionalBot",
        capabilities=["chat"],
    )
    agent.is_provisional = True
    await db.flush()

    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Hello from provisional bot"},
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_provisional_bot_cannot_create_listings(client: AsyncClient, db):
    """22. Provisional bot cannot create marketplace listings."""
    _, eid_a = await _setup_user(client, USER_A, db)
    operator = await db.get(Entity, uuid.UUID(eid_a))
    agent, api_key = await create_agent(
        db, operator=operator, display_name="ProvisionalBot2",
        capabilities=["chat"],
    )
    agent.is_provisional = True
    # Give the bot a trust score so the trust gate doesn't block before
    # the provisional check fires
    db.add(TrustScore(
        id=uuid.uuid4(), entity_id=agent.id, score=0.6,
        components={"verification": 0.3, "age": 0.2, "activity": 0.1},
    ))
    await db.flush()

    resp = await client.post(
        "/api/v1/marketplace/listings",
        json={
            "title": "Unauthorized listing",
            "description": "Should not be allowed",
            "category": "service",
            "price_cents": 1000,
        },
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_bot_cannot_access_another_bots_api_keys(
    client: AsyncClient, db,
):
    """23. Bot A cannot access Bot B's API keys."""
    _, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)

    agent_a, api_key_a = await _create_agent_for_user(db, eid_a)
    agent_b, _ = await _create_agent_for_user(db, eid_b)

    # Bot A tries to list Bot B's API keys
    resp = await client.get(
        f"/api/v1/agents/{agent_b.id}/api-keys",
        headers={"X-API-Key": api_key_a},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_bot_with_limited_scopes_cannot_write(client: AsyncClient, db):
    """24. Bot with read-only scopes cannot write to full-scope endpoints."""
    _, eid_a = await _setup_user(client, USER_A, db)
    operator = await db.get(Entity, uuid.UUID(eid_a))
    agent, _ = await create_agent(
        db, operator=operator, display_name="ReadOnlyBot",
        capabilities=["chat"],
    )
    await db.flush()

    # Create a limited-scope API key (read-only)
    plaintext_key = secrets.token_hex(32)
    key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
    scoped_key = APIKey(
        id=uuid.uuid4(),
        entity_id=agent.id,
        key_hash=key_hash,
        label="read-only",
        scopes=["read"],
    )
    db.add(scoped_key)
    await db.flush()

    # The key authenticates fine for reads
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"X-API-Key": plaintext_key},
    )
    assert resp.status_code == 200

    # But should be rejected for write-scope operations
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Trying to write with read-only key"},
        headers={"X-API-Key": plaintext_key},
    )
    # Should be 403 due to missing write scope
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revoked_api_key_returns_401(client: AsyncClient, db):
    """25. Revoked API key returns 401."""
    _, eid_a = await _setup_user(client, USER_A, db)
    operator = await db.get(Entity, uuid.UUID(eid_a))
    agent, api_key = await create_agent(
        db, operator=operator, display_name="RevokedBot",
        capabilities=["chat"],
    )
    await db.flush()

    # Verify key works
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 200

    # Revoke the key
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash),
    )
    key_obj = result.scalar_one()
    key_obj.is_active = False
    await db.flush()

    # Now the key should fail
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 401


# =====================================================================
# TOKEN / AUTH ESCALATION
# =====================================================================


@pytest.mark.asyncio
async def test_expired_jwt_returns_401(client: AsyncClient, db):
    """26. Expired JWT returns 401."""
    _, eid_a = await _setup_user(client, USER_A, db)

    # Create a token that expired 1 hour ago
    payload = {
        "sub": eid_a,
        "type": "human",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "kind": "access",
        "jti": secrets.token_urlsafe(16),
    }
    expired_token = jwt.encode(
        payload, settings.jwt_secret, algorithm=settings.jwt_algorithm,
    )

    resp = await client.get(
        "/api/v1/auth/me",
        headers=_auth(expired_token),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tampered_jwt_returns_401(client: AsyncClient, db):
    """27. Tampered JWT (signed with wrong secret) returns 401."""
    _, eid_a = await _setup_user(client, USER_A, db)

    # Create a token signed with a different secret
    payload = {
        "sub": eid_a,
        "type": "human",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        "kind": "access",
        "jti": secrets.token_urlsafe(16),
    }
    tampered_token = jwt.encode(
        payload, "wrong-secret-key", algorithm=settings.jwt_algorithm,
    )

    resp = await client.get(
        "/api/v1/auth/me",
        headers=_auth(tampered_token),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_cannot_be_used_as_access_token(
    client: AsyncClient, db,
):
    """28. Refresh token cannot be used as an access token."""
    token_a, eid_a = await _setup_user(client, USER_A, db)

    # Create a refresh token
    refresh = create_refresh_token(uuid.UUID(eid_a))

    # Try to use the refresh token as a Bearer token for a protected endpoint
    resp = await client.get(
        "/api/v1/auth/me",
        headers=_auth(refresh),
    )
    assert resp.status_code == 401, \
        "Refresh token must not be accepted as an access token"


@pytest.mark.asyncio
async def test_access_token_cannot_be_used_as_refresh_token(
    client: AsyncClient, db,
):
    """29. Access token cannot be used for the refresh endpoint."""
    token_a, eid_a = await _setup_user(client, USER_A, db)

    # Try to use the access token to refresh
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token_a},
    )
    assert resp.status_code in (401, 422, 400), \
        "Access token must not be accepted as a refresh token"


@pytest.mark.asyncio
async def test_logged_out_token_returns_401(client: AsyncClient, db):
    """30. Logged-out (blacklisted) token returns 401."""
    token_a, eid_a = await _setup_user(client, USER_A, db)

    # Verify the token works
    resp = await client.get("/api/v1/auth/me", headers=_auth(token_a))
    assert resp.status_code == 200

    # Logout
    resp = await client.post("/api/v1/auth/logout", headers=_auth(token_a))
    assert resp.status_code == 200

    # Now the token should be blacklisted
    resp = await client.get("/api/v1/auth/me", headers=_auth(token_a))
    assert resp.status_code == 401


# =====================================================================
# ADDITIONAL EDGE CASES
# =====================================================================


@pytest.mark.asyncio
async def test_admin_verified_via_actual_admin(client: AsyncClient, db):
    """Verify that admin endpoints actually work for real admins (positive test)."""
    admin_token, admin_eid = await _setup_admin(client, db)

    resp = await client.get(
        "/api/v1/admin/stats",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_user_cannot_forge_admin_claim_in_jwt(client: AsyncClient, db):
    """User cannot forge a JWT with is_admin in the payload to gain admin access."""
    _, eid_a = await _setup_user(client, USER_A, db)

    # Even if user crafts a JWT with admin claims, the server checks the DB
    payload = {
        "sub": eid_a,
        "type": "human",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        "kind": "access",
        "jti": secrets.token_urlsafe(16),
        "is_admin": True,  # Forged claim
    }
    forged_token = jwt.encode(
        payload, settings.jwt_secret, algorithm=settings.jwt_algorithm,
    )

    # Admin endpoints should still reject because is_admin comes from DB
    resp = await client.get(
        "/api/v1/admin/stats",
        headers=_auth(forged_token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_deleted_user_token_returns_401(client: AsyncClient, db):
    """Token for a deactivated/deleted user returns 401."""
    token_a, eid_a = await _setup_user(client, USER_A, db)

    # Deactivate the user directly in DB
    entity = await db.get(Entity, uuid.UUID(eid_a))
    entity.is_active = False
    await db.flush()

    resp = await client.get(
        "/api/v1/auth/me",
        headers=_auth(token_a),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_user_cannot_escalate_via_agent_update(client: AsyncClient, db):
    """User A cannot update User B's agent details."""
    token_a, eid_a = await _setup_user(client, USER_A, db)
    _, eid_b = await _setup_user(client, USER_B, db)
    agent_b, _ = await _create_agent_for_user(db, eid_b)

    resp = await client.patch(
        f"/api/v1/agents/{agent_b.id}",
        json={"display_name": "Hijacked Agent"},
        headers=_auth(token_a),
    )
    assert resp.status_code == 403
