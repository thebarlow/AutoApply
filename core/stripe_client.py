"""Thin wrapper over the Stripe SDK. Router code calls these so tests can
monkeypatch this module instead of reaching into the SDK."""
from __future__ import annotations

import os

import stripe


def _client() -> "stripe.StripeClient":
    """Build a Stripe client using the secret key from the environment.

    Returns:
        A configured `stripe.StripeClient` instance.
    """
    return stripe.StripeClient(os.environ["STRIPE_SECRET_KEY"])


def create_customer(email: str) -> str:
    """Create a Stripe Customer.

    Args:
        email: The customer's email address.

    Returns:
        The new customer's Stripe ID.
    """
    customer = _client().v1.customers.create(params={"email": email})
    return customer.id


def create_checkout_session(*, customer_id: str, price_id: str,
                             success_url: str, cancel_url: str):
    """Create a one-time-payment Checkout Session.

    Args:
        customer_id: Stripe Customer ID to attach to the session.
        price_id: Stripe Price ID for the single line item.
        success_url: URL to redirect to after successful payment.
        cancel_url: URL to redirect to if the customer cancels.

    Returns:
        The created `stripe.checkout.Session` object (exposes `.id`, `.url`).
    """
    return _client().v1.checkout.sessions.create(params={
        "mode": "payment",
        "customer": customer_id,
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
    })


def retrieve_price(price_id: str):
    """Fetch a Stripe Price.

    Args:
        price_id: The Stripe Price ID to retrieve.

    Returns:
        The `stripe.Price` object (exposes `.unit_amount`, `.currency`).
    """
    return _client().v1.prices.retrieve(price_id)


def construct_event(payload: bytes, sig_header: str):
    """Verify and parse a Stripe webhook event.

    Args:
        payload: The raw request body.
        sig_header: The value of the `Stripe-Signature` header.

    Returns:
        The parsed `stripe.Event` object.

    Raises:
        stripe.error.SignatureVerificationError: If the signature is invalid.
    """
    return stripe.Webhook.construct_event(
        payload, sig_header, os.environ["STRIPE_WEBHOOK_SECRET"])
