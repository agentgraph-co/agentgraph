"""WebSocket endpoints for real-time updates.

Provides WebSocket connections for live feed updates, notifications,
and activity streams. Clients authenticate via first message or query parameter.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from src.api.auth_service import decode_token, get_entity_by_id
from src.database import async_session
from src.ws import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


async def _safe_send(ws: WebSocket, data: dict) -> None:
    """Send JSON to WebSocket, ignoring errors if client already disconnected."""
    try:
        await ws.send_text(json.dumps(data))
    except (RuntimeError, WebSocketDisconnect):
        pass


async def _safe_close(ws: WebSocket, code: int = 1000, reason: str = "") -> None:
    """Close WebSocket, ignoring errors if already closed."""
    try:
        await ws.close(code=code, reason=reason)
    except (RuntimeError, WebSocketDisconnect):
        pass


async def _authenticate_ws(token: str) -> str | None:
    """Validate a JWT token and return entity_id or None."""
    payload = decode_token(token)
    if payload is None or payload.get("kind") != "access":
        return None

    entity_id = payload.get("sub")
    if not entity_id:
        return None

    # Check token blacklist (logout / rotation)
    jti = payload.get("jti")
    if jti:
        from src.api.auth_service import is_token_blacklisted

        async with async_session() as db:
            if await is_token_blacklisted(db, jti):
                return None

    async with async_session() as db:
        entity = await get_entity_by_id(db, entity_id)
        if entity is None or not entity.is_active:
            return None

    # Check password-change invalidation
    from src import cache

    inv_ts = await cache.get(f"token:inv:{entity_id}")
    if inv_ts is not None and payload.get("iat", 0) <= inv_ts:
        return None

    return entity_id


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(None),
    channels: str = Query("feed,notifications"),
):
    """WebSocket endpoint for real-time updates.

    Authentication methods (in priority order):
        1. First message: {"type": "auth", "token": "..."} (preferred — avoids token in URL)
        2. Query parameter: ?token=... (backward compatible)

    Query parameters:
        channels: comma-separated channel names (feed, notifications, activity)
    """
    entity_id: str | None = None

    # Method 1: token in query param — authenticate BEFORE accept to avoid
    # ASGI state errors from accepting then immediately closing.
    if token:
        logger.warning(
            "WebSocket auth via query parameter is deprecated, "
            "use first-message auth instead"
        )
        entity_id = await _authenticate_ws(token)
        if entity_id is None:
            try:
                await websocket.close(code=4001, reason="Authentication failed")
            except (RuntimeError, WebSocketDisconnect):
                pass
            return
        try:
            await websocket.accept()
        except (RuntimeError, WebSocketDisconnect):
            return
    else:
        # Method 2: must accept first, then wait for auth message
        try:
            await websocket.accept()
        except (RuntimeError, WebSocketDisconnect):
            return

        try:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "auth" and msg.get("token"):
                entity_id = await _authenticate_ws(msg["token"])
            if entity_id is None:
                await _safe_send(websocket, {"type": "auth_failed", "reason": "Invalid token"})
                await _safe_close(websocket, 4001, "Authentication failed")
                return
        except (json.JSONDecodeError, WebSocketDisconnect, RuntimeError):
            await _safe_close(websocket, 4001, "Authentication failed")
            return

    # Send auth confirmation
    await _safe_send(websocket, {"type": "auth_ok"})

    channel_list = [c.strip() for c in channels.split(",") if c.strip()]
    valid_channels = {
        "feed", "notifications", "activity", "aip",
        "messages", "marketplace", "disputes",
    }
    channel_list = [c for c in channel_list if c in valid_channels]
    if not channel_list:
        channel_list = ["feed"]

    await manager.connect(websocket, entity_id, channel_list)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                # Handle ping/pong for keepalive
                if msg.get("type") == "ping":
                    await _safe_send(websocket, {"type": "pong"})
                # Handle AIP protocol messages
                elif msg.get("type") in (
                    "discover_request",
                    "negotiate_request",
                    "delegate_request",
                    "delegate_status",
                    "ack",
                ):
                    try:
                        from src.protocol.router import handle_aip_message

                        async with async_session() as aip_db:
                            response = await handle_aip_message(
                                aip_db, entity_id, msg,
                            )
                            await aip_db.commit()
                        if response:
                            await _safe_send(websocket, response)
                    except Exception:
                        logger.exception(
                            "Error handling AIP message for entity %s",
                            entity_id,
                        )
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        logger.debug("WebSocket disconnect for entity %s", entity_id)
        manager.disconnect(websocket, entity_id)
    except RuntimeError as exc:
        # "WebSocket is not connected" — normal client disconnect
        if "not connected" in str(exc).lower():
            logger.debug("WebSocket already disconnected for entity %s", entity_id)
        else:
            logger.exception(
                "Unexpected WebSocket RuntimeError for entity %s", entity_id,
            )
        manager.disconnect(websocket, entity_id)
    except Exception:
        logger.exception(
            "Unexpected WebSocket error for entity %s", entity_id,
        )
        manager.disconnect(websocket, entity_id)
