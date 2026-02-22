"""Escrow lifecycle helpers for marketplace transactions.

Provides functions for releasing, cancelling, and partially capturing
escrowed payments via Stripe delayed capture.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.audit import log_action
from src.models import Transaction, TransactionStatus

logger = logging.getLogger(__name__)


async def release_escrow(
    db: AsyncSession,
    transaction: Transaction,
    captured_by_id: uuid.UUID,
) -> Transaction:
    """Capture the full authorized amount and complete the transaction."""
    from src.payments.stripe_service import capture_payment_intent

    if transaction.stripe_payment_intent_id:
        capture_payment_intent(transaction.stripe_payment_intent_id)

    transaction.status = TransactionStatus.COMPLETED
    transaction.completed_at = datetime.now(timezone.utc)

    await log_action(
        db,
        action="escrow.release",
        entity_id=captured_by_id,
        resource_type="transaction",
        resource_id=transaction.id,
        details={
            "amount_cents": transaction.amount_cents,
            "stripe_pi": transaction.stripe_payment_intent_id,
        },
    )
    await db.flush()

    logger.info(
        "Escrow released for transaction %s (captured by %s)",
        transaction.id, captured_by_id,
    )
    return transaction


async def cancel_escrow(
    db: AsyncSession,
    transaction: Transaction,
    cancelled_by_id: uuid.UUID,
) -> Transaction:
    """Cancel the payment authorization and mark the transaction cancelled."""
    from src.payments.stripe_service import cancel_payment_intent

    if transaction.stripe_payment_intent_id:
        cancel_payment_intent(transaction.stripe_payment_intent_id)

    transaction.status = TransactionStatus.CANCELLED

    await log_action(
        db,
        action="escrow.cancel",
        entity_id=cancelled_by_id,
        resource_type="transaction",
        resource_id=transaction.id,
        details={
            "amount_cents": transaction.amount_cents,
            "stripe_pi": transaction.stripe_payment_intent_id,
        },
    )
    await db.flush()

    logger.info(
        "Escrow cancelled for transaction %s (by %s)",
        transaction.id, cancelled_by_id,
    )
    return transaction


async def partial_capture(
    db: AsyncSession,
    transaction: Transaction,
    amount_cents: int,
    captured_by_id: uuid.UUID,
) -> Transaction:
    """Capture a partial amount from the authorized PaymentIntent."""
    from src.payments.stripe_service import capture_payment_intent

    if transaction.stripe_payment_intent_id:
        capture_payment_intent(
            transaction.stripe_payment_intent_id, amount_cents=amount_cents,
        )

    transaction.status = TransactionStatus.COMPLETED
    transaction.amount_cents = amount_cents
    transaction.completed_at = datetime.now(timezone.utc)

    await log_action(
        db,
        action="escrow.partial_capture",
        entity_id=captured_by_id,
        resource_type="transaction",
        resource_id=transaction.id,
        details={
            "original_amount_cents": transaction.amount_cents,
            "captured_amount_cents": amount_cents,
            "stripe_pi": transaction.stripe_payment_intent_id,
        },
    )
    await db.flush()

    logger.info(
        "Partial escrow capture for transaction %s: %d cents (by %s)",
        transaction.id, amount_cents, captured_by_id,
    )
    return transaction
