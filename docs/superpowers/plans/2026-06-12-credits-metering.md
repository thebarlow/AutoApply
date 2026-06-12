# Credits & Metering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every tenant a cost-backed credit balance that LLM actions debit, blocking metered actions when balance is below a floor, with signup + admin grants and a dev view of the OpenRouter key balance.

**Architecture:** A new append-only `credit_ledger` table is the source of truth; `account` carries a cached `credit_balance` and a per-account `credit_rate` multiplier. All LLM calls already funnel through `call_llm` in `core/llm.py`, which records each call's real `usage.cost` into a `metering` contextvar. A `meter_action()` context manager at the router/pipeline layer gates on balance, runs the action (sub-calls accrue cost), then settles one debit ledger row. Grants (signup, admin, later Stripe) all go through one `grant_credits()` helper.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / Alembic / Postgres (SQLite in tests) / React (dashboard). Tests: pytest.

**Conversion:** `debit_credits = round(raw_cost_usd × credit_rate × 1000)` (1000 credits = $1). Tiers: dev `0`, F&F `1.5`, customer `10.0`. Signup grant `100` (=$0.10). Floor `10`.

---

## File Structure

- `db/database.py` — add `CreditLedger` model; add `credit_balance`, `credit_rate` columns to `Account`.
- `alembic/versions/<rev>_add_credits.py` — new migration (create table + add columns).
- `core/credits.py` — NEW. Config readers, `InsufficientCredits`, `to_credits`, account lookup, `grant_credits`, `debit_for_action`, `reconcile_balance`.
- `core/metering.py` — NEW. `metering` contextvar, `record_call`, `meter_action` context manager.
- `core/llm.py` — `call_llm` records each call into the meter.
- `web/auth/identity.py` — signup grant in `_provision_account`.
- `web/routers/credits.py` — NEW. `GET /api/credits`, `POST /api/admin/credits/grant`, `GET /api/admin/system-balance`; admin dependency; 402 exception handler registration.
- `web/main.py` — register the credits router + the `InsufficientCredits` exception handler.
- `web/routers/jobs.py`, `web/intake_pipeline.py` — wrap metered call sites in `meter_action`.
- `react-dashboard/src/` — balance display, 402 out-of-credits signal, dev system-balance panel.
- Tests under `tests/core/` and `tests/web/`.

**Account lookup convention:** metering/billing acts on the `Account` row whose `profile_id` matches the active tenant. If no `Account` row exists for a `profile_id` (local dev / tray / tests without auth), metering is a **no-op** (no gate, no debit) — billing only engages in the authenticated hosted world. Tests that exercise debiting create an `Account` row explicitly.

---

## Task 1: DB model — CreditLedger + Account columns

**Files:**
- Modify: `db/database.py`
- Test: `tests/db/test_credit_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/db/test_credit_models.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.database import Base, Account, CreditLedger


def _session():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def test_account_has_credit_columns():
    db = _session()
    acct = Account(email="a@b.c", is_admin=False, profile_id=1,
                   created_at="now", credit_balance=100, credit_rate=1.5)
    db.add(acct)
    db.commit()
    got = db.query(Account).filter_by(profile_id=1).first()
    assert got.credit_balance == 100
    assert got.credit_rate == 1.5


def test_credit_ledger_row_roundtrips():
    db = _session()
    row = CreditLedger(profile_id=1, delta=-7, reason="debit", action="generate",
                       job_key="job-1", raw_cost_usd=0.0046, meta='{"model":"x"}',
                       created_at="now")
    db.add(row)
    db.commit()
    got = db.query(CreditLedger).first()
    assert got.delta == -7
    assert got.reason == "debit"
    assert got.profile_id == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/db/test_credit_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'CreditLedger'`.

- [ ] **Step 3: Add the model and columns**

In `db/database.py`, add `Float` to the `sqlalchemy` import line (alongside `Integer`, `String`, etc.). Add two columns to `Account` (after `created_at`):

