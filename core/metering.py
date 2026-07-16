"""Action-level LLM metering.

A ``meter_action`` context manager gates on the tenant's credit balance,
debits the action's fixed price upfront (before the body runs), opens a
per-action accumulator (a contextvar) so every ``call_llm`` sub-call can
append its real cost via ``record_call``, then on success annotates the
debit row with the observed cost for margin tracking. On failure the debit
is refunded. Outside an active meter, ``record_call`` is a no-op so
local/dev/tray runs are unaffected.
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy.orm import Session

from core.credits import (
    InsufficientCredits,
    debit_fixed,
    get_account_for_profile,
    refund_debit,
)
from core.pricing import price_for

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
                 job_key: str | None = None, price: int | None = None):
    """Prepaid gate + fixed debit for a single billable action.

    - No Account row, admin, or rate 0: run ungated, never debit (dev/tests).
    - Otherwise: atomically debit the action's fixed price before the body runs
      (InsufficientCredits if the balance can't cover it), refund on exception,
      and annotate the debit row with the summed actual LLM cost on success.
    """
    acct = get_account_for_profile(db, profile_id)
    metered = acct is not None and not acct.is_admin and (acct.credit_rate or 0.0) > 0
    if not metered:
        yield
        return

    debit_row = debit_fixed(db, profile_id, action=action, job_key=job_key,
                            price=price if price is not None else price_for(action))
    _notify_credits_changed(profile_id)
    token = _meter.set([])
    try:
        yield
    except BaseException:
        try:
            refund_debit(db, debit_row)
        except Exception:
            logger.exception("refund failed for action=%s job=%s", action, job_key)
            db.rollback()
        else:
            _notify_credits_changed(profile_id)
        raise
    finally:
        calls = _meter.get() or []
        _meter.reset(token)
    # Success: annotate the debit with observed cost for margin tracking.
    total = sum(c["cost"] for c in calls)
    if calls:
        try:
            debit_row.raw_cost_usd = total
            debit_row.meta = json.dumps({
                "calls": len(calls), "models": [c["model"] for c in calls],
                "prompt_tokens": sum(c["prompt_tokens"] for c in calls),
                "completion_tokens": sum(c["completion_tokens"] for c in calls)})
            db.commit()
        except Exception:
            logger.exception("cost annotation failed for action=%s job=%s", action, job_key)
            db.rollback()
