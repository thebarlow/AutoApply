"""Prepaid fixed-price credit ledger: grants, atomic debits, refunds.

Actions have fixed integer credit prices (see ``core/pricing.py``); this module
no longer converts raw LLM cost to credits. The ``credit_ledger`` table is the
source of truth; ``account.credit_balance`` is a cached denormalization updated
in the same transaction as each ledger row. Billing acts on the Account row
matching a tenant's ``profile_id``; if there is no such row (local/dev/tests
without auth), grants/debits are no-ops.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from db.database import Account, CreditLedger

CREDITS_PER_DOLLAR = 1000


class InsufficientCredits(Exception):
    """Raised by the prepaid gate when balance < the action's price."""

    def __init__(self, balance: int, price: int, action: str = ""):
        self.balance = balance
        self.price = price
        self.action = action
        super().__init__(f"insufficient credits: {balance} < {price} ({action})")


def default_rate() -> float:
    return float(os.getenv("CREDIT_DEFAULT_RATE", "1.0"))


def signup_grant_for_tier(tier: str) -> int:
    defaults = {"standard": 20, "friends_family": 50, "beta": 200}
    raw = os.getenv("CREDIT_SIGNUP_GRANTS", "").strip()
    table = {**defaults, **json.loads(raw)} if raw else defaults
    return int(table.get(tier, table["standard"]))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_account_for_profile(db: Session, profile_id: int) -> Account | None:
    return db.query(Account).filter_by(profile_id=profile_id).first()


def grant_credits(db: Session, profile_id: int, amount: int, reason: str, *,
                  created_by: int | None = None, note: str | None = None,
                  commit: bool = True) -> CreditLedger | None:
    """Insert a positive ledger row and bump the cached balance atomically.

    If ``commit`` is False, the ledger row and balance bump are added to the
    session but not committed, letting the caller fold them into a larger
    atomic transaction.
    """
    acct = get_account_for_profile(db, profile_id)
    if acct is None:
        return None
    row = CreditLedger(profile_id=profile_id, delta=amount, reason=reason,
                       meta=json.dumps({"note": note}) if note else None,
                       created_by=created_by, created_at=_now())
    db.add(row)
    acct.credit_balance = (acct.credit_balance or 0) + amount
    if commit:
        db.commit()
    return row


def debit_fixed(db: Session, profile_id: int, *, action: str, job_key: str | None,
                price: int) -> CreditLedger:
    """Atomically gate and debit a fixed price.

    One conditional UPDATE guards the gate: concurrent actions cannot overdraw
    because only updates that still satisfy ``credit_balance >= price`` match.
    """
    matched = (
        db.query(Account)
        .filter(Account.profile_id == profile_id, Account.credit_balance >= price)
        .update({Account.credit_balance: Account.credit_balance - price},
                synchronize_session=False)
    )
    if matched != 1:
        db.rollback()
        acct = get_account_for_profile(db, profile_id)
        raise InsufficientCredits(
            (acct.credit_balance or 0) if acct else 0, price, action)
    row = CreditLedger(profile_id=profile_id, delta=-price, reason="debit",
                       action=action, job_key=job_key, created_at=_now())
    db.add(row)
    db.commit()
    return row


def refund_debit(db: Session, debit_row: CreditLedger) -> CreditLedger:
    """Offset a debit after the action failed; restores the balance."""
    price = -debit_row.delta
    row = CreditLedger(profile_id=debit_row.profile_id, delta=price,
                       reason="refund", action=debit_row.action,
                       job_key=debit_row.job_key, created_at=_now())
    db.add(row)
    acct = get_account_for_profile(db, debit_row.profile_id)
    if acct is not None:
        acct.credit_balance = (acct.credit_balance or 0) + price
    db.commit()
    return row


def reconcile_balance(db: Session, profile_id: int) -> int:
    """Recompute the cached balance from the ledger SUM and persist it."""
    total = db.query(func.coalesce(func.sum(CreditLedger.delta), 0)).filter_by(
        profile_id=profile_id).scalar()
    acct = get_account_for_profile(db, profile_id)
    if acct is not None:
        acct.credit_balance = int(total)
        db.commit()
    return int(total)
