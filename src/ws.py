"""WebSocket connection manager with Redis pub/sub for cross-worker broadcasting.

Each Gunicorn worker maintains its own local WebSocket connections.
When a broadcast is needed, the message is published to a Redis channel
so all workers can relay it to their connected clients.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Redis channel prefix for WebSocket broadcasts
_REDIS_WS_CHANNEL = "agentgraph:ws"

# Unique ID for this worker process (prevents double-delivery)
_WORKER_ID = str(uuid.uuid4())


class ConnectionManager:
    """Manages WebSocket connections with per-entity channels.

    Local connections are tracked in-memory per worker process.
    Cross-worker messaging uses Redis pub/sub.
    """

    def __init__(self) -> None:
        # channel:entity_id -> set of WebSocket connections (local to this worker)
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        # All connections for broadcast (local to this worker)
        self._all: set[WebSocket] = set()
        # Whether the Redis subscriber background task is running
        self._subscriber_task: asyncio.Task | None = None

    async def connect(
        self, websocket: WebSocket, entity_id: str, channels: list[str] | None = None,
    ) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        self._all.add(websocket)
        for ch in channels or ["feed"]:
            key = f"{ch}:{entity_id}"
            self._connections[key].add(websocket)
        # Start Redis subscriber if not already running
        self._ensure_subscriber()

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
        """Send a message to all connections of an entity on a channel, across all workers."""
        # Always deliver locally first for immediate feedback
        sent = await self._local_send_to_entity(entity_id, channel, data)
        # Then publish to Redis for other workers
        await self._publish({
            "target": "entity",
            "channel": channel,
            "entity_id": entity_id,
            "data": data,
            "origin": _WORKER_ID,
        })
        return sent

    async def broadcast_to_channel(
        self, channel: str, data: dict[str, Any],
    ) -> int:
        """Broadcast to all connections subscribed to a channel, across all workers."""
        # Always deliver locally first
        sent = await self._local_broadcast_to_channel(channel, data)
        # Then publish to Redis for other workers
        await self._publish({
            "target": "channel",
            "channel": channel,
            "data": data,
            "origin": _WORKER_ID,
        })
        return sent

    async def broadcast(self, data: dict[str, Any]) -> int:
        """Broadcast to all connected clients across all workers."""
        # Always deliver locally first
        sent = await self._local_broadcast(data)
        # Then publish to Redis for other workers
        await self._publish({
            "target": "all",
            "data": data,
            "origin": _WORKER_ID,
        })
        return sent

    @property
    def active_connections(self) -> int:
        return len(self._all)

    # --- Redis pub/sub ---

    async def _publish(self, message: dict[str, Any]) -> bool:
        """Publish a message to the Redis WebSocket channel."""
        try:
            from src.redis_client import get_redis

            r = get_redis()
            await r.publish(_REDIS_WS_CHANNEL, json.dumps(message, default=str))
            return True
        except Exception:
            logger.debug("Redis pub/sub unavailable, using local-only delivery")
            return False

    def _ensure_subscriber(self) -> None:
        """Start the Redis subscriber task if not already running."""
        if self._subscriber_task is None or self._subscriber_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._subscriber_task = loop.create_task(self._subscribe_loop())
            except RuntimeError:
                pass

    async def _subscribe_loop(self) -> None:
        """Background task that listens for Redis pub/sub messages and delivers locally."""
        try:
            from src.redis_client import get_redis

            r = get_redis()
            pubsub = r.pubsub()
            await pubsub.subscribe(_REDIS_WS_CHANNEL)

            async for raw_message in pubsub.listen():
                if raw_message["type"] != "message":
                    continue
                try:
                    msg = json.loads(raw_message["data"])
                    await self._handle_pubsub_message(msg)
                except Exception:
                    logger.exception("Error handling pub/sub message")
        except asyncio.CancelledError:
            return
        except Exception:
            logger.warning("Redis subscriber disconnected, will retry on next connection")
            self._subscriber_task = None

    async def _handle_pubsub_message(self, msg: dict[str, Any]) -> None:
        """Route an incoming pub/sub message to local WebSocket connections.

        Skip messages from this worker (already delivered locally).
        """
        if msg.get("origin") == _WORKER_ID:
            return

        target = msg.get("target")
        data = msg.get("data", {})

        if target == "entity":
            await self._local_send_to_entity(
                msg["entity_id"], msg["channel"], data,
            )
        elif target == "channel":
            await self._local_broadcast_to_channel(msg["channel"], data)
        elif target == "all":
            await self._local_broadcast(data)

    # --- Local delivery (this worker only) ---

    async def _local_send_to_entity(
        self, entity_id: str, channel: str, data: dict[str, Any],
    ) -> int:
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

    async def _local_broadcast_to_channel(
        self, channel: str, data: dict[str, Any],
    ) -> int:
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

    async def _local_broadcast(self, data: dict[str, Any]) -> int:
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


# Global singleton
manager = ConnectionManager()
