# Credits & Metering — Design

**Date:** 2026-06-12
**Sub-project:** (2) Credits & Metering — second of the SaaS conversion stack (Auth → **Credits** → Payments → Onboarding).
**Status:** Spec.
**Depends on:** Auth & Identity (done, live). The `account`/`identity` tables, `profile_id` tenancy seam, `scoped()`, and the `before_flush` tenant guard all exist.

## Goal

Give every tenant a credit balance that is debited by the real cost of LLM work, and block LLM-driven actions when the balance is too low. Credits are **cost-backed**: a debit is the platform's actual LLM spend for an action, marked up per account and converted to credits. Pre-Stripe, credits enter via a signup grant and admin grants.

This sub-project does **not** add Stripe/payments (next sub-project), an effort-tier model selector, or any tier-management UI. It builds the ledger, the metering plumbing, the action-level gate, and the minimum UI to see and react to balance.

## Credit model

- **Denomination:** abstract credits at a fixed conversion of **1000 credits = $1** (1 credit = $0.001 of *marked-up* cost).
- **Conversion:** `debit_credits = round(raw_cost_usd × credit_rate × 1000)`.
  - `raw_cost_usd` is the actual LLM cost for the call, read from `usage.cost` (OpenRouter returns it; already captured by `core/session_cost`).
  - `credit_rate` is a per-account multiplier folding in markup and user tier. Concrete tiers: **developer = `0`** (free), **friends-and-family = `1.5`**, **standard customer = `10.0`**. Default for new accounts comes from config (`CREDIT_DEFAULT_RATE`). **Seam only** in v1 — set manually per account, no UI.
- **Gating (action level):** before a metered action runs, require `balance ≥ CREDIT_FLOOR` (a small configured static floor — roughly the credit cost of one action). Sub-calls of the action then run freely and each accrues actual cost. A single action may overshoot slightly into a small negative balance on an unexpectedly expensive call — acceptable, because real cost was still collected. Per-action estimate tables / rolling averages are explicitly deferred.
  - Note the floor is a flat credit amount while `credit_rate` varies per account, so a 10× customer reaches the floor sooner than a 1.5× F&F user for the same raw work. Acceptable in v1.
  - **Dev accounts (`credit_rate = 0`)** are never debited and are not gated: a 0× rate yields a 0-credit debit, and their balance is irrelevant to them. Devs instead see the **system-wide** balance (see Dev system-balance view).

## Data model — one Alembic migration

### `credit_ledger` (new table — append-only, source of truth)

| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `profile_id` | int, indexed, not null | tenant |
| `delta` | int, not null | signed credits: `+` grant, `−` debit |
| `reason` | str, not null | `signup_grant` \| `admin_grant` \| `debit` \| `adjustment` (`purchase` added by Payments) |
| `action` | str, nullable | debits only: `score`/`generate`/`refine`/`eval`/`extract` |
| `job_key` | str, nullable | links a debit to a job |
| `raw_cost_usd` | float, nullable | actual LLM cost for the debit (audit) |
| `meta` | text (JSON), nullable | `{model, prompt_tokens, completion_tokens, calls}` |
| `created_by` | int, nullable | account id for admin grants |
| `created_at` | str (iso), not null | |

Append-only: rows are never updated or deleted. The ledger is the reconcilable truth.

### `account` — two new columns

- `credit_balance` int, not null, default `0` — cached denormalized balance, mutated in the **same transaction** as every ledger insert. A `reconcile_balance(db, profile_id)` helper recomputes it as `SUM(delta)` from the ledger (for repair / tests).
- `credit_rate` float, not null, default from config (`CREDIT_DEFAULT_RATE`) — the per-account tier multiplier.

> Note: balance and rate live on `account` (the billing identity), not `user_profile`. The ledger keys on `profile_id` for tenancy consistency; the 1:1 account↔profile mapping makes either key equivalent. Balance reads/writes go through the account row that owns the active `profile_id`.

## Metering chokepoint — `core/llm.py`

Extend the existing `core/session_cost` accumulator pattern. Add a **`metering` contextvar** that, when active, holds a per-action list of call records. `call_llm` already reads `usage.cost`; when a meter is active it appends `{cost, model, prompt_tokens, completion_tokens}` to it. When no meter is active (tray/local, scripts), `call_llm` behaves exactly as today. `core/job.py` is untouched.

## Action boundary — `meter_action()` context manager

A reusable context manager (new `core/metering.py`) wraps each metered core call **at the router / `intake_pipeline` layer**, not inside `core/job.py`:

```
with meter_action(db, profile_id, action="generate", job_key=key, floor=CREDIT_FLOOR):
    job.generate_resume_md(...)   # all sub-calls accrue cost
```

