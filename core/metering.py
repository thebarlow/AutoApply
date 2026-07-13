"""Action-level LLM metering.

A ``meter_action`` context manager gates on the tenant's credit balance, opens a
per-action accumulator (a contextvar), runs the action — every ``call_llm``
sub-call appends its real cost via ``record_call`` — then settles one debit
ledger row from the summed cost. Outside an active meter, ``record_call`` is a
no-op so local/dev/tray runs are unaffected.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy.orm import Session

from core.credits import (
    InsufficientCredits,
    credit_floor,
    debit_for_action,
    get_account_for_profile,
)

logger = logging.getLogger(__name__)

_meter: ContextVar[list | None] = ContextVar("_meter", default=None)


def _notify_credits_changed(profile_id: int) -> None:
    """Nudge the tenant's SSE clients to refetch their own balance.

    Best-effort: a broadcast failure must never affect billing. The payload
    carries no balance — each client refetches its own authenticated
    ``/api/credits`` instead of trusting a pushed figure. Scoped to the tenant
    that spent so the event never reaches other tenants' streams. Fixes the
    stale navbar balance after a spend.
    """
    try:
        from web.sse import send
        send("credits", {}, profile_id=profile_id)
    except Exception:
        logger.exception("credits-changed SSE notify failed")


def record_call(cost: float, model: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Append one LLM call's cost to the active meter, if any."""
    bucket = _meter.get()
    if bucket is None:
        return
    bucket.append({
        "cost": float(cost or 0.0),
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    })


@contextmanager
def meter_action(db: Session, profile_id: int, *, action: str,
                 job_key: str | None = None, floor: int | None = None):
    """Gate, meter, and settle a single billable action.

    - No Account row for this profile, or rate 0: run ungated, never debit.
    - Otherwise: balance < floor -> InsufficientCredits before the body runs.
    - On exit (success or error): debit the summed actual cost as one ledger row.
    """
    if floor is None:
        floor = credit_floor()
    acct = get_account_for_profile(db, profile_id)
    # Admins draw directly from the platform's system balance: never gated, never
    # debited, regardless of any stored credit_rate.
    metered = acct is not None and not acct.is_admin and (acct.credit_rate or 0.0) > 0
    if metered and (acct.credit_balance or 0) < floor:
        raise InsufficientCredits(acct.credit_balance or 0, floor)

    if not metered:
        yield
        return

    token = _meter.set([])
    try:
        yield
    finally:
        calls = _meter.get() or []
        _meter.reset(token)
        total = sum(c["cost"] for c in calls)
        if total > 0:
            meta = {"calls": len(calls), "models": [c["model"] for c in calls],
                    "prompt_tokens": sum(c["prompt_tokens"] for c in calls),
                    "completion_tokens": sum(c["completion_tokens"] for c in calls)}
            try:
                debit_for_action(db, profile_id, action=action, job_key=job_key,
                                 raw_cost_usd=total, meta=meta)
            except Exception:
                # Never let a settle failure mask the action's own outcome.
                # Roll back the half-applied debit; balance can be repaired via
                # reconcile_balance from the ledger later.
                logger.exception("credit settle failed for action=%s job=%s", action, job_key)
                db.rollback()
            else:
                _notify_credits_changed(profile_id)
