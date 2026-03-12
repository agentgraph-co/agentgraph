"""Tests for social notification emails and email preference toggle."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.main import app
from src.models import Entity, EntityType, NotificationPreference


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _create_human(db: AsyncSession, **kwargs) -> Entity:
    defaults = {
        "id": uuid.uuid4(),
        "type": EntityType.HUMAN,
        "email": f"user-{uuid.uuid4().hex[:6]}@test.com",
        "display_name": "TestUser",
        "did_web": f"did:web:agentgraph.co:u:{uuid.uuid4().hex[:8]}",
        "email_verified": True,
        "is_active": True,
    }
    defaults.update(kwargs)
    entity = Entity(**defaults)
    db.add(entity)
    await db.flush()
    return entity


@pytest.mark.asyncio
async def test_social_email_sent_on_reply_notification(db: AsyncSession):
    """Reply notification triggers email for verified human."""
    entity = await _create_human(db)

    with patch("src.email.send_social_notification_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        from src.api.notification_router import create_notification

        notif = await create_notification(
            db,
            entity_id=entity.id,
            kind="reply",
            title="Someone replied to your post",
            body="Check out the reply!",
            reference_id=str(uuid.uuid4()),
        )
        assert notif is not None

        # Give the fire-and-forget task a chance to execute
        import asyncio
        await asyncio.sleep(0.1)

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        assert call_kwargs[1]["to"] == entity.email
        assert "replied" in call_kwargs[1]["title"]


@pytest.mark.asyncio
async def test_social_email_not_sent_for_agent(db: AsyncSession):
    """Agent entities should NOT receive social emails."""
    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.AGENT,
        email="agent@test.com",
        display_name="TestAgent",
        did_web=f"did:web:agentgraph.co:u:{uuid.uuid4().hex[:8]}",
        email_verified=True,
        is_active=True,
    )
    db.add(entity)
    await db.flush()

    with patch("src.email.send_social_notification_email", new_callable=AsyncMock) as mock_send:
        from src.api.notification_router import create_notification

        await create_notification(
            db,
            entity_id=entity.id,
            kind="follow",
            title="Someone followed you",
            body="You have a new follower!",
        )

        import asyncio
        await asyncio.sleep(0.1)

        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_social_email_not_sent_when_disabled(db: AsyncSession):
    """Email not sent when email_notifications_enabled is False."""
    entity = await _create_human(db)

    # Set preference to disable email notifications
    pref = NotificationPreference(
        id=uuid.uuid4(),
        entity_id=entity.id,
        email_notifications_enabled=False,
    )
    db.add(pref)
    await db.flush()

    with patch("src.email.send_social_notification_email", new_callable=AsyncMock) as mock_send:
        from src.api.notification_router import create_notification

        await create_notification(
            db,
            entity_id=entity.id,
            kind="mention",
            title="You were mentioned",
            body="Someone mentioned you in a post.",
        )

        import asyncio
        await asyncio.sleep(0.1)

        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_social_email_not_sent_for_unverified(db: AsyncSession):
    """Email not sent when entity email is not verified."""
    entity = await _create_human(db, email_verified=False)

    with patch("src.email.send_social_notification_email", new_callable=AsyncMock) as mock_send:
        from src.api.notification_router import create_notification

        await create_notification(
            db,
            entity_id=entity.id,
            kind="vote",
            title="Someone upvoted your post",
            body="Your post got a vote!",
        )

        import asyncio
        await asyncio.sleep(0.1)

        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_email_preference_toggle_via_api(client: AsyncClient, db: AsyncSession):
    """email_notifications_enabled can be toggled via preferences endpoint."""
    from src.api.auth_service import hash_password

    entity = Entity(
        id=uuid.uuid4(),
        type=EntityType.HUMAN,
        email=f"pref-{uuid.uuid4().hex[:6]}@test.com",
        display_name="PrefUser",
        did_web=f"did:web:agentgraph.co:u:{uuid.uuid4().hex[:8]}",
        password_hash=hash_password("***REMOVED***"),
        email_verified=True,
        is_active=True,
    )
    db.add(entity)
    await db.flush()

    # Login
    login = await client.post("/api/v1/auth/login", json={
        "email": entity.email,
        "password": "***REMOVED***",
    })
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get defaults
    r = await client.get("/api/v1/notifications/preferences", headers=headers)
    assert r.status_code == 200
    assert r.json()["email_notifications_enabled"] is True

    # Disable
    r = await client.patch("/api/v1/notifications/preferences", headers=headers, json={
        "email_notifications_enabled": False,
    })
    assert r.status_code == 200
    assert r.json()["email_notifications_enabled"] is False

    # Verify persisted
    r = await client.get("/api/v1/notifications/preferences", headers=headers)
    assert r.status_code == 200
    assert r.json()["email_notifications_enabled"] is False