Lifecycle:
1. **Gate** — if the account's `credit_rate == 0` (dev), skip the gate entirely. Otherwise read `account.credit_balance`; if `< floor`, raise `InsufficientCredits` (→ HTTP 402).
2. **Open** — set the `metering` contextvar (carries profile_id, action, job_key); reset accumulator.
3. **Run** — the wrapped action; every `call_llm` sub-call (generate + eval + ATS, etc.) appends its cost.
4. **Settle** — sum accumulated `raw_cost_usd`; compute `debit_credits` with the account's `credit_rate`; in one transaction insert a single `debit` ledger row and decrement `credit_balance`. Settle even if the action raised after at least one paid sub-call (cost was incurred) — wrap step 3 so settle runs in a `finally`, with the error re-raised after.

Helper `grant_credits(db, profile_id, amount, reason, *, created_by=None, note=None)` does the inverse: insert a `+delta` ledger row and bump `credit_balance` atomically. Used by the signup hook, the admin endpoint, and (later) the Stripe webhook.

## API surface — `web/routers/credits.py` (new)

- `GET /api/credits` → `{balance, rate, recent: [ledger rows]}` for the active tenant. Drives the UI.
- `POST /api/admin/credits/grant` (admin-only, reuses the auth admin check) → body `{profile_id | email, amount, note}` → `grant_credits(..., reason="admin_grant", created_by=<admin account id>)`. **This is the exact call the Stripe webhook will reuse.**
- `GET /api/admin/system-balance` (admin/dev-only) → fetches the **OpenRouter API key's remaining credit balance** (the platform's actual money in the system) via OpenRouter's key/credits endpoint, returning `{usage, limit, remaining}`. Read-only; surfaced in the dev view.

Gating raises `InsufficientCredits` → a `402` handler returns `{error: "insufficient_credits", balance, floor}`.

## Signup grant

Hook `_provision_account` in `web/auth/identity.py` (the single new-account path): after the account is created, call `grant_credits(db, profile_id, CREDIT_SIGNUP_GRANT, reason="signup_grant")` in the same flow so a new beta user has immediate runway (config'd, `100` credits = $0.10).

## UI (`react-dashboard/`)

- **Balance display** — credit balance in the navbar and the User/Settings tab, fed by `GET /api/credits`. Refresh after any metered action.
- **Out-of-credits signal** — metered action calls that return `402` surface a clear "Out of credits" modal/toast (not a silent failure), explaining the user is out and (for now) to contact the admin. Becomes the buy-credits CTA once Payments lands.
- **Dev system-balance view** — for dev/admin accounts, a small panel (User/Settings tab) showing the OpenRouter key's remaining balance from `GET /api/admin/system-balance` — "money currently in the system". Hidden for non-dev users.

## Config / env

| key | meaning | example |
|---|---|---|
| `CREDIT_DEFAULT_RATE` | default `account.credit_rate` for new accounts (F&F beta) | `1.5` |
| `CREDIT_SIGNUP_GRANT` | credits granted at signup (= $0.10) | `100` |
| `CREDIT_FLOOR` | minimum balance to start a metered action (flat credits) | `10` |

Tier rates (set per account manually): developer `0`, friends-and-family `1.5`, standard customer `10.0`. The signup grant of 100 credits ($0.10) is sized from observed usage (~$0.20 over several weeks of real use), so it gives a beta user a long runway. Reading the OpenRouter key balance needs the existing `LLM_API_KEY`; no new secret.

## Metered actions (where `meter_action` wraps)

The LLM-driven entry points in `web/routers/` (delegating to `core/job.py`) and `web/intake_pipeline.py`:
`score`, `generate` (resume + cover), `refine` (incl. user-feedback refine), `eval`, `extract_description`. Each gets a `meter_action` wrapper at its router/pipeline call site. Non-LLM endpoints are untouched.

## Out of scope (designed-for, not built)

- **Payments / Stripe** — next sub-project; reuses `grant_credits` via webhook + a `purchase` ledger reason.
- **Effort tiers** (standard vs high → model swap). Metering already records `model` per call, so a per-action model override slots in later with no ledger change.
- **Tier-management UI** — `credit_rate` exists and is set manually in v1.
- **Per-action credit estimates / rolling averages** — the static `CREDIT_FLOOR` is v1; richer estimates layer on once the ledger has real cost data.

## Testing

- **Conversion** — `debit_credits` rounding across rates (0, 1.5, 10.0) and small/large costs; rate `0` always yields a 0-credit debit and skips the gate.
- **Metering** — a fake `call_llm` accruing multiple sub-call costs settles to one debit row with summed `raw_cost_usd`.
- **Gate** — balance below floor raises `InsufficientCredits` before any sub-call runs; balance at/above floor proceeds.
- **Settle-on-error** — an action that raises mid-way still debits the cost already incurred.
- **Grants** — signup grant fires once per new account; admin grant bumps balance and writes a `created_by` row; `reconcile_balance` equals ledger SUM after a mix of grants and debits.
- **Tenancy** — ledger rows and balance reads respect `profile_id` scoping (one tenant cannot see/spend another's credits).
```