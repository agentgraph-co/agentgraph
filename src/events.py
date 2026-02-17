"""In-process event bus for AgentGraph.

Dispatches events to registered handlers and webhook subscribers.
Production deployment should replace with Redis pub/sub or a
dedicated message broker for multi-process support.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from collections.abc import Coroutine
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import WebhookSubscription

logger = logging.getLogger(__name__)

# Type for async event handlers
EventHandler = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]

# In-memory handler registry
_handlers: dict[str, list[EventHandler]] = {}


def on(event_type: str) -> Callable[[EventHandler], EventHandler]:
    """Decorator to register an event handler."""
    def decorator(fn: EventHandler) -> EventHandler:
        if event_type not in _handlers:
            _handlers[event_type] = []
        _handlers[event_type].append(fn)
        return fn
    return decorator


def register_handler(event_type: str, handler: EventHandler) -> None:
    """Register an event handler programmatically."""
    if event_type not in _handlers:
        _handlers[event_type] = []
    _handlers[event_type].append(handler)


async def emit(event_type: str, payload: dict[str, Any]) -> None:
    """Emit an event to all registered handlers.

    Handlers run concurrently but failures in one don't affect others.
    """
    handlers = _handlers.get(event_type, [])
    if not handlers:
        return

    tasks = [_safe_call(h, event_type, payload) for h in handlers]
    await asyncio.gather(*tasks)


async def _safe_call(
    handler: EventHandler, event_type: str, payload: dict[str, Any]
) -> None:
    """Call a handler, catching and logging exceptions."""
    try:
        await handler(event_type, payload)
    except Exception:
        logger.exception("Event handler failed for %s", event_type)


async def dispatch_webhooks(
    db: AsyncSession,
    event_type: str,
    payload: dict[str, Any],
) -> int:
    """Deliver an event to all matching webhook subscribers.

    Returns the number of successful deliveries.
    """
    result = await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.is_active.is_(True),
        )
    )
    subscriptions = result.scalars().all()

    # Filter to subscriptions interested in this event type
    matching = [s for s in subscriptions if event_type in (s.event_types or [])]

    if not matching:
        return 0

    delivered = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for sub in matching:
            success = await _deliver_webhook(client, sub, event_type, payload)
            if success:
                delivered += 1
                if sub.consecutive_failures > 0:
                    sub.consecutive_failures = 0
            else:
                sub.consecutive_failures = (sub.consecutive_failures or 0) + 1
                # Auto-deactivate after 10 consecutive failures
                if sub.consecutive_failures >= 10:
                    sub.is_active = False
                    logger.warning(
                        "Deactivated webhook %s after %d failures",
                        sub.id,
                        sub.consecutive_failures,
                    )

    await db.flush()
    return delivered


async def _deliver_webhook(
    client: httpx.AsyncClient,
    sub: WebhookSubscription,
    event_type: str,
    payload: dict[str, Any],
) -> bool:
    """Deliver a single webhook. Returns True on success."""
    body = json.dumps({
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }, default=str)

    # Sign the payload with HMAC-SHA256
    signature = hmac.new(
        sub.secret_hash.encode(),
        body.encode(),
        hashlib.sha256,
    ).hexdigest()

    try:
        response = await client.post(
            sub.callback_url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-AgentGraph-Signature": f"sha256={signature}",
                "X-AgentGraph-Event": event_type,
            },
        )
        return 200 <= response.status_code < 300
    except Exception:
        logger.exception("Webhook delivery failed for %s", sub.callback_url)
        return False


def clear_handlers() -> None:
    """Clear all registered handlers. Useful for testing."""
    _handlers.clear()
