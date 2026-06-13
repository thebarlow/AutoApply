"""Stripe Checkout for credit packs: pack listing, checkout, webhook, history."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import payments, stripe_client
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