```python
    credit_balance = Column(Integer, nullable=False, default=0)
    credit_rate = Column(Float, nullable=False, default=1.5)
```

Add a new model after `Identity`:

```python
class CreditLedger(Base):
    """Append-only credit ledger: the reconcilable source of truth for balances.

    One row per grant or debit. Never updated or deleted. ``account.credit_balance``
    is a cached denormalization kept in step via the same transaction.
    """

    __tablename__ = "credit_ledger"

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, nullable=False, index=True)
    delta = Column(Integer, nullable=False)            # +grant / -debit
    reason = Column(String, nullable=False)            # signup_grant|admin_grant|debit|adjustment
    action = Column(String, nullable=True)             # debits: score|generate|refine|eval|extract
    job_key = Column(String, nullable=True)
    raw_cost_usd = Column(Float, nullable=True)
    meta = Column(Text, nullable=True)                 # JSON: model, tokens, calls
    created_by = Column(Integer, nullable=True)        # account id for admin grants
    created_at = Column(String, nullable=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/db/test_credit_models.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add db/database.py tests/db/test_credit_models.py
git commit -m "feat: add CreditLedger model and Account credit columns"
```

---

## Task 2: Alembic migration

**Files:**
- Create: `alembic/versions/<rev>_add_credits.py` (generate the revision, then edit)

- [ ] **Step 1: Autogenerate the revision skeleton**

Run: `python -m alembic revision -m "add credits"`
Expected: prints `Generating .../alembic/versions/<hash>_add_credits.py ... done`. Note the new file path.

- [ ] **Step 2: Fill in the migration body**

Replace the generated `upgrade`/`downgrade` with (keep the auto-filled `revision`/`down_revision` header — `down_revision` must be the current head `bdf3f4523095`):

```python
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column("account", sa.Column("credit_balance", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("account", sa.Column("credit_rate", sa.Float(), nullable=False, server_default="1.5"))
    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=True),
        sa.Column("job_key", sa.String(), nullable=True),
        sa.Column("raw_cost_usd", sa.Float(), nullable=True),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_credit_ledger_profile_id", "credit_ledger", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_credit_ledger_profile_id", table_name="credit_ledger")
    op.drop_table("credit_ledger")
    op.drop_column("account", "credit_rate")
    op.drop_column("account", "credit_balance")
```

- [ ] **Step 3: Apply and verify the migration round-trips**

Run: `python -m alembic upgrade head && python -m alembic downgrade -1 && python -m alembic upgrade head`
Expected: each command exits 0 with no error. (Uses the local SQLite `auto_apply.db` unless `DATABASE_URL` is set.)

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "feat: alembic migration for credit_ledger and account credit columns"
```

---

## Task 3: core/credits.py — conversion, grants, debits

**Files:**
- Create: `core/credits.py`
- Test: `tests/core/test_credits.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_credits.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.database import Base, Account, CreditLedger
import core.credits as credits


def _session():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _acct(db, profile_id=1, rate=1.5, balance=0):
    a = Account(email=f"u{profile_id}@x.c", is_admin=False, profile_id=profile_id,
                created_at="now", credit_balance=balance, credit_rate=rate)
    db.add(a); db.commit(); return a


def test_to_credits_rounds():
    assert credits.to_credits(0.0046, 1.5) == 7      # 0.0046*1.5*1000=6.9 -> 7
    assert credits.to_credits(0.0046, 10.0) == 46
    assert credits.to_credits(0.0046, 0) == 0


def test_grant_credits_inserts_row_and_bumps_balance():
    db = _session(); _acct(db, balance=0)
    credits.grant_credits(db, 1, 100, reason="signup_grant")
    assert db.query(Account).filter_by(profile_id=1).first().credit_balance == 100
    row = db.query(CreditLedger).filter_by(reason="signup_grant").first()
    assert row.delta == 100


