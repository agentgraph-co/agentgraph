from __future__ import annotations

import json

import pytest

from src.ws import ConnectionManager


class FakeWebSocket:
    """Minimal mock WebSocket for testing ConnectionManager."""

    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[str] = []
        self.closed = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        if self.closed:
            raise RuntimeError("WebSocket closed")
        self.messages.append(data)


@pytest.mark.asyncio
async def test_connect_and_disconnect():
    mgr = ConnectionManager()
    ws = FakeWebSocket()

    await mgr.connect(ws, "entity-1", ["feed"])
    assert mgr.active_connections == 1

    mgr.disconnect(ws, "entity-1")
    assert mgr.active_connections == 0


@pytest.mark.asyncio
async def test_send_to_entity():
    mgr = ConnectionManager()
    ws = FakeWebSocket()

    await mgr.connect(ws, "entity-1", ["notifications"])
    sent = await mgr.send_to_entity(
        "entity-1", "notifications", {"type": "test"},
    )
    assert sent == 1
    assert len(ws.messages) == 1
    assert json.loads(ws.messages[0])["type"] == "test"


@pytest.mark.asyncio
async def test_send_to_different_channel_no_delivery():
    mgr = ConnectionManager()
    ws = FakeWebSocket()

    await mgr.connect(ws, "entity-1", ["feed"])
    sent = await mgr.send_to_entity(
        "entity-1", "notifications", {"type": "test"},
    )
    assert sent == 0
    assert len(ws.messages) == 0


@pytest.mark.asyncio
async def test_broadcast_to_channel():
    mgr = ConnectionManager()
    ws1 = FakeWebSocket()
    ws2 = FakeWebSocket()
    ws3 = FakeWebSocket()

    await mgr.connect(ws1, "entity-1", ["feed"])
    await mgr.connect(ws2, "entity-2", ["feed"])
    await mgr.connect(ws3, "entity-3", ["notifications"])

    sent = await mgr.broadcast_to_channel(
        "feed", {"type": "new_post"},
    )
    assert sent == 2
    assert len(ws1.messages) == 1
    assert len(ws2.messages) == 1
    assert len(ws3.messages) == 0


@pytest.mark.asyncio
async def test_broadcast_all():
    mgr = ConnectionManager()
    ws1 = FakeWebSocket()
    ws2 = FakeWebSocket()

    await mgr.connect(ws1, "entity-1", ["feed"])
    await mgr.connect(ws2, "entity-2", ["notifications"])

    sent = await mgr.broadcast({"type": "system_alert"})
    assert sent == 2


@pytest.mark.asyncio
async def test_dead_connection_cleaned_up():
    mgr = ConnectionManager()
    ws = FakeWebSocket()

    await mgr.connect(ws, "entity-1", ["feed"])
    ws.closed = True  # Simulate disconnection

    sent = await mgr.send_to_entity(
        "entity-1", "feed", {"type": "test"},
    )
    assert sent == 0
    assert mgr.active_connections == 0


@pytest.mark.asyncio
async def test_multiple_channels():
    mgr = ConnectionManager()
    ws = FakeWebSocket()

    await mgr.connect(ws, "entity-1", ["feed", "notifications"])

    sent_feed = await mgr.send_to_entity(
        "entity-1", "feed", {"type": "feed_update"},
    )
    sent_notif = await mgr.send_to_entity(
        "entity-1", "notifications", {"type": "notification"},
    )
    assert sent_feed == 1
    assert sent_notif == 1
    assert len(ws.messages) == 2
