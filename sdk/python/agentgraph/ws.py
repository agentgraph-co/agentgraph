"""WebSocket client helper for real-time AgentGraph streams."""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# Type alias for message handlers
MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


class AgentGraphWebSocket:
    """WebSocket client for real-time AgentGraph events.

    Usage:
        ws = AgentGraphWebSocket(
            base_url="ws://localhost:8000",
            access_token="your_jwt_token",
            channels=["feed", "notifications", "marketplace"],
        )
        ws.on("feed", handle_feed_message)
        ws.on("marketplace", handle_marketplace_message)
        await ws.connect()
    """

    def __init__(
        self,
        base_url: str,
        access_token: str,
        channels: list[str] | None = None,
        ping_interval: float = 30.0,
    ):
        self._base_url = (
            base_url.rstrip("/")
            .replace("http://", "ws://")
            .replace("https://", "wss://")
        )
        self._access_token = access_token
        self._channels = channels or ["feed", "notifications"]
        self._ping_interval = ping_interval
        self._handlers: dict[str, list[MessageHandler]] = {}
        self._ws: Any = None
        self._running = False

    def on(self, channel: str, handler: MessageHandler) -> None:
        """Register a handler for messages on a specific channel."""
        self._handlers.setdefault(channel, []).append(handler)

    def on_any(self, handler: MessageHandler) -> None:
        """Register a handler for messages on any channel."""
        self._handlers.setdefault("*", []).append(handler)

    @property
    def ws_url(self) -> str:
        """Build the full WebSocket URL with token and channels."""
        channels_str = ",".join(self._channels)
        return (
            f"{self._base_url}/api/v1/ws"
            f"?token={self._access_token}"
            f"&channels={channels_str}"
        )

    async def connect(self) -> None:
        """Connect to the WebSocket and start receiving messages.

        Requires the ``websockets`` package: pip install websockets
        """
        try:
            import websockets  # noqa: F811
        except ImportError:
            raise ImportError(
                "websockets package required: pip install websockets"
            )

        self._running = True
        async with websockets.connect(self.ws_url) as ws:
            self._ws = ws
            ping_task = asyncio.create_task(self._ping_loop())
            try:
                async for message in ws:
                    try:
                        data = json.loads(message)
                        await self._dispatch(data)
                    except json.JSONDecodeError:
                        logger.warning(
                            "Received non-JSON message: %s", message[:100],
                        )
            finally:
                self._running = False
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()

    async def send(self, data: dict[str, Any]) -> None:
        """Send a message over the WebSocket."""
        if self._ws:
            await self._ws.send(json.dumps(data))

    async def _ping_loop(self) -> None:
        """Send periodic pings to keep the connection alive."""
        while self._running:
            await asyncio.sleep(self._ping_interval)
            if self._ws and self._running:
                try:
                    await self._ws.send(json.dumps({"type": "ping"}))
                except Exception:
                    break

    async def _dispatch(self, data: dict[str, Any]) -> None:
        """Dispatch a message to registered handlers."""
        if data.get("type") == "pong":
            return

        channel = data.get("channel", "")

        # Channel-specific handlers
        for handler in self._handlers.get(channel, []):
            try:
                await handler(data)
            except Exception:
                logger.exception("Handler error on channel %s", channel)

        # Wildcard handlers
        for handler in self._handlers.get("*", []):
            try:
                await handler(data)
            except Exception:
                logger.exception("Wildcard handler error")