def test_debit_for_action_decrements_and_logs():
    db = _session(); _acct(db, rate=1.5, balance=100)
    row = credits.debit_for_action(db, 1, action="generate", job_key="j1",
                                   raw_cost_usd=0.0046, meta={"model": "x"})
    assert row.delta == -7
    assert db.query(Account).filter_by(profile_id=1).first().credit_balance == 93


def test_debit_noop_without_account():
    db = _session()  # no account row for profile 1
    assert credits.debit_for_action(db, 1, action="generate", job_key="j1",
                                    raw_cost_usd=0.005, meta={}) is None


def test_reconcile_balance_matches_ledger_sum():
    db = _session(); _acct(db, balance=0)
    credits.grant_credits(db, 1, 100, reason="admin_grant")
    credits.debit_for_action(db, 1, action="score", job_key="j", raw_cost_usd=0.01, meta={})
    assert credits.reconcile_balance(db, 1) == db.query(Account).filter_by(profile_id=1).first().credit_balance
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_credits.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.credits'`.

- [ ] **Step 3: Implement core/credits.py**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_credits.py -v`
Expected: PASS (all five tests).

- [ ] **Step 5: Commit**

```bash
git add core/credits.py tests/core/test_credits.py
git commit -m "feat: credit ledger conversion, grants, debits, reconcile"
```

---

## Task 4: core/metering.py — meter contextvar + meter_action

**Files:**
- Create: `core/metering.py`
- Test: `tests/core/test_metering.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_metering.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.database import Base, Account, CreditLedger
import core.metering as metering
from core.credits import InsufficientCredits


def _db_with_account(rate=1.5, balance=100):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    db.add(Account(email="u@x.c", is_admin=False, profile_id=1, created_at="now",
                   credit_balance=balance, credit_rate=rate))
    db.commit()
    return db


def test_records_accumulate_and_settle_to_one_debit():
    db = _db_with_account(rate=1.5, balance=100)
    with metering.meter_action(db, 1, action="generate", job_key="j1", floor=10):
        metering.record_call(0.002, "modelA", 100, 50)
        metering.record_call(0.0026, "modelB", 80, 40)  # total 0.0046
    rows = db.query(CreditLedger).filter_by(reason="debit").all()
    assert len(rows) == 1
    assert rows[0].delta == -7          # 0.0046*1.5*1000 = 6.9 -> 7
    assert db.query(Account).first().credit_balance == 93


def test_gate_blocks_below_floor_before_any_call():
    db = _db_with_account(balance=5)
    with pytest.raises(InsufficientCredits):
        with metering.meter_action(db, 1, action="generate", job_key="j1", floor=10):
            pytest.fail("body should not run when gated")


def test_rate_zero_skips_gate_and_debit():
    db = _db_with_account(rate=0.0, balance=0)
    with metering.meter_action(db, 1, action="generate", job_key="j1", floor=10):
        metering.record_call(0.05, "modelA", 100, 50)
    assert db.query(CreditLedger).filter_by(reason="debit").count() == 0


def test_settles_cost_even_when_action_raises():
    db = _db_with_account(rate=1.5, balance=100)
    with pytest.raises(ValueError):
        with metering.meter_action(db, 1, action="generate", job_key="j1", floor=10):
            metering.record_call(0.0046, "modelA", 100, 50)
            raise ValueError("boom")
    assert db.query(CreditLedger).filter_by(reason="debit").count() == 1


def test_record_call_outside_meter_is_noop():
    metering.record_call(0.01, "m", 1, 1)  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_metering.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.metering'`.

- [ ] **Step 3: Implement core/metering.py**

