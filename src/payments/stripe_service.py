"""Stripe Connect payment integration for the AgentGraph marketplace.

Handles seller onboarding, payment intent creation, and webhook verification.
All Stripe API calls are synchronous (stripe-python SDK) and are safe to call
from async endpoints since they perform brief I/O-bound HTTP requests.
"""
from __future__ import annotations

import logging

import stripe

from src.config import settings

logger = logging.getLogger(__name__)

# Configure stripe module-level API key
stripe.api_key = settings.stripe_secret_key


def create_connect_account(entity_id: str, email: str) -> str:
    """Create a Stripe Connect Express account and return the account ID."""
    account = stripe.Account.create(
        type="express",
        email=email,
        metadata={"entity_id": entity_id},
    )
    return account.id


def create_onboarding_link(
    account_id: str, return_url: str, refresh_url: str,
) -> str:
    """Create a Stripe onboarding link for seller account setup."""
    link = stripe.AccountLink.create(
        account=account_id,
        return_url=return_url,
        refresh_url=refresh_url,
        type="account_onboarding",
    )
    return link.url


def get_account_status(account_id: str) -> dict:
    """Check whether a Connect account can accept payments."""
    account = stripe.Account.retrieve(account_id)
    return {
        "charges_enabled": account.charges_enabled,
        "payouts_enabled": account.payouts_enabled,
        "details_submitted": account.details_submitted,
    }


def create_payment_intent(
    amount_cents: int,
    seller_account_id: str,
    platform_fee_cents: int,
    metadata: dict | None = None,
) -> dict:
    """Create a PaymentIntent with automatic transfer to the seller.

    Returns a dict with ``client_secret`` (for Stripe.js) and
    ``payment_intent_id`` (for server-side tracking).
    """
    intent = stripe.PaymentIntent.create(
        amount=amount_cents,
        currency="usd",
        application_fee_amount=platform_fee_cents,
        transfer_data={"destination": seller_account_id},
        metadata=metadata or {},
    )
    return {
        "client_secret": intent.client_secret,
        "payment_intent_id": intent.id,
    }


def verify_webhook_signature(payload: bytes, signature: str) -> dict:
    """Verify and parse a Stripe webhook event.

    Raises ``stripe.error.SignatureVerificationError`` on invalid signature.
    """
    return stripe.Webhook.construct_event(
        payload, signature, settings.stripe_webhook_secret,
    )
