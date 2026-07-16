# Fixed-Unit Credit Pricing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace post-paid cost-passthrough LLM metering with fixed, prepaid, per-action unit prices (intake 2u, fresh doc 4u, regen 2u, small actions 1u), tiered signup grants, and unit-denominated packs.

**Architecture:** A new `core/pricing.py` owns the price card and the fresh-vs-regen resolver. `core/credits.py` gains an atomic conditional debit (`debit_fixed`) and `refund_debit`; `core/metering.py`'s `meter_action` becomes prepaid (gate+debit on enter, refund on exception, raw-cost annotation on success). Call sites are rewired so priced meters exist only at user-initiated boundaries; bundled sub-calls (post-generation eval/refine turns, post-generation ATS) run meter-free. An Alembic migration re-denominates balances (÷20) and tops up never-purchased accounts to their tier grant.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy (SQLite dev / Postgres prod), Alembic, pytest, React (Vite).

**Spec:** `docs/superpowers/specs/2026-07-15-fixed-unit-pricing-design.md`

## Global Constraints

- Prices (units): `intake=2`, `generate_fresh=4`, `regenerate=2`, `score=1`, `extract=1`, `resume_parse=1`, `ats=1`, `rematch=1`, `draft=1`. Each env-overridable as `PRICE_<ACTION_UPPERCASED>`.
- `UNIT_USD` default **0.02**, env var `CREDIT_UNIT_USD`.
- Signup grants: env JSON `CREDIT_SIGNUP_GRANTS`, default `{"standard": 20, "friends_family": 50, "beta": 200}`. Replaces flat `CREDIT_SIGNUP_GRANT`.
- Pack multipliers: env JSON `CREDIT_TIER_MULTIPLIERS`, default `{"standard": 1.0, "friends_family": 4.0, "beta": 10.0}`. Replaces `CREDIT_TIER_MARGINS` margins-on-cost math.
- Nothing that hits the LLM is free; fresh-vs-regen is derived server-side only.
- Admins (`is_admin`) and accounts with `credit_rate == 0` or no `Account` row stay fully unmetered (unchanged).
- Gate+debit must be one atomic conditional UPDATE (`credit_balance >= price`); balances can never go negative.
- Failed metered actions are refunded (`reason="refund"` ledger row).
- Commit format `[type] Imperative subject`; NO Claude/Anthropic attribution in commits.
- Run tests with `.\.venv\Scripts\python.exe -m pytest <path> -q` from the repo root (Windows).
- Pre-existing known-flaky test: `tests/scraper/test_runner.py::test_run_scraper_continues_on_source_error` fails in full-suite runs on main; ignore it.

---

### Task 1: `core/pricing.py` — price card + generate-action resolver

**Files:**
- Create: `core/pricing.py`
- Test: `tests/core/test_pricing.py`

**Interfaces:**
- Produces: `price_for(action: str) -> int` (raises `KeyError` on unknown action), `unit_usd() -> float`, `resolve_generate_action(db, job, doc_type: str) -> str` (returns `"generate_fresh"` or `"regenerate"`), `DEFAULT_PRICES: dict[str, int]`.

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_pricing.py
"""Price card + fresh-vs-regen resolver."""
import pytest

from core import pricing


def test_default_prices():
    assert pricing.price_for("intake") == 2
    assert pricing.price_for("generate_fresh") == 4
    assert pricing.price_for("regenerate") == 2
    for small in ("score", "extract", "resume_parse", "ats", "rematch", "draft"):
        assert pricing.price_for(small) == 1


def test_price_env_override(monkeypatch):
    monkeypatch.setenv("PRICE_GENERATE_FRESH", "7")
    assert pricing.price_for("generate_fresh") == 7


def test_unknown_action_raises():
    with pytest.raises(KeyError):
        pricing.price_for("nonsense")


def test_unit_usd_default_and_override(monkeypatch):
    assert pricing.unit_usd() == 0.02
    monkeypatch.setenv("CREDIT_UNIT_USD", "0.05")
    assert pricing.unit_usd() == 0.05


def _make_job(db, **kw):
    from core.job import Job
    job = Job(job_key="j1", profile_id=1, source="test", title="T",
              company="C", url="u", description="d", **kw)
    db.add(job)
    db.commit()
    return job


def test_resolver_fresh_when_no_document_or_path(db_session):
    job = _make_job(db_session)
    assert pricing.resolve_generate_action(db_session, job, "resume") == "generate_fresh"
    assert pricing.resolve_generate_action(db_session, job, "cover") == "generate_fresh"


def test_resolver_regen_when_document_row_exists(db_session):
    from db.database import Document
    job = _make_job(db_session)
    Document.upsert(db_session, "j1", "resume", "{}", profile_id=1)
    assert pricing.resolve_generate_action(db_session, job, "resume") == "regenerate"
    # cover has no row -> still fresh
    assert pricing.resolve_generate_action(db_session, job, "cover") == "generate_fresh"


def test_resolver_regen_when_output_path_set(db_session):
    job = _make_job(db_session, cover_path="C:/somewhere/out.pdf")
    assert pricing.resolve_generate_action(db_session, job, "cover") == "regenerate"
```

Note: `db_session` is the existing fixture pattern used across `tests/core/` (in-memory
SQLite with `Base.metadata.create_all`). If `tests/core/conftest.py` does not already
provide it, copy the fixture from `tests/core/test_metering.py`.

- [ ] **Step 2: Run tests — expect FAIL (`ModuleNotFoundError: core.pricing`)**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_pricing.py -q`

- [ ] **Step 3: Implement `core/pricing.py`**