```python
"""Action-level LLM metering.

A ``meter_action`` context manager gates on the tenant's credit balance, opens a
per-action accumulator (a contextvar), runs the action — every ``call_llm``
sub-call appends its real cost via ``record_call`` — then settles one debit
ledger row from the summed cost. Outside an active meter, ``record_call`` is a
no-op so local/dev/tray runs are unaffected.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy.orm import Session

from core.credits import (
    InsufficientCredits,
    credit_floor,
    debit_for_action,
    get_account_for_profile,
)

_meter: ContextVar[list | None] = ContextVar("_meter", default=None)


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
    metered = acct is not None and (acct.credit_rate or 0.0) > 0
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
            debit_for_action(db, profile_id, action=action, job_key=job_key,
                             raw_cost_usd=total, meta=meta)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_metering.py -v`
Expected: PASS (all five tests).

- [ ] **Step 5: Commit**

```bash
git add core/metering.py tests/core/test_metering.py
git commit -m "feat: meter_action context manager with gate and settle"
```

---

## Task 5: Wire call_llm into the meter

**Files:**
- Modify: `core/llm.py:74-83`
- Test: `tests/core/test_llm_metering.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_llm_metering.py
from types import SimpleNamespace
import core.metering as metering
import core.llm as llm


class _FakeClient:
    def __init__(self, cost):
        usage = SimpleNamespace(cost=cost, prompt_tokens=10, completion_tokens=5)
        msg = SimpleNamespace(content="hi")
        choice = SimpleNamespace(message=msg, finish_reason="stop")
        self._resp = SimpleNamespace(usage=usage, choices=[choice])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **k: self._resp))


def test_call_llm_records_into_active_meter(monkeypatch):
    captured = []
    monkeypatch.setattr(metering, "_meter", metering._meter)
    token = metering._meter.set(captured)
    try:
        out = llm.call_llm("p", _FakeClient(0.0033), "modelZ")
    finally:
        metering._meter.reset(token)
    assert out == "hi"
    assert len(captured) == 1
    assert captured[0]["cost"] == 0.0033
    assert captured[0]["model"] == "modelZ"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_llm_metering.py -v`
Expected: FAIL — `assert len(captured) == 1` is `0` (call_llm does not record yet).

- [ ] **Step 3: Add the record_call hook**

In `core/llm.py`, inside `call_llm`, after the existing `session_cost.add_cost(...)` block, add the meter record. The block currently reads:

```python
    usage = getattr(response, "usage", None)
    if usage is not None:
        session_cost.add_cost(float(getattr(usage, "cost", None) or 0.0))
```

Replace it with:

```python
    usage = getattr(response, "usage", None)
    if usage is not None:
        cost = float(getattr(usage, "cost", None) or 0.0)
        session_cost.add_cost(cost)
        from core import metering
        metering.record_call(
            cost, model,
            int(getattr(usage, "prompt_tokens", 0) or 0),
            int(getattr(usage, "completion_tokens", 0) or 0),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/core/test_llm_metering.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/llm.py tests/core/test_llm_metering.py
git commit -m "feat: call_llm records cost into the active meter"
```

---

## Task 6: Signup grant on account provisioning

**Files:**
- Modify: `web/auth/identity.py:110-120` (`_provision_account`)
- Test: `tests/web/test_signup_grant.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_signup_grant.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.database import Base, Account, CreditLedger
from core.user import User
import web.auth.identity as identity


def _db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    db.add(User(id=1, name="T", data="{}")); db.commit()
    return db


def test_provision_account_grants_signup_credits(monkeypatch):
    db = _db()
    monkeypatch.setenv("CREDIT_SIGNUP_GRANT", "100")
    claims = identity.Claims(provider="google", subject="sub-1", email="new@x.c")
    acct = identity._provision_account(db, email="new@x.c", is_admin=False, claims=claims)
    assert acct.credit_balance == 100
    grant = db.query(CreditLedger).filter_by(reason="signup_grant", profile_id=acct.profile_id).first()
    assert grant is not None and grant.delta == 100
```

