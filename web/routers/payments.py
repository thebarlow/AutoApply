"""Stripe Checkout for credit packs: pack listing, checkout, webhook, history."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import payments, stripe_client
from core.credits import grant_credits
from db.database import Account, Purchase, get_db
from web.tenancy import current_profile_id

router = APIRouter(prefix="/api/payments", tags=["payments"])
logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/packs")
def list_packs():
    """Configured packs with live price/currency from Stripe."""
    out = []
    for price_id, credits in payments.load_packs().items():
        price = stripe_client.retrieve_price(price_id)
        out.append({
            "price_id": price_id,
            "credits": credits,
            "amount_usd": (price.unit_amount or 0) / 100,
            "currency": price.currency,
        })
    return out


class CheckoutRequest(BaseModel):
    price_id: str


@router.post("/checkout")
def create_checkout(body: CheckoutRequest, db: Session = Depends(get_db),
                    profile_id: int = Depends(current_profile_id)):
    """Create a Stripe Checkout session for a pack and record a pending purchase."""
    credits = payments.credits_for_price(body.price_id)
    if credits is None:
        raise HTTPException(status_code=400, detail="unknown price_id")
    acct = db.query(Account).filter_by(profile_id=profile_id).first()
    if acct is None:
        raise HTTPException(status_code=404, detail="account not found")

    if not acct.stripe_customer_id:
        acct.stripe_customer_id = stripe_client.create_customer(acct.email)
        db.commit()

    base = os.getenv("APP_BASE_URL", "http://localhost:8080")
    try:
        session = stripe_client.create_checkout_session(
            customer_id=acct.stripe_customer_id,
            price_id=body.price_id,
            success_url=f"{base}/?purchase=success",
            cancel_url=f"{base}/?purchase=cancel",
        )
    except Exception:
        logger.exception("checkout: Stripe session creation failed")
        raise HTTPException(status_code=502, detail="payment provider error")

    price = stripe_client.retrieve_price(body.price_id)
    db.add(Purchase(profile_id=profile_id, stripe_session_id=session.id,
                    price_id=body.price_id, credits=credits,
                    amount_usd=(price.unit_amount or 0) / 100,
                    status="pending", created_at=_now()))
    db.commit()
    return {"url": session.url}


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe webhook: fulfill a completed checkout by granting credits (idempotent)."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe_client.construct_event(payload, sig)
    except Exception:
        logger.warning("webhook: signature verification failed")
        raise HTTPException(status_code=400, detail="invalid signature")

    if event.type != "checkout.session.completed":
        return {"status": "ignored"}

    if db.query(Purchase).filter_by(stripe_event_id=event.id).first():
        return {"status": "duplicate"}

    session_id = event.data.object["id"]
    purchase = db.query(Purchase).filter_by(stripe_session_id=session_id).first()
    if purchase is None:
        logger.error("webhook: no purchase for session %s", session_id)
        return {"status": "no_purchase"}
    if purchase.status == "completed":
        return {"status": "already_completed"}

    purchase.stripe_event_id = event.id
    purchase.status = "completed"
    db.commit()
    grant_credits(db, purchase.profile_id, purchase.credits, reason="purchase",
                  note=f"pack {purchase.price_id}")
    return {"status": "ok"}