```python
"""Fixed-unit price card for billable LLM actions.

One unit is worth ``unit_usd()`` dollars to buyers. Prices are integers in
units; each is env-overridable (``PRICE_<ACTION>``) so tuning needs no deploy.
See docs/superpowers/specs/2026-07-15-fixed-unit-pricing-design.md.
"""
from __future__ import annotations

import os
from typing import Any

DEFAULT_PRICES: dict[str, int] = {
    "intake": 2,          # pipeline bundle: score + extract + skill-match
    "generate_fresh": 4,  # first generation of a doc_type for a job
    "regenerate": 2,      # re-generate / feedback refine of an existing doc
    "score": 1,
    "extract": 1,
    "resume_parse": 1,
    "ats": 1,
    "rematch": 1,
    "draft": 1,
}


def price_for(action: str) -> int:
    """Units charged for one action. Raises KeyError for unknown actions —
    a call site naming a nonexistent action is a bug, not a free ride."""
    default = DEFAULT_PRICES[action]
    raw = os.getenv(f"PRICE_{action.upper()}", "").strip()
    return int(raw) if raw else default


def unit_usd() -> float:
    """Dollar value of one unit (what buyers pay)."""
    return float(os.getenv("CREDIT_UNIT_USD", "0.02"))


def resolve_generate_action(db: Any, job: Any, doc_type: str) -> str:
    """'generate_fresh' if this doc_type was never generated for the job,
    else 'regenerate'. Server-derived only: a Documents row or a stored
    output path counts as previously generated."""
    from db.database import Document

    if Document.fetch(db, job.job_key, doc_type, job.profile_id) is not None:
        return "regenerate"
    path = job.resume_path if doc_type == "resume" else job.cover_path
    return "regenerate" if path else "generate_fresh"
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_pricing.py -q`

- [ ] **Step 5: Commit**

```bash
git add core/pricing.py tests/core/test_pricing.py
git commit -m "[feat] Add fixed-unit price card and generate-action resolver"
```

---

### Task 2: `core/credits.py` — atomic prepaid debit, refund, tiered signup grants

**Files:**
- Modify: `core/credits.py`
- Test: `tests/core/test_credits.py` (extend), `tests/web/test_signup_grant.py` (update in Task 4)

