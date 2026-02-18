"""Cascade cleanup when an entity is deactivated.

Revokes API keys, deactivates webhooks, and logs the cascade.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit import log_action
from src.models import APIKey, Listing, Transaction, TransactionStatus, WebhookSubscription


async def cascade_deactivate(
    db: AsyncSession,
    entity_id: uuid.UUID,
    *,
    performed_by: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> dict:
    """Run cascade cleanup for a deactivated entity.

    Returns a summary dict of what was cleaned up.
    """
    now = datetime.now(timezone.utc)

    # 1. Revoke all active API keys
    result = await db.execute(
        select(APIKey).where(
            APIKey.entity_id == entity_id,
            APIKey.is_active.is_(True),
        )
    )
    api_keys = result.scalars().all()
    revoked_keys = len(api_keys)
    for key in api_keys:
        key.is_active = False
        key.revoked_at = now

    # 2. Deactivate all webhook subscriptions
    wh_result = await db.execute(
        update(WebhookSubscription)
        .where(
            WebhookSubscription.entity_id == entity_id,
            WebhookSubscription.is_active.is_(True),
        )
        .values(is_active=False)
        .returning(WebhookSubscription.id)
    )
    deactivated_webhooks = len(wh_result.fetchall())

    # 3. Deactivate all active marketplace listings
    listing_result = await db.execute(
        update(Listing)
        .where(
            Listing.entity_id == entity_id,
            Listing.is_active.is_(True),
        )
        .values(is_active=False)
        .returning(Listing.id)
    )
    deactivated_listings = len(listing_result.fetchall())

    # 4. Cancel pending transactions where entity is seller
    txn_result = await db.execute(
        update(Transaction)
        .where(
            Transaction.seller_entity_id == entity_id,
            Transaction.status == TransactionStatus.PENDING,
        )
        .values(status=TransactionStatus.CANCELLED)
        .returning(Transaction.id)
    )
    cancelled_transactions = len(txn_result.fetchall())

    # 5. Audit log the cascade
    await log_action(
        db,
        action="entity.deactivation_cascade",
        entity_id=performed_by or entity_id,
        resource_type="entity",
        resource_id=entity_id,
        details={
            "revoked_api_keys": revoked_keys,
            "deactivated_webhooks": deactivated_webhooks,
            "deactivated_listings": deactivated_listings,
            "cancelled_transactions": cancelled_transactions,
        },
        ip_address=ip_address,
    )

    await db.flush()

    return {
        "revoked_api_keys": revoked_keys,
        "deactivated_webhooks": deactivated_webhooks,
        "deactivated_listings": deactivated_listings,
        "cancelled_transactions": cancelled_transactions,
    }
