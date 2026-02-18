from __future__ import annotations

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.database import get_db
from src.main import app
from src.ws import manager


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
    "email": "ws_feed_a@example.com",
    "password": "Str0ngP@ss",
    "display_name": "WsFeedA",
}
USER_B = {
    "email": "ws_feed_b@example.com",
    "password": "Str0ngP@ss",
    "display_name": "WsFeedB",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_user(client: AsyncClient, user: dict) -> tuple[str, str]:
    await client.post(REGISTER_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"email": user["email"], "password": user["password"]},
    )
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_auth(token))
    return token, me.json()["id"]


class FakeWebSocket:
    """Mock WebSocket for testing broadcasts."""

    def __init__(self) -> None:
        self.messages: list[str] = []
        self.accepted = False
        self.closed = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        self.messages.append(data)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_post_creation_broadcasts_to_feed(client: AsyncClient):
    """Creating a post sends a WebSocket broadcast to the feed channel."""
    token_a, id_a = await _setup_user(client, USER_A)

    # Connect a fake WS to the feed channel
    ws = FakeWebSocket()
    await manager.connect(ws, id_a, channels=["feed"])

    try:
        # Create a post
        resp = await client.post(
            "/api/v1/feed/posts",
            json={"content": "Hello WS world!"},
            headers=_auth(token_a),
        )
        assert resp.status_code == 201

        # Check that the WS received the broadcast
        assert len(ws.messages) >= 1
        msg = json.loads(ws.messages[-1])
        assert msg["type"] == "new_post"
        assert msg["post"]["content"] == "Hello WS world!"
        assert msg["post"]["author_display_name"] == "WsFeedA"
    finally:
        manager.disconnect(ws, id_a)


@pytest.mark.asyncio
async def test_vote_broadcasts_to_feed(client: AsyncClient):
    """Voting on a post sends a WebSocket broadcast."""
    token_a, id_a = await _setup_user(client, USER_A)

    # Create a post first
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Vote broadcast test"},
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    # Connect WS
    ws = FakeWebSocket()
    await manager.connect(ws, id_a, channels=["feed"])

    try:
        # Vote
        resp = await client.post(
            f"/api/v1/feed/posts/{post_id}/vote",
            json={"direction": "up"},
            headers=_auth(token_a),
        )
        assert resp.status_code == 200

        # Find the vote_update message
        vote_msgs = [
            json.loads(m) for m in ws.messages
            if "vote_update" in m
        ]
        assert len(vote_msgs) >= 1
        assert vote_msgs[0]["post_id"] == post_id
        assert vote_msgs[0]["vote_count"] == 1
    finally:
        manager.disconnect(ws, id_a)


@pytest.mark.asyncio
async def test_notification_broadcasts_to_entity(client: AsyncClient):
    """Follow notification is sent via WebSocket to the target."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, id_b = await _setup_user(client, USER_B)

    # Connect A to notifications channel
    ws = FakeWebSocket()
    await manager.connect(ws, id_a, channels=["notifications"])

    try:
        # B follows A — should trigger notification to A
        resp = await client.post(
            f"/api/v1/social/follow/{id_a}", headers=_auth(token_b),
        )
        assert resp.status_code == 200

        # Check WS message
        notif_msgs = [
            json.loads(m) for m in ws.messages
            if "notification" in m
        ]
        assert len(notif_msgs) >= 1
        assert notif_msgs[0]["type"] == "notification"
        assert notif_msgs[0]["notification"]["kind"] == "follow"
    finally:
        manager.disconnect(ws, id_a)


@pytest.mark.asyncio
async def test_reply_broadcasts_notification(client: AsyncClient):
    """Reply triggers WS notification to original post author."""
    token_a, id_a = await _setup_user(client, USER_A)
    token_b, _ = await _setup_user(client, USER_B)

    # A creates a post
    resp = await client.post(
        "/api/v1/feed/posts",
        json={"content": "Original post"},
        headers=_auth(token_a),
    )
    post_id = resp.json()["id"]

    # Connect A to notifications
    ws = FakeWebSocket()
    await manager.connect(ws, id_a, channels=["notifications"])

    try:
        # B replies
        resp = await client.post(
            "/api/v1/feed/posts",
            json={"content": "Great post!", "parent_post_id": post_id},
            headers=_auth(token_b),
        )
        assert resp.status_code == 201

        # A should get a reply notification via WS
        notif_msgs = [
            json.loads(m) for m in ws.messages
            if "notification" in m
        ]
        assert len(notif_msgs) >= 1
        assert notif_msgs[0]["notification"]["kind"] == "reply"
    finally:
        manager.disconnect(ws, id_a)
