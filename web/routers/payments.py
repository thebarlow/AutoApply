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


def _is_no_such_customer(exc: Exception) -> bool:
    """True if a Stripe error indicates the referenced customer doesn't exist."""
    return "no such customer" in str(exc).lower()


@router.get("/packs")
def list_packs(db: Session = Depends(get_db),
               profile_id: int = Depends(current_profile_id)):
    """Packs visible to the current account's tier, with computed credits."""
    acct = db.query(Account).filter_by(profile_id=profile_id).first()
    tier = acct.tier if acct is not None else "standard"
    try:
        return payments.packs_for_tier(tier)
    except ValueError:
        logger.exception("packs: pricing misconfigured for tier %s", tier)
        raise HTTPException(status_code=500, detail="pricing configuration error")


class CheckoutRequest(BaseModel):
    price_id: str


@router.post("/checkout")
def create_checkout(body: CheckoutRequest, db: Session = Depends(get_db),
                    profile_id: int = Depends(current_profile_id)):
    """Create a Checkout session for a pack visible to the buyer's tier."""
    acct = db.query(Account).filter_by(profile_id=profile_id).first()
    if acct is None:
        raise HTTPException(status_code=404, detail="account not found")

    try:
        resolved = payments.resolve_price_id(body.price_id, acct.tier)
    except ValueError:
        logger.exception("checkout: pricing misconfigured for tier %s", acct.tier)
        raise HTTPException(status_code=500, detail="pricing configuration error")
    if resolved is None:
        raise HTTPException(status_code=400, detail="unknown or unavailable price_id")
    amount_usd, credits = resolved

    if not acct.stripe_customer_id:
        acct.stripe_customer_id = stripe_client.create_customer(acct.email)
        db.commit()

    base = os.getenv("APP_BASE_URL", "http://localhost:8080")

    def _open_session():
        return stripe_client.create_checkout_session(
            customer_id=acct.stripe_customer_id,
            price_id=body.price_id,
            success_url=f"{base}/?purchase=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base}/?purchase=cancel",
        )

    try:
        session = _open_session()
    except Exception as exc:
        # A stored customer can go stale (e.g. the Stripe environment/key changed).
        # Recreate it once and retry rather than failing the purchase.
        if _is_no_such_customer(exc):
            logger.warning("checkout: stale customer %s, recreating",
                           acct.stripe_customer_id)
            acct.stripe_customer_id = stripe_client.create_customer(acct.email)
            db.commit()
            try:
                session = _open_session()
            except Exception:
                logger.exception("checkout: session creation failed after customer refresh")
                raise HTTPException(status_code=502, detail="payment provider error")
        else:
            logger.exception("checkout: Stripe session creation failed")
            raise HTTPException(status_code=502, detail="payment provider error")

    db.add(Purchase(profile_id=profile_id, stripe_session_id=session.id,
                    price_id=body.price_id, credits=credits,
                    amount_usd=float(amount_usd), status="pending",
                    tier=acct.tier, created_at=_now()))
    db.commit()
    return {"url": session.url}


@router.get("/history")
def history(db: Session = Depends(get_db),
            profile_id: int = Depends(current_profile_id)):
    """Recent purchases for the current tenant, newest first."""
    rows = (db.query(Purchase).filter_by(profile_id=profile_id)
            .order_by(Purchase.id.desc()).limit(50).all())
    return [{"stripe_session_id": r.stripe_session_id, "credits": r.credits,
             "amount_usd": r.amount_usd, "status": r.status,
             "created_at": r.created_at} for r in rows]


def _fulfill(db: Session, session_id: str, *, event_id: str | None = None) -> str:
    """Grant credits for a paid checkout exactly once. Shared by the webhook and
    the success-redirect verify path. Returns a short status string.

    Idempotency is enforced by an **atomic conditional claim**: a single SQL
    ``UPDATE ... WHERE status != 'completed'`` flips the purchase to completed,
    and only the caller whose update actually matches a row (rowcount == 1) goes
    on to grant credits. Concurrent webhook/verify calls (or double-clicks) that
    lose the race match 0 rows and grant nothing — so a single payment can never
    be credited twice, even under a race. The grant and the status flip share one
    transaction, so a failed grant rolls the claim back too (the purchase stays
    pending and can be retried)."""
    purchase = db.query(Purchase).filter_by(stripe_session_id=session_id).first()
    if purchase is None:
        logger.error("fulfill: no purchase for session %s", session_id)
        return "no_purchase"
    if purchase.status == "completed":
        return "already_completed"

    values = {Purchase.status: "completed"}
    if event_id:
        values[Purchase.stripe_event_id] = event_id
    claimed = (db.query(Purchase)
               .filter(Purchase.id == purchase.id, Purchase.status != "completed")
               .update(values, synchronize_session=False))
    if not claimed:
        # Another concurrent caller already claimed and granted this purchase.
        db.rollback()
        return "already_completed"

    granted = grant_credits(db, purchase.profile_id, purchase.credits,
                            reason="purchase", note=f"pack {purchase.price_id}",
                            commit=False)
    if granted is None:
        db.rollback()  # also reverts the status claim — purchase stays pending
        logger.error("fulfill: no account for profile %s", purchase.profile_id)
        return "no_account"
    db.commit()
    return "ok"


@router.get("/verify")
def verify(session_id: str, db: Session = Depends(get_db),
           profile_id: int = Depends(current_profile_id)):
    """Fallback fulfillment on the success redirect — covers the local case where
    Stripe's webhook can't reach localhost, and delayed/missed webhooks in prod.
    Confirms payment with Stripe before granting; idempotent with the webhook."""
    try:
        session = stripe_client.retrieve_checkout_session(session_id)
    except Exception:
        logger.exception("verify: retrieve session failed")
        raise HTTPException(status_code=502, detail="payment provider error")

    status = (session.get("payment_status") if hasattr(session, "get")
              else getattr(session, "payment_status", None))
    if status != "paid":
        return {"status": "unpaid"}

    purchase = db.query(Purchase).filter_by(stripe_session_id=session_id).first()
    if purchase is not None and purchase.profile_id != profile_id:
        raise HTTPException(status_code=403, detail="not your purchase")
    return {"status": _fulfill(db, session_id)}


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

    obj = event.data.object
    session_id = obj.get("id") if hasattr(obj, "get") else getattr(obj, "id", None)
    if not session_id:
        logger.error("webhook: completed event missing session id")
        return {"status": "bad_payload"}

    return {"status": _fulfill(db, session_id, event_id=event.id)}
