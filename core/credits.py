"""Cost-backed credit ledger: conversion, grants, debits, reconciliation.

The ``credit_ledger`` table is the source of truth; ``account.credit_balance``
is a cached denormalization updated in the same transaction as each ledger row.
Billing acts on the Account row matching a tenant's ``profile_id``; if there is
no such row (local/dev/tests without auth), grants/debits are no-ops.
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
    """Raised by the action gate when balance is below the floor."""

    def __init__(self, balance: int, floor: int):
        self.balance = balance
        self.floor = floor
        super().__init__(f"insufficient credits: {balance} < {floor}")


def default_rate() -> float:
    return float(os.getenv("CREDIT_DEFAULT_RATE", "1.5"))


def signup_grant_amount() -> int:
    return int(os.getenv("CREDIT_SIGNUP_GRANT", "100"))


def credit_floor() -> int:
    return int(os.getenv("CREDIT_FLOOR", "10"))


def to_credits(raw_cost_usd: float, rate: float) -> int:
    """Marked-up dollar cost converted to whole credits."""
    return round(raw_cost_usd * rate * CREDITS_PER_DOLLAR)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_account_for_profile(db: Session, profile_id: int) -> Account | None:
    return db.query(Account).filter_by(profile_id=profile_id).first()


def grant_credits(db: Session, profile_id: int, amount: int, reason: str, *,
                  created_by: int | None = None, note: str | None = None) -> CreditLedger | None:
    """Insert a positive ledger row and bump the cached balance atomically."""
    acct = get_account_for_profile(db, profile_id)
    if acct is None:
        return None
    row = CreditLedger(profile_id=profile_id, delta=amount, reason=reason,
                       meta=json.dumps({"note": note}) if note else None,
                       created_by=created_by, created_at=_now())
    db.add(row)
    acct.credit_balance = (acct.credit_balance or 0) + amount
    db.commit()
    return row


def debit_for_action(db: Session, profile_id: int, *, action: str, job_key: str | None,
                     raw_cost_usd: float, meta: dict) -> CreditLedger | None:
    """Insert a negative ledger row for an action's actual cost; decrement balance."""
    acct = get_account_for_profile(db, profile_id)
    if acct is None:
        return None
    amount = to_credits(raw_cost_usd, acct.credit_rate or 0.0)
    row = CreditLedger(profile_id=profile_id, delta=-amount, reason="debit",
                       action=action, job_key=job_key, raw_cost_usd=raw_cost_usd,
                       meta=json.dumps(meta), created_at=_now())
    db.add(row)
    acct.credit_balance = (acct.credit_balance or 0) - amount
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
