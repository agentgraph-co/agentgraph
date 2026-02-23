"""WebSocket endpoints for real-time updates.

Provides WebSocket connections for live feed updates, notifications,
and activity streams. Clients authenticate via query parameter token.
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
    token: str = Query(...),
    channels: str = Query("feed,notifications"),
):
    """WebSocket endpoint for real-time updates.

    Query parameters:
        token: JWT access token for authentication
        channels: comma-separated channel names (feed, notifications, activity)
    """
    entity_id = await _authenticate_ws(token)
    if entity_id is None:
        await websocket.close(code=4001, reason="Authentication failed")
        return

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
                    await websocket.send_text(
                        json.dumps({"type": "pong"})
                    )
                # Handle AIP protocol messages
                elif msg.get("type") in (
                    "discover_request",
                    "negotiate_request",
                    "delegate_request",
                    "delegate_status",
                    "ack",
                ):
                    from src.protocol.router import handle_aip_message

                    async with async_session() as aip_db:
                        response = await handle_aip_message(
                            aip_db, entity_id, msg,
                        )
                        await aip_db.commit()
                    if response:
                        await websocket.send_text(json.dumps(response))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket, entity_id)