> If `identity.Claims` has a different constructor signature, adapt the test's `Claims(...)` call to match the real dataclass in `web/auth/identity.py` (check its fields first). The behavior under test is unchanged.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_signup_grant.py -v`
Expected: FAIL — `assert acct.credit_balance == 100` sees `0`.

- [ ] **Step 3: Add the grant + default rate to provisioning**

In `web/auth/identity.py`, at the top add `from core.credits import grant_credits, default_rate, signup_grant_amount`. In `_provision_account`, set the rate when constructing the account and grant after commit:

```python
def _provision_account(db: Session, *, email: str, is_admin: bool, claims: Claims) -> Account:
    profile_id = _profile_for_new_account(db, is_admin)
    acct = Account(email=email, is_admin=is_admin, profile_id=profile_id,
                   created_at=_now(), credit_rate=0.0 if is_admin else default_rate())
    db.add(acct)
    db.flush()
    db.add(Identity(
        account_id=acct.id, provider=claims.provider,
        provider_subject=claims.subject, created_at=_now(),
    ))
    db.commit()
    grant_credits(db, profile_id, signup_grant_amount(), reason="signup_grant")
    return acct
```

(Admins get rate `0` — free + ungated, consistent with the dev tier.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_signup_grant.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/auth/identity.py tests/web/test_signup_grant.py
git commit -m "feat: grant signup credits and set tier rate on account provisioning"
```

---

## Task 7: Credits router — balance, admin grant, system balance

**Files:**
- Create: `web/routers/credits.py`
- Modify: `web/main.py` (register router + exception handler)
- Test: `tests/web/test_credits_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_credits_api.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, get_db
import core.user  # noqa: F401
from core.user import User
from web.main import app
from web.tenancy import current_profile_id
import core.credits as credits


@pytest.fixture
def db_session():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    s.add(User(id=1, name="T", data="{}"))
    s.add(Account(email="u@x.c", is_admin=False, profile_id=1, created_at="now",
                  credit_balance=100, credit_rate=1.5))
    s.add(Account(email="admin@x.c", is_admin=True, profile_id=2, created_at="now",
                  credit_balance=0, credit_rate=0.0))
    s.add(User(id=2, name="A", data="{}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[current_profile_id] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_credits_returns_balance(client):
    r = client.get("/api/credits")
    assert r.status_code == 200
    assert r.json()["balance"] == 100
    assert r.json()["rate"] == 1.5


def test_admin_grant_requires_admin(client):
    # active profile 1 is not admin
    r = client.post("/api/admin/credits/grant", json={"profile_id": 1, "amount": 50})
    assert r.status_code == 403


def test_admin_grant_credits(client, db_session):
    app.dependency_overrides[current_profile_id] = lambda: 2  # admin tenant
    r = client.post("/api/admin/credits/grant", json={"profile_id": 1, "amount": 50, "note": "topup"})
    assert r.status_code == 200
    assert db_session.query(Account).filter_by(profile_id=1).first().credit_balance == 150
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_credits_api.py -v`
Expected: FAIL — 404 on `/api/credits` (router not registered).

- [ ] **Step 3: Implement the router**

Create `web/routers/credits.py`:

```python
"""Credit balance, admin grants, and the dev system-balance view."""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import Account, CreditLedger, get_db
from core.credits import grant_credits
from web.tenancy import current_profile_id

router = APIRouter(prefix="/api", tags=["credits"])


def require_admin(request: Request, db: Session = Depends(get_db),
                  profile_id: int = Depends(current_profile_id)) -> Account:
    """Resolve the active account and ensure it is an admin."""
    acct = db.query(Account).filter_by(profile_id=profile_id).first()
    if acct is None or not acct.is_admin:
        raise HTTPException(status_code=403, detail="admin only")
    return acct


@router.get("/credits")
def get_credits(db: Session = Depends(get_db), profile_id: int = Depends(current_profile_id)):
    acct = db.query(Account).filter_by(profile_id=profile_id).first()
    if acct is None:
        return {"balance": 0, "rate": 0.0, "recent": []}
    recent = (db.query(CreditLedger).filter_by(profile_id=profile_id)
              .order_by(CreditLedger.id.desc()).limit(20).all())
    return {
        "balance": acct.credit_balance or 0,
        "rate": acct.credit_rate or 0.0,
        "recent": [
            {"delta": r.delta, "reason": r.reason, "action": r.action,
             "job_key": r.job_key, "created_at": r.created_at}
            for r in recent
        ],
    }


class GrantRequest(BaseModel):
    profile_id: int | None = None
    email: str | None = None
    amount: int
    note: str | None = None


@router.post("/admin/credits/grant")
def admin_grant(body: GrantRequest, db: Session = Depends(get_db),
                admin: Account = Depends(require_admin)):
    target_pid = body.profile_id
    if target_pid is None and body.email:
        tgt = db.query(Account).filter_by(email=body.email).first()
        if tgt is None:
            raise HTTPException(status_code=404, detail="account not found")
        target_pid = tgt.profile_id
    if target_pid is None:
        raise HTTPException(status_code=400, detail="profile_id or email required")
    row = grant_credits(db, target_pid, body.amount, reason="admin_grant",
                        created_by=admin.id, note=body.note)
    if row is None:
        raise HTTPException(status_code=404, detail="target account not found")
    bal = db.query(Account).filter_by(profile_id=target_pid).first().credit_balance
    return {"granted": body.amount, "balance": bal}


@router.get("/admin/system-balance")
def system_balance(admin: Account = Depends(require_admin)):
    """Remaining balance on the platform OpenRouter key (money in the system)."""
    key = os.getenv("LLM_API_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="no platform key")
    try:
        resp = httpx.get("https://openrouter.ai/api/v1/credits",
                         headers={"Authorization": f"Bearer {key}"}, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        total = float(data.get("total_credits", 0))
        used = float(data.get("total_usage", 0))
        return {"total": total, "used": used, "remaining": total - used}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"openrouter error: {exc}")
```

In `web/main.py`: import and register the router alongside the others (match the existing `app.include_router(...)` style), and register the 402 handler:

```python
from core.credits import InsufficientCredits
from fastapi.responses import JSONResponse

@app.exception_handler(InsufficientCredits)
async def _insufficient_credits_handler(request, exc: InsufficientCredits):
    return JSONResponse(status_code=402,
                        content={"error": "insufficient_credits",
                                 "balance": exc.balance, "floor": exc.floor})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_credits_api.py -v`
Expected: PASS (all three tests).

- [ ] **Step 5: Verify httpx is available**

Run: `python -c "import httpx; print(httpx.__version__)"`
Expected: prints a version. If `ModuleNotFoundError`, add `httpx` to `requirements.txt` and `pip install httpx` into the active `.venv` (httpx is a FastAPI/Starlette test dependency and is usually already present).

- [ ] **Step 6: Commit**

```bash
git add web/routers/credits.py web/main.py tests/web/test_credits_api.py requirements.txt
git commit -m "feat: credits router (balance, admin grant, system balance) + 402 handler"
```

---

## Task 8: Gate + meter the metered call sites

**Files:**
- Modify: `web/routers/jobs.py` (score `:241`, generate resume `:275`, generate cover `:290`, extract `:631`)
- Modify: `web/intake_pipeline.py` (score `:58`, extract `:76`, eval `:238`/`:460`)
- Test: `tests/web/test_metered_endpoints.py`

> Read each call site first (line numbers drift). Each metered call already has `db` and a `profile_id` in scope (via `current_profile_id` or a passed `profile_id`). Wrap only the LLM-driven call, not surrounding bookkeeping.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_metered_endpoints.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.database import Base, Account, get_db
import core.user  # noqa: F401
from core.user import User
from core.job import Job, JobState
from web.main import app
from web.tenancy import current_profile_id


@pytest.fixture
def db_session():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    s.add(User(id=1, name="T", data="{}"))
    s.add(Account(email="u@x.c", is_admin=False, profile_id=1, created_at="now",
                  credit_balance=5, credit_rate=1.5))  # below floor 10
    s.add(Job(job_key="j1", profile_id=1, source="indeed", state=JobState.NEW,
              title="T", company="C", description="d"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[current_profile_id] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_generate_blocked_when_below_floor(client, monkeypatch):
    monkeypatch.setenv("CREDIT_FLOOR", "10")
    r = client.post("/api/jobs/j1/generate/resume")  # adjust path to the real generate route
    assert r.status_code == 402
    assert r.json()["error"] == "insufficient_credits"
```

> Adjust the request path/method to the actual generate-resume route in `web/routers/jobs.py` (read it first). The assertion — a 402 with `error: insufficient_credits` when below floor — is what matters.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/web/test_metered_endpoints.py -v`
Expected: FAIL — generate returns 200 (no gate yet).

- [ ] **Step 3: Wrap the call sites**

Add `from core.metering import meter_action` to both files. Wrap each metered call. Examples:

`web/routers/jobs.py` — generate resume (around `:275`):

```python
    with meter_action(db, profile_id, action="generate", job_key=job.job_key):
        job.generate_resume_md(user, prompt_content, client, model, db)
```

generate cover (around `:290`):

```python
    with meter_action(db, profile_id, action="generate", job_key=job.job_key):
        job.generate_cover_md(user, prompt_content, client, model, db)
```

score (around `:241`):

```python
    with meter_action(db, profile_id, action="score", job_key=job.job_key):
        job.score(user, config, client, model, db, prompt_content)
```

extract — wrap the body of `_do_extract_description` (around `:577-631`) so both the route and the pipeline path are covered:

```python
def _do_extract_description(job: Job, db: Session, profile_id: int) -> None:
    with meter_action(db, profile_id, action="extract", job_key=job.job_key):
        ...  # existing body
```

`web/intake_pipeline.py` — score (around `:58`):

```python
    with meter_action(db, profile_id, action="score", job_key=job.job_key):
        job.score(user, config, client, model, db, prompt_content)
```

eval (around `:238` and `:460`) — wrap each `evaluate_fn(...)` call:

```python
    with meter_action(db, profile_id, action="eval", job_key=job.job_key):
        result = evaluate_fn(eval_prompt, user, eval_client, resolved_eval_model)
```

(The `_do_extract_description` wrap already covers the pipeline's extract at `:76`; do not double-wrap it.)

refine — the auto-refine machinery (`run_resume_refinement`/`run_cover_refinement`/`run_user_feedback_refine`) runs in background threads with their own `SessionLocal` and a passed `profile_id`. Wrap the refine LLM loop in each `run_*` entry point: `with meter_action(db, profile_id, action="refine", job_key=job_key):`. Read those functions (search `def run_resume_refinement` / `def run_user_feedback_refine` in `web/intake_pipeline.py`) and wrap the section that calls the model, using the function's own `db`/`profile_id`. Background refine is not gated by a route, so a below-floor user is stopped earlier at the generate gate; the wrap here is for the debit, which is why settle-on-error matters.

Confirm `profile_id` is in scope at each site; in `web/routers/jobs.py` routes it comes from `Depends(current_profile_id)` — add the dependency to any metered route that lacks it.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/web/test_metered_endpoints.py -v`
Expected: PASS (402 when below floor).

- [ ] **Step 5: Run the full backend suite for regressions**

Run: `python -m pytest tests/web tests/core -q`
Expected: PASS. Existing tests use `profile_id=1` with no Account row, so metering is a no-op there — no behavior change.

- [ ] **Step 6: Commit**

```bash
git add web/routers/jobs.py web/intake_pipeline.py tests/web/test_metered_endpoints.py
git commit -m "feat: gate and meter score/generate/refine/eval/extract actions"
```

---

## Task 9: Frontend — balance display, out-of-credits signal, dev panel

**Files:**
- Modify: a shared API helper + the navbar/User tab (read `react-dashboard/CONTEXT.md` for exact files)
- Create: `react-dashboard/src/components/widgets/CreditBalance.jsx`

> Frontend has no unit-test harness here; verify manually in the running app. Keep changes small and follow existing component patterns.

- [ ] **Step 1: Add a credits fetch + balance widget**

Create `CreditBalance.jsx` that calls `GET /api/credits` on mount and renders `balance` (e.g. "1,234 credits"). Place it in the navbar and the User/Settings tab. Refetch after any metered action completes (hook into the existing post-generate/score refresh, or expose a `refreshCredits()` callback).

- [ ] **Step 2: Handle 402 globally**

In the shared fetch/axios wrapper, detect `status === 402` with `body.error === "insufficient_credits"` and surface a clear modal/toast: "You're out of credits — contact the admin to top up." (becomes the buy-credits CTA after Payments). Do not let the action fail silently.

- [ ] **Step 3: Dev system-balance panel**

In the User/Settings tab, when the logged-in account is admin (`api_me` returns `is_admin: true`), render a small panel that calls `GET /api/admin/system-balance` and shows `remaining` as the OpenRouter money in the system. Hide it for non-admins.

- [ ] **Step 4: Manual verification**

Run the app (`start.bat` or the dev server). As a non-admin tenant with balance below the floor, attempt a generation → expect the out-of-credits modal and a 402 in the network tab. As an admin, confirm the system-balance panel shows a number. Confirm the navbar balance decrements after a successful generation.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src
git commit -m "feat: credit balance display, out-of-credits signal, dev system-balance panel"
```

---

## Task 10: Docs + CONTEXT updates

**Files:**
- Modify: `ARCHITECTURE.md`, `web/CONTEXT.md`, `core/CONTEXT.md`, `db/CONTEXT.md`, `TODO.md`

- [ ] **Step 1: Update docs**

- `ARCHITECTURE.md` — add a "Credits & Metering" subsection (ledger as source of truth, `meter_action` chokepoint, conversion formula, tier rates).
- `db/CONTEXT.md` — document the `credit_ledger` table and the two `account` columns.
- `core/CONTEXT.md` — document `core/credits.py` and `core/metering.py` and the `call_llm` meter hook.
- `web/CONTEXT.md` — document the credits router, the admin gate, the 402 handler, and which endpoints are metered.
- `TODO.md` — mark **(2) Credits & Metering** done; move to the Done section with a one-line summary; note Payments is now unblocked.

- [ ] **Step 2: Commit**

```bash
git add ARCHITECTURE.md db/CONTEXT.md core/CONTEXT.md web/CONTEXT.md TODO.md
git commit -m "docs: record Credits & Metering (ledger, metering, tiers)"
```

---

## Self-Review Notes

- **Spec coverage:** ledger + account columns (T1/T2), conversion + grants + debits + reconcile (T3), metering contextvar + action gate/settle + rate-0 skip + settle-on-error (T4), call_llm hook (T5), signup grant + admin rate (T6), `GET /api/credits` + admin grant + system-balance + 402 handler (T7), gate/meter all metered actions (T8), UI balance + 402 signal + dev panel (T9), docs (T10). All spec sections mapped.
- **Type consistency:** `grant_credits`, `debit_for_action`, `to_credits`, `get_account_for_profile`, `reconcile_balance`, `InsufficientCredits(balance, floor)`, `record_call(cost, model, prompt_tokens, completion_tokens)`, `meter_action(db, profile_id, *, action, job_key, floor)` are used identically across tasks.
- **Open verification during execution:** exact OpenRouter credits endpoint shape (`data.total_credits`/`total_usage`), the `Claims` dataclass fields, and the real generate-resume route path — each task notes where to confirm against live code.
```