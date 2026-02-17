"""WebSocket connection manager for real-time updates.

Manages WebSocket connections grouped by entity ID and channel,
enabling targeted broadcasting of feed updates, notifications,
and activity streams.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections with per-entity channels."""

    def __init__(self) -> None:
        # channel:entity_id -> set of WebSocket connections
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        # All connections for broadcast
        self._all: set[WebSocket] = set()

    async def connect(
        self, websocket: WebSocket, entity_id: str, channels: list[str] | None = None,
    ) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        self._all.add(websocket)
        for ch in channels or ["feed"]:
            key = f"{ch}:{entity_id}"
            self._connections[key].add(websocket)

    def disconnect(self, websocket: WebSocket, entity_id: str) -> None:
        """Remove a WebSocket connection from all channels."""
        self._all.discard(websocket)
        keys_to_remove = []
        for key, sockets in self._connections.items():
            sockets.discard(websocket)
            if not sockets:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            del self._connections[key]

    async def send_to_entity(
        self, entity_id: str, channel: str, data: dict[str, Any],
    ) -> int:
        """Send a message to all connections of an entity on a channel."""
        key = f"{channel}:{entity_id}"
        sockets = self._connections.get(key, set())
        sent = 0
        dead = []
        message = json.dumps(data, default=str)
        for ws in sockets:
            try:
                await ws.send_text(message)
                sent += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections[key].discard(ws)
            self._all.discard(ws)
        return sent

    async def broadcast_to_channel(
        self, channel: str, data: dict[str, Any],
    ) -> int:
        """Broadcast to all connections subscribed to a channel."""
        message = json.dumps(data, default=str)
        sent = 0
        dead = []
        for key, sockets in self._connections.items():
            if key.startswith(f"{channel}:"):
                for ws in sockets:
                    try:
                        await ws.send_text(message)
                        sent += 1
                    except Exception:
                        dead.append((key, ws))
        for key, ws in dead:
            self._connections.get(key, set()).discard(ws)
            self._all.discard(ws)
        return sent

    async def broadcast(self, data: dict[str, Any]) -> int:
        """Broadcast to all connected clients."""
        message = json.dumps(data, default=str)
        sent = 0
        dead = []
        for ws in self._all:
            try:
                await ws.send_text(message)
                sent += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._all.discard(ws)
        return sent

    @property
    def active_connections(self) -> int:
        return len(self._all)


# Global singleton
manager = ConnectionManager()