**Interfaces:**
- Consumes: `pricing.price_for` (Task 1) — not directly; prices arrive as ints.
- Produces:
  - `InsufficientCredits(balance: int, price: int, action: str = "")` with attributes `.balance`, `.price`, `.action` (the old `.floor` attribute is REMOVED).
  - `debit_fixed(db, profile_id, *, action, job_key, price) -> CreditLedger` — atomic conditional debit; raises `InsufficientCredits`.
  - `refund_debit(db, debit_row) -> CreditLedger` — offsetting `reason="refund"` row.
  - `signup_grant_for_tier(tier: str) -> int`.
  - REMOVED: `credit_floor()`, `debit_for_action()`, `to_credits()`, `signup_grant_amount()`.
  - Kept unchanged: `grant_credits`, `reconcile_balance`, `get_account_for_profile`, `default_rate`, `CREDITS_PER_DOLLAR` (still used by the redenomination migration's ÷1000 conversion docs; keep the constant).

- [ ] **Step 1: Write failing tests (append to `tests/core/test_credits.py`)**

```python
def _acct(db, balance=10, rate=1.0, profile_id=1):
    from db.database import Account
    a = Account(profile_id=profile_id, email=f"u{profile_id}@x.com",
                created_at="now", credit_balance=balance, credit_rate=rate)
    db.add(a)
    db.commit()
    return a


def test_debit_fixed_success_writes_row_and_decrements(db_session):
    from core import credits
    _acct(db_session, balance=10)
    row = credits.debit_fixed(db_session, 1, action="score", job_key="j1", price=2)
    assert row.delta == -2 and row.reason == "debit" and row.action == "score"
    acct = credits.get_account_for_profile(db_session, 1)
    assert acct.credit_balance == 8


def test_debit_fixed_insufficient_raises_with_price_and_action(db_session):
    from core import credits
    _acct(db_session, balance=1)
    with pytest.raises(credits.InsufficientCredits) as ei:
        credits.debit_fixed(db_session, 1, action="generate_fresh", job_key="j1", price=4)
    assert ei.value.balance == 1
    assert ei.value.price == 4
    assert ei.value.action == "generate_fresh"
    # balance untouched
    assert credits.get_account_for_profile(db_session, 1).credit_balance == 1


def test_debit_fixed_exact_balance_passes(db_session):
    from core import credits
    _acct(db_session, balance=4)
    credits.debit_fixed(db_session, 1, action="generate_fresh", job_key="j1", price=4)
    assert credits.get_account_for_profile(db_session, 1).credit_balance == 0


def test_refund_debit_restores_balance(db_session):
    from core import credits
    _acct(db_session, balance=10)
    row = credits.debit_fixed(db_session, 1, action="regenerate", job_key="j1", price=2)
    refund = credits.refund_debit(db_session, row)
    assert refund.delta == 2 and refund.reason == "refund" and refund.action == "regenerate"
    assert credits.get_account_for_profile(db_session, 1).credit_balance == 10


def test_signup_grant_for_tier_defaults(monkeypatch):
    from core import credits
    monkeypatch.delenv("CREDIT_SIGNUP_GRANTS", raising=False)
    assert credits.signup_grant_for_tier("standard") == 20
    assert credits.signup_grant_for_tier("friends_family") == 50
    assert credits.signup_grant_for_tier("beta") == 200
    assert credits.signup_grant_for_tier("unknown_tier") == 20  # falls back to standard


def test_signup_grant_env_override(monkeypatch):
    from core import credits
    monkeypatch.setenv("CREDIT_SIGNUP_GRANTS", '{"standard": 5}')
    assert credits.signup_grant_for_tier("standard") == 5
```

- [ ] **Step 2: Run — expect FAIL (attributes/functions missing)**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_credits.py -q`

- [ ] **Step 3: Implement in `core/credits.py`**

Replace `InsufficientCredits`, delete `credit_floor`/`to_credits`/`debit_for_action`/`signup_grant_amount`, add:

```python
class InsufficientCredits(Exception):
    """Raised by the prepaid gate when balance < the action's price."""

    def __init__(self, balance: int, price: int, action: str = ""):
        self.balance = balance
        self.price = price
        self.action = action
        super().__init__(f"insufficient credits: {balance} < {price} ({action})")


def signup_grant_for_tier(tier: str) -> int:
    defaults = {"standard": 20, "friends_family": 50, "beta": 200}
    raw = os.getenv("CREDIT_SIGNUP_GRANTS", "").strip()
    table = {**defaults, **json.loads(raw)} if raw else defaults
    return int(table.get(tier, table["standard"]))


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
```

(Keep the module docstring accurate: update it to describe prepaid fixed pricing.)

- [ ] **Step 4: Run credits tests — expect PASS; expect `test_metering.py` and others to now FAIL on removed symbols (fixed in Tasks 3–5).**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_credits.py -q`

- [ ] **Step 5: Commit**

```bash
git add core/credits.py tests/core/test_credits.py
git commit -m "[feat] Add atomic prepaid debit, refund, and tiered signup grants to credit ledger"
```

---

### Task 3: `core/metering.py` — prepaid meter_action

**Files:**
- Modify: `core/metering.py`
- Test: `tests/core/test_metering.py` (rewrite the affected tests)

**Interfaces:**
- Consumes: `credits.debit_fixed`, `credits.refund_debit`, `credits.InsufficientCredits` (Task 2); `pricing.price_for` (Task 1).
- Produces: `meter_action(db, profile_id, *, action: str, job_key: str | None = None, price: int | None = None)` context manager. The old `floor=` kwarg is REMOVED. `record_call` unchanged. Unmetered accounts (no row / admin / rate 0) behave exactly as before.

- [ ] **Step 1: Rewrite `tests/core/test_metering.py` gate/settle tests**

Keep the fixture helper; replace tests that used `floor=` / cost-based debits with:

```python
def test_meter_debits_fixed_price_upfront(db_session):
    _acct(db_session, balance=10, rate=1.0)
    with metering.meter_action(db_session, 1, action="score", job_key="j1"):
        pass  # no LLM cost recorded
    from db.database import CreditLedger
    rows = db_session.query(CreditLedger).all()
    assert len(rows) == 1 and rows[0].delta == -1 and rows[0].reason == "debit"
    assert _balance(db_session) == 9


def test_meter_blocks_below_price(db_session):
    _acct(db_session, balance=3, rate=1.0)
    with pytest.raises(InsufficientCredits) as ei:
        with metering.meter_action(db_session, 1, action="generate_fresh", job_key="j1"):
            raise AssertionError("body must not run")
    assert ei.value.price == 4 and ei.value.balance == 3


def test_meter_refunds_on_body_exception(db_session):
    _acct(db_session, balance=10, rate=1.0)
    with pytest.raises(RuntimeError):
        with metering.meter_action(db_session, 1, action="regenerate", job_key="j1"):
            raise RuntimeError("llm blew up")
    from db.database import CreditLedger
    reasons = [r.reason for r in db_session.query(CreditLedger).all()]
    assert reasons == ["debit", "refund"]
    assert _balance(db_session) == 10


def test_meter_annotates_raw_cost_on_success(db_session):
    _acct(db_session, balance=10, rate=1.0)
    with metering.meter_action(db_session, 1, action="regenerate", job_key="j1"):
        metering.record_call(0.002, "modelA", 100, 50)
        metering.record_call(0.001, "modelB", 80, 40)
    from db.database import CreditLedger
    row = db_session.query(CreditLedger).filter_by(reason="debit").one()
    assert row.raw_cost_usd == pytest.approx(0.003)
    import json
    meta = json.loads(row.meta)
    assert meta["calls"] == 2 and meta["prompt_tokens"] == 180


def test_meter_explicit_price_overrides_card(db_session):
    _acct(db_session, balance=10, rate=1.0)
    with metering.meter_action(db_session, 1, action="score", job_key="j1", price=3):
        pass
    assert _balance(db_session) == 7


def test_unmetered_admin_and_rate_zero_pass_through(db_session):
    _acct(db_session, balance=0, rate=0.0)
    with metering.meter_action(db_session, 1, action="generate_fresh", job_key="j1"):
        metering.record_call(0.05, "m", 1, 1)
    from db.database import CreditLedger
    assert db_session.query(CreditLedger).count() == 0
```

Add `_balance(db)` helper: `credits.get_account_for_profile(db, 1).credit_balance`.
Delete tests that assert cost-based debit amounts / `floor` behavior; keep
`test_record_call_outside_meter_is_noop` and the `record_usage` feed tests, adjusting
their assertions to the annotate-on-success shape (debit is the fixed price; `raw_cost_usd`
carries the actual cost).

- [ ] **Step 2: Run — expect FAIL**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_metering.py -q`

- [ ] **Step 3: Rewrite `meter_action` in `core/metering.py`**

```python
from core.credits import InsufficientCredits, debit_fixed, get_account_for_profile, refund_debit
from core.pricing import price_for


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
```

Add `import json` at top. Note the success-path annotation runs AFTER the
`finally` (calls captured there), so move the annotation into the `finally` guarded
by an `exc`-tracking flag OR restructure exactly as above — the code above works
because the `except BaseException` re-raises, so lines after the try/finally only
run on success. Keep `record_call` and `_notify_credits_changed` unchanged.

- [ ] **Step 4: Run metering + credits tests — expect PASS**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core/test_metering.py tests/core/test_credits.py -q`

- [ ] **Step 5: Commit**

```bash
git add core/metering.py tests/core/test_metering.py
git commit -m "[feat] Make meter_action prepaid: fixed-price gate, upfront debit, refund on failure"
```

---

### Task 4: 402 handler payload + tiered signup grant wiring

**Files:**
- Modify: `web/main.py:194-203` (exception handler), `web/auth/identity.py:183` (grant call)
- Test: `tests/web/test_signup_grant.py` (update), `tests/web/test_metered_endpoints.py` (update payload assertions)

**Interfaces:**
- Consumes: `InsufficientCredits(.balance, .price, .action)` (Task 2), `signup_grant_for_tier` (Task 2).
- Produces: HTTP 402 body `{"error": "insufficient_credits", "balance": int, "price": int, "action": str}` (the `floor` key is REMOVED).

- [ ] **Step 1: Update the handler in `web/main.py`**

```python
@app.exception_handler(InsufficientCredits)
async def _insufficient_credits_handler(request, exc: InsufficientCredits):
    return JSONResponse(
        status_code=402,
        content={
            "error": "insufficient_credits",
            "balance": exc.balance,
            "price": exc.price,
            "action": exc.action,
        },
    )
```

- [ ] **Step 2: Update `_provision_account` in `web/auth/identity.py`**

Change the import from `signup_grant_amount` to `signup_grant_for_tier` and the grant line to:

```python
    grant_credits(db, profile_id, signup_grant_for_tier(tier), reason="signup_grant")
```

- [ ] **Step 3: Update tests**

In `tests/web/test_signup_grant.py`: the non-admin provisioning test currently asserts
the flat `CREDIT_SIGNUP_GRANT` amount (100). Change it to assert tier-based grants:

```python
def test_standard_signup_gets_20_units(...):  # adapt existing fixture/flow
    ...
    assert acct.credit_balance == 20


def test_beta_invite_signup_gets_200_units(...):  # invite row with tier="beta"
    ...
    assert acct.credit_balance == 200
```

(Reuse the file's existing OAuth-callback/provisioning test scaffolding; only the
expected amounts and an invite-tier variant change.) In
`tests/web/test_metered_endpoints.py`, update 402-body assertions from `"floor"`
to `"price"` and `"action"`.

- [ ] **Step 4: Run — expect PASS**

Run: `.\.venv\Scripts\python.exe -m pytest tests/web/test_signup_grant.py tests/web/test_metered_endpoints.py tests/web/test_identity.py -q`

(`test_metered_endpoints.py` may still fail on action names until Task 5 — if so, note it and defer those assertions to Task 5.)

- [ ] **Step 5: Commit**

```bash
git add web/main.py web/auth/identity.py tests/web/test_signup_grant.py tests/web/test_metered_endpoints.py
git commit -m "[feat] Tiered signup grants and price-bearing 402 payload"
```

---

### Task 5: Rewire all meter call sites to priced actions

**Files:**
- Modify: `web/routers/jobs.py` (score/extract/rematch/generate/feedback), `web/intake_pipeline.py` (intake bundle, refinement loops, ATS gate, feedback refine), `web/routers/config.py` (no action-name change: `resume_parse` and `draft` already match the card)
- Test: `tests/web/test_metered_endpoints.py`, `tests/web/test_run_ats_gate_pipeline.py`, `tests/web/test_feedback_refine.py`, `tests/web/test_section_refinement.py` (adjust stubs)

**Interfaces:**
- Consumes: `meter_action` (Task 3), `resolve_generate_action` (Task 1).
- Produces: the final metering topology:
  - `POST /{job_key}/score` → `action="score"` (unchanged name, now 1u).
  - `POST /{job_key}/description/extract` → `action="extract"` with the skill-match call INSIDE the same meter.
  - `POST /{job_key}/rematch-skills` → `action="rematch"` (renamed from `"extract"`).
  - `POST /{job_key}/generate/{doc}` → `action=resolve_generate_action(db, job, doc_type)`.
  - `run_pipeline` (intake) → ONE `action="intake"` meter around extract+score; the inner helpers no longer open their own meters when called from the pipeline.
  - Post-generation refinement loops (`_run_doc_refinement`, `_run_resume_section_refinement`) and pipeline-triggered `run_ats_gate` → NO meters (bundled into the generation price).
  - `run_ats_gate(job_key, profile_id, metered=False)` — `metered=True` only when spawned by the document-PUT edit path (`action="ats"`, 1u).
  - `run_user_feedback_refine` → ONE `action="regenerate"` meter wrapping the whole refine+eval body (replaces its internal per-step meters).

- [ ] **Step 1: `web/routers/jobs.py` — extraction folds skill-match into one meter**

In `_do_extract_description`, add a keyword-only `metered: bool = True` parameter and
restructure so ONE meter wraps both LLM calls (replacing the current two blocks —
the extract meter at the raw call and the separate skill-match meter):

```python
def _do_extract_description(job: Job, db: Session, profile_id: int, *,
                            metered: bool = True) -> None:
    """Run description extraction + semantic skill match and persist fields.

    ``metered=False`` when the caller (intake pipeline) already opened the
    'intake' bundle meter — nested meters would double-charge.
    """
    from contextlib import nullcontext
    user = User.load(db, profile_id=profile_id)
    try:
        prompt_content = user.resolve_prompt("extraction")
    except PromptNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        client, model = get_client_for_profile(user, user.prompt_extraction_model)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    actual_prompt = job.build_description_prompt(prompt_content)
    meter = (meter_action(db, profile_id, action="extract", job_key=job.job_key)
             if metered else nullcontext())
    with meter:
        try:
            raw = _call_llm_for_extraction(client, model, actual_prompt, label=f"extract:{job.job_key}")
        except Exception as exc:
            raise RuntimeError(f"Description extraction failed: {exc}") from exc
        try:
            data = _json.loads(raw)
        except (_json.JSONDecodeError, TypeError):
            raise RuntimeError("Description extraction failed: LLM returned invalid JSON")
        _apply_extraction_fields(job, data)   # the existing field-assignment block, unchanged
        # Semantic skill match — best-effort; failure must not lose the extraction.
        try:
            from db.database import PromptDefault
            row = db.query(PromptDefault).filter_by(type_key="skill_match").first()
            if row is not None:
                job.match_profile_skills(user, client, model, db, row.content)
        except Exception:
            pass
    _add_pending_review(job, "description")
    job.unread_indicator = "ok"
    job.last_result_error = None
    db.commit()
```

(Extract the existing `job.ext_* = ...` assignments into a private
`_apply_extraction_fields(job, data)` helper verbatim so the meter block stays
readable. Note: JSON parse failure now happens inside the meter → the debit is
refunded, which is the correct prepaid semantics.)

- [ ] **Step 2: `web/routers/jobs.py` — rematch rename + generate resolver + feedback pre-check**

In `rematch_skills`, change `action="extract"` to `action="rematch"`.

In `_do_generate_resume` / `_do_generate_cover`:

```python
    from core.pricing import resolve_generate_action
    action = resolve_generate_action(db, job, "resume")   # "cover" in _do_generate_cover
    with meter_action(db, profile_id, action=action, job_key=job.job_key):
        job.generate_resume_md(user, prompt_content, client, model, db)
```

In `submit_document_feedback` (the 202 endpoint), add a fail-fast affordability
pre-check before spawning the background job (the real gate+debit happens in the
background meter; this only converts the common case into an immediate 402):

```python
    from core.credits import InsufficientCredits, get_account_for_profile
    from core.pricing import price_for
    acct = get_account_for_profile(db, profile_id)
    if (acct is not None and not acct.is_admin and (acct.credit_rate or 0.0) > 0
            and (acct.credit_balance or 0) < price_for("regenerate")):
        raise InsufficientCredits(acct.credit_balance or 0, price_for("regenerate"), "regenerate")
```

In the document-PUT handler (`PUT .../{doc_type}/document`, currently
`_spawn(run_ats_gate, job_key, profile_id)`), pass the metered flag:
`_spawn(run_ats_gate, job_key, profile_id, True)`.

- [ ] **Step 3: `web/intake_pipeline.py` — intake bundle, bundled refinement, ATS flag, feedback meter**

1. `_do_score(job, db, profile_id, *, metered: bool = True)` — wrap `job.score(...)`
   in `meter_action(..., action="score", ...)` only when `metered`; use
   `contextlib.nullcontext()` otherwise (same pattern as Step 1).
2. In `run_pipeline`, wrap steps 1+2 in the bundle meter and pass `metered=False`
   down. `InsufficientCredits` aborts the pipeline with the job marked errored:

```python
        from core.credits import InsufficientCredits
        try:
            with meter_action(db, profile_id, action="intake", job_key=job_key):
                # Step 1: description extraction
                llm_status.start(profile_id, job_key, "description")
                try:
                    _do_extract_description(job, db, profile_id, metered=False)
                finally:
                    llm_status.finish(profile_id, job_key, "description")
                db.refresh(job)
                _emit(job)
                # Step 2: scoring
                llm_status.start(profile_id, job_key, "score")
                try:
                    _do_score(job, db, profile_id, metered=False)
                finally:
                    llm_status.finish(profile_id, job_key, "score")
        except InsufficientCredits:
            job = Job.get(job_key, db, profile_id)
            job.unread_indicator = "error"
            job.last_result_error = "Out of credits — intake needs 2 credits."
            db.commit()
        except Exception as exc:
            db.rollback()
            job = Job.get(job_key, db, profile_id)
            job.unread_indicator = "error"
            job.last_result_error = str(exc)
            db.commit()
        db.refresh(job)
        _emit(job)
```

   (This intentionally collapses the current per-step try/except into one bundle-level
   handler: a failure anywhere in the bundle refunds the whole 2u and marks the job
   errored. The old behavior of "extraction failed → skip scoring" is preserved because
   the exception aborts the `with` body before scoring runs.)
3. Remove `meter_action` wrappers from `_run_doc_refinement` and
   `_run_resume_section_refinement` eval/refine steps (all currently
   `action="eval"` / `action="refine"` sites at the top of each loop body) —
   these turns are bundled into the generation price. Keep `llm_status` and error
   handling untouched; only the `with meter_action(...):` lines and their
   indentation change.
4. `run_ats_gate(job_key: str, profile_id: int, metered: bool = False)` — replace
   the Task-1-audit meter with:

```python
        meter = (meter_action(db, profile_id, action="ats", job_key=job_key)
                 if metered else nullcontext())
        try:
            with meter:
                report = job.run_ats_check(db, user, client, model)
        except InsufficientCredits as exc:
            print(f"[ats] {job_key}: skipped — {exc}", flush=True)
            return
        except FileNotFoundError as exc:
            print(f"[ats] {job_key}: artifact missing — {exc}", flush=True)
            return
```

5. `run_user_feedback_refine`: replace its internal `action="refine"` /
   `action="eval"` meters with ONE
   `with meter_action(db, profile_id, action="regenerate", job_key=job_key):`
   wrapping the whole refine+eval sequence (open it where the first current meter
   opens; close after the last metered step). On `InsufficientCredits`, mark the
   job errored (`job.last_result_error = "Out of credits — refine needs 2 credits."`)
   and return, mirroring the pipeline pattern above.

- [ ] **Step 4: Update affected tests**

- `tests/web/test_metered_endpoints.py`: 5-credit account (fixture sets
  `credit_balance=5`) now: score (1u) passes, generate fresh (4u) passes once then
  regen (2u) blocks at balance 0, etc. Update expected 402s, ledger deltas, and
  action names (`rematch`, `generate_fresh`, `intake`).
- `tests/web/test_run_ats_gate_pipeline.py`: `run_ats_gate` default is now
  unmetered — update `test_run_ats_gate_skips_on_insufficient_credits` to call
  `pipeline.run_ats_gate("job1", 1, metered=True)`.
- `tests/web/test_feedback_refine.py` / `test_section_refinement.py`: the
  `fake_meter` monkeypatch signature keeps working (`meter_action` still accepts
  `action=`/`job_key=`); remove `floor=` from any fake signatures if present.

- [ ] **Step 5: Run the web + core suites — expect PASS**

Run: `.\.venv\Scripts\python.exe -m pytest tests/web tests/core -q`

- [ ] **Step 6: Commit**

```bash
git add web/routers/jobs.py web/intake_pipeline.py tests/web
git commit -m "[feat] Rewire metering to fixed-price actions: intake bundle, fresh/regen resolution, bundled refinement"
```

---

### Task 6: `core/payments.py` — unit-denominated packs

**Files:**
- Modify: `core/payments.py` (`compute_credits`, `tier_margins` → `tier_multipliers`), plus call-site renames in `web/routers/credits.py` (tier validation) and anywhere else `tier_margins` is imported (grep: `git grep -n "tier_margins"`).
- Test: `tests/core/test_payments.py` (or the existing pack-computation test file — locate with `git grep -ln "compute_credits" tests/`)

**Interfaces:**
- Consumes: `pricing.unit_usd()` (Task 1).
- Produces: `tier_multipliers() -> dict[str, float]` (env `CREDIT_TIER_MULTIPLIERS`, defaults `{"standard": 1.0, "friends_family": 4.0, "beta": 10.0}`); `compute_credits(price_usd: int, tier: str) -> int` in units. `tier_margins` is DELETED (update `web/routers/credits.py`'s tier-set validation to `payments.tier_multipliers()`).

- [ ] **Step 1: Write failing tests**

```python
def test_compute_credits_standard(monkeypatch):
    from core import payments
    monkeypatch.delenv("CREDIT_TIER_MULTIPLIERS", raising=False)
    monkeypatch.delenv("CREDIT_UNIT_USD", raising=False)
    # $5 pack: net = 5 - (0.30 + 5*0.029) = 4.555; /0.02 = 227.75; ×1; +5% bulk discount
    got = payments.compute_credits(5, "standard")
    assert got == round(4.555 / 0.02 * 1.0 * 1.05)  # 239


def test_compute_credits_beta_multiplier():
    from core import payments
    std = payments.compute_credits(5, "standard")
    beta = payments.compute_credits(5, "beta")
    assert beta == pytest.approx(std * 10, rel=0.01)


def test_unknown_tier_raises():
    from core import payments
    with pytest.raises(ValueError):
        payments.compute_credits(5, "nope")
```

(Verify the exact `_net()` fee formula in `core/payments.py` before finalizing the
expected numbers — adjust the literal in the first assert to whatever
`_net(5) / 0.02 * 1.0 * (1 + discount)` rounds to with the real `_net`.)

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement**

```python
_DEFAULT_MULTIPLIERS = {"standard": 1.0, "friends_family": 4.0, "beta": 10.0}


def tier_multipliers() -> dict[str, float]:
    """Tier name -> pack purchasing-power multiplier."""
    cfg = _env_json("CREDIT_TIER_MULTIPLIERS")
    if not cfg:
        return dict(_DEFAULT_MULTIPLIERS)
    return {str(k): float(v) for k, v in cfg.items()}


def compute_credits(price_usd: int, tier: str) -> int:
    """Units granted for a pack: net proceeds ÷ UNIT_USD × tier multiplier,
    plus the bulk discount. Replaces the cost-margin model (meaningless at
    near-zero LLM cost)."""
    from core.pricing import unit_usd

    mults = tier_multipliers()
    if tier not in mults:
        raise ValueError(f"unknown tier: {tier}")
    discount = price_tiers().get(price_usd, 0.0)
    units = round(_net(price_usd) / unit_usd() * mults[tier] * (1 + discount))
    if units <= 0:
        raise ValueError(f"pack ${price_usd} for tier {tier} is not profitable")
    return units
```

Delete `_DEFAULT_MARGINS`, `tier_margins`, `CREDITS_PER_DOLLAR`, and `_round25` if
now unused (`git grep -n "_round25\|CREDITS_PER_DOLLAR\|tier_margins"`); update
`web/routers/credits.py` tier validation and any admin router imports.

- [ ] **Step 4: Run payments + credits-router tests — expect PASS**

Run: `.\.venv\Scripts\python.exe -m pytest tests/core -q; .\.venv\Scripts\python.exe -m pytest tests/web/test_payments_router.py tests/web/test_admin_set_tier.py -q`

- [ ] **Step 5: Commit**

```bash
git add core/payments.py web/routers/credits.py tests/
git commit -m "[feat] Denominate packs in units via UNIT_USD and tier multipliers"
```

---

### Task 7: Alembic redenomination migration

**Files:**
- Create: `alembic/versions/aa10units01_redenominate_units.py`
- Test: `tests/db/test_redenomination.py` (function-level test of the migration's data logic, mirroring `tests/db/test_tier_migration.py`'s model-level style)

**Interfaces:**
- Consumes: nothing at runtime (raw SQL over `account`, `credit_ledger`, `purchase`).
- Produces: revision `aa10units01`, `down_revision = "aa09rmprompts01"`.

- [ ] **Step 1: Write the migration**

```python
"""redenominate credit balances to units (÷20) + tier grant top-up

Revision ID: aa10units01
Revises: aa09rmprompts01
Create Date: 2026-07-16

Converts old 1000-credits-per-dollar balances to $0.02 units (old ÷ 20),
writing a 'redenomination' ledger row per account for the delta. Accounts that
never completed a purchase and land below their tier's new signup grant
(standard 20 / friends_family 50 / beta 200 — frozen here on purpose) are
topped up with a 'redenomination_topup' row.
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "aa10units01"
down_revision: Union[str, Sequence[str], None] = "aa09rmprompts01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GRANTS = {"standard": 20, "friends_family": 50, "beta": 200}


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()
    accounts = bind.execute(sa.text(
        "SELECT profile_id, credit_balance, tier, is_admin FROM account"
    )).fetchall()
    for profile_id, old, tier, is_admin in accounts:
        old = old or 0
        new = round(old / 20)
        if new != old:
            bind.execute(sa.text(
                "INSERT INTO credit_ledger (profile_id, delta, reason, created_at) "
                "VALUES (:p, :d, 'redenomination', :t)"
            ), {"p": profile_id, "d": new - old, "t": now})
        purchased = bind.execute(sa.text(
            "SELECT COUNT(*) FROM purchase WHERE profile_id = :p AND status = 'completed'"
        ), {"p": profile_id}).scalar() or 0
        grant = _GRANTS.get(tier or "standard", _GRANTS["standard"])
        if not is_admin and purchased == 0 and new < grant:
            bind.execute(sa.text(
                "INSERT INTO credit_ledger (profile_id, delta, reason, created_at) "
                "VALUES (:p, :d, 'redenomination_topup', :t)"
            ), {"p": profile_id, "d": grant - new, "t": now})
            new = grant
        bind.execute(sa.text(
            "UPDATE account SET credit_balance = :b WHERE profile_id = :p"
        ), {"b": new, "p": profile_id})


def downgrade() -> None:
    # One-way by design: the pre-conversion balances are recoverable from the
    # 'redenomination'/'redenomination_topup' ledger rows if ever needed.
    pass
```

(Check `credit_ledger`'s NOT NULL columns in `db/database.py` before finalizing the
INSERTs — if `action`/`meta` etc. are nullable this is fine as written; add any
required columns with NULL-safe values.)

- [ ] **Step 2: Test the data logic**

```python
# tests/db/test_redenomination.py
"""Data-logic checks for the aa10units01 redenomination (run against SQLite)."""
import importlib

from sqlalchemy import create_engine, text

from db.database import Base


def _setup(engine, rows):
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        for r in rows:
            c.execute(text(
                "INSERT INTO account (email, profile_id, is_admin, banned, created_at,"
                " credit_balance, credit_rate, tier)"
                " VALUES (:email, :pid, :adm, 0, 't', :bal, 1.0, :tier)"
            ), r)


def _run_upgrade(engine):
    mig = importlib.import_module("alembic.versions.aa10units01_redenominate_units")
    # Execute the same statements via a lightweight op-shim
    from unittest.mock import patch
    with engine.begin() as conn:
        with patch.object(mig, "op") as op_mock:
            op_mock.get_bind.return_value = conn
            mig.upgrade()


def test_conversion_and_topup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'m.db'}")
    _setup(engine, [
        {"email": "a@x", "pid": 1, "adm": 0, "bal": 100, "tier": "beta"},      # ->5 -> topup 200
        {"email": "b@x", "pid": 2, "adm": 0, "bal": 5000, "tier": "standard"}, # ->250, no topup
        {"email": "c@x", "pid": 3, "adm": 1, "bal": 100, "tier": "standard"},  # admin: ->5, no topup
    ])
    _run_upgrade(engine)
    with engine.connect() as c:
        bals = dict(c.execute(text("SELECT profile_id, credit_balance FROM account")).fetchall())
        assert bals == {1: 200, 2: 250, 3: 5}
        reasons = [r[0] for r in c.execute(text("SELECT reason FROM credit_ledger ORDER BY id")).fetchall()]
        assert "redenomination" in reasons and "redenomination_topup" in reasons
```

(If the `alembic.versions` package isn't importable by module path, load the file
with `importlib.util.spec_from_file_location` instead — follow whatever pattern
`tests/db/` already uses; if no precedent exists, use `spec_from_file_location`.)

- [ ] **Step 3: Run — expect PASS; also run `alembic upgrade head` against a scratch SQLite DB**

Run: `.\.venv\Scripts\python.exe -m pytest tests/db/test_redenomination.py -q`
Then: `$env:DATABASE_URL="sqlite:///$env:TEMP\redenom_check.db"; .\.venv\Scripts\python.exe -m alembic upgrade head` — expect clean run (verify the env-var name Alembic's `env.py` reads before running).

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/aa10units01_redenominate_units.py tests/db/test_redenomination.py
git commit -m "[feat] Redenominate credit balances to units with tier-grant top-up"
```

---

### Task 8: Frontend — price-aware 402 toast + price hints

**Files:**
- Modify: `react-dashboard/src/App.jsx:55-61` (toast handler), `react-dashboard/src/components/widgets/Settings.jsx` (action buttons near line 669; also its inline 402 handler near line 690)
- Create: `react-dashboard/src/prices.js`

**Interfaces:**
- Consumes: 402 body `{error, balance, price, action}` (Task 4) — already forwarded by `api.js` as `event.detail`.
- Produces: `PRICES` map + `priceLabel(action)` used by Settings buttons.

- [ ] **Step 1: `react-dashboard/src/prices.js`**

```javascript
// Mirrors core/pricing.py DEFAULT_PRICES — display only; the server is authoritative.
export const PRICES = {
  intake: 2,
  generate_fresh: 4,
  regenerate: 2,
  score: 1,
  extract: 1,
  resume_parse: 1,
  ats: 1,
  rematch: 1,
  draft: 1,
}

export const priceLabel = (action) =>
  PRICES[action] != null ? `${PRICES[action]}⚡` : ''
```

- [ ] **Step 2: App.jsx toast with price context**

```javascript
  // Out-of-credits signal (dispatched from api.js on HTTP 402)
  useEffect(() => {
    const handler = (e) => {
      const d = e?.detail || {}
      const msg = d.price != null
        ? `Not enough credits — this costs ${d.price}, you have ${d.balance}.`
        : "You're out of credits — purchase more to continue."
      pushToast(msg)
    }
    window.addEventListener('auto-apply:credits-error', handler)
    return () => window.removeEventListener('auto-apply:credits-error', handler)
  }, [pushToast])
```

Apply the same message shape to Settings.jsx's inline 402 handler (~line 690).

- [ ] **Step 3: Price hints on the Settings action buttons**

In `Settings.jsx` where the score/resume/cover action buttons render (the component
that posts to the URLs at ~line 669), append `priceLabel(...)` to each button label:
score → `priceLabel('score')`, resume/cover → `priceLabel('generate_fresh')` when the
job has no doc yet (the job object's `resume_md_exists`/`cover_md_exists` serializer
flags), else `priceLabel('regenerate')`. Import from `../../prices` (adjust relative
path to the actual file location).

Also check `CreditBalance.jsx`'s recent-activity list: it renders ledger rows by
`reason`. If it special-cases reason strings, add friendly labels for `refund`,
`redenomination`, and `redenomination_topup`; if it renders reasons generically,
no change is needed.

- [ ] **Step 4: Verify build + eyeball**

Run: `cd react-dashboard; npm run build` — expect a clean build.
Then run the app (`start.bat dev`) and confirm: buttons show `1⚡`/`4⚡`/`2⚡`, and
(with a dev account forced metered at balance 0 — set `credit_balance=0`,
`credit_rate=1` on a local Account row) a metered action shows the price-bearing toast.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/prices.js react-dashboard/src/App.jsx react-dashboard/src/components/widgets/Settings.jsx
git commit -m "[feat] Show unit prices on action buttons and price-aware out-of-credits toast"
```

---

### Task 9: Full-suite verification + docs sync

**Files:**
- Modify: `web/CONTEXT.md` (Credits & Metering section), `core/CONTEXT.md` (metering description), `TODO.md` (mark item done), `ARCHITECTURE.md` (only if it describes the metering model)

- [ ] **Step 1: Run the full suite**

Run: `.\.venv\Scripts\python.exe -m pytest tests -q`
Expected: everything passes except the pre-existing `tests/scraper/test_runner.py::test_run_scraper_continues_on_source_error` full-suite flake.

- [ ] **Step 2: Update docs**

- `web/CONTEXT.md` → rewrite the "Credits & Metering" bullet: prepaid fixed prices,
  the price card, the metering topology from Task 5's Interfaces block, the new 402
  payload, tiered grants, unit-denominated packs, redenomination migration.
- `core/CONTEXT.md` → update its metering/credits section to match (`debit_fixed`,
  `refund_debit`, `price_for`, no more floor).
- `TODO.md` → mark the "Fixed-unit credit pricing" item `[x]` with a one-line result.

- [ ] **Step 3: Commit**

```bash
git add web/CONTEXT.md core/CONTEXT.md TODO.md ARCHITECTURE.md
git commit -m "[docs] Document fixed-unit prepaid pricing model"
```

- [ ] **Step 4: Deployment notes (manual, with user approval)**

- Push to origin → Railway deploys and runs `alembic upgrade head` on startup
  (redenomination executes exactly once).
- No new REQUIRED env vars (all defaults baked in); optional knobs:
  `CREDIT_UNIT_USD`, `CREDIT_SIGNUP_GRANTS`, `CREDIT_TIER_MULTIPLIERS`, `PRICE_*`.
- `CREDIT_SIGNUP_GRANT`, `CREDIT_FLOOR`, `CREDIT_DEFAULT_RATE` (rate keeps working),
  `CREDIT_TIER_MARGINS` — remove stale values from Railway if set.
- Verify post-deploy: `GET /api/credits` for the beta user shows 200; a metered
  action debits its fixed price; `GET /api/payments/packs` shows unit counts.
