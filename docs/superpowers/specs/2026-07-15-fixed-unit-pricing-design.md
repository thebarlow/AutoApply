# Fixed-Unit Credit Pricing — Design

**Date:** 2026-07-15
**Status:** Approved (session workshop)
**Replaces:** post-paid cost-passthrough metering (`meter_action` debiting `raw_cost_usd × credit_rate`, gated only by a flat 10-credit floor)

## Problem

Today a user cannot know what an action will cost (debits are actual LLM cost × rate),
the balance can run negative (gate is a flat floor, debit is post-paid), and cheap
actions look free while refine loops make generation cost spiky. The product needs
predictable arcade-token pricing where an action is simply blocked when the user
can't afford it.

## Price Card

Credits are re-denominated to coarse units. A standard job costs **10 units**:
2 intake + 4 résumé + 4 cover letter.

| Action key | Units | Trigger |
|---|---|---|
| `intake` | 2 | Intake-pipeline bundle on a new job: score + extract + skill-match under one meter |
| `generate_fresh` | 4 | First generation of a doc_type (résumé or cover) for a job — no `documents` row and no rendered `.md` exists yet. Includes the auto eval/refine turns and the post-generation ATS check |
| `regenerate` | 2 | Re-generating an existing doc, or a feedback refine. Includes its eval/refine turns + ATS |
| `score` | 1 | Standalone manual re-score |
| `extract` | 1 | Standalone re-extract (includes its skill-match) |
| `resume_parse` | 1 | Résumé parse (onboarding or re-parse) |
| `ats` | 1 | ATS re-check triggered by a manual document edit |
| `rematch` | 1 | Rematch-skills |
| `draft` | 1 | Section-prompt draft helper |

Rules:

- **Nothing that hits the LLM is free.** Every LLM call site runs inside a priced meter.
- **Fresh vs. regen is derived server-side** from whether a `documents` row (or rendered
  `.md`) already exists for `(job, doc_type)`. No client input.
- Prices live in a single table in `core/pricing.py`, each env-overridable
  (`PRICE_INTAKE`, `PRICE_GENERATE_FRESH`, …) so tuning needs no deploy.
- Bundled sub-calls (eval/refine turns inside a generation, ATS after generation,
  skill-match inside extract/intake) do **not** open their own meters — they run inside
  the parent action's meter. Only user-initiated standalone triggers use the 1-unit rows.

## Metering Engine (`core/metering.py`)

`meter_action(db, profile_id, action=..., job_key=...)` changes from post-paid to
**priced, prepaid**:

1. **Enter:** resolve the action's price; atomically gate (`balance ≥ price`) and debit
   the fixed price as one ledger row (`reason="debit"`, `delta=-price`). Gate failure
   raises `InsufficientCredits(balance, price)` — the existing HTTP 402 handler is
   reused, with the payload extended to `{error, balance, price, action}` so the UI can
   say "Scoring costs 2 credits — you have 1."
   The gate+debit must be a single conditional `UPDATE account SET credit_balance =
   credit_balance - :price WHERE profile_id = :pid AND credit_balance >= :price`
   (rowcount 0 ⇒ 402), so concurrent actions cannot overdraw.
2. **Body:** `record_call` keeps accumulating actual LLM cost exactly as today.
3. **Exit, success:** write the summed `raw_cost_usd` + call metadata into the debit
   row's `raw_cost_usd`/`meta` — the ledger permanently records margin (units charged
   vs. dollars spent) per action.
4. **Exit, exception:** write an offsetting `reason="refund"` row (`delta=+price`) and
   restore the balance in the same transaction. The user never pays for a failed action.
   (`InsufficientCredits` from the gate itself opens no debit, so nothing to refund.)

Unchanged semantics: admins are never gated or debited; no `Account` row (local dev,
tests) runs unmetered; `credit_rate` drops out of the debit math entirely and survives
only as the metered on/off flag (`0` = unmetered admin/dev, `>0` = metered). The
flat `CREDIT_FLOOR` concept is deleted — the price IS the gate.

The balance-changed SSE nudge (`credits` event) now also fires on refunds.

## Denomination Migration

- `UNIT_USD` — the dollar value of one unit — is a global config value, **calibrated
  before rollout** (see below).
- One Alembic migration converts existing account balances by dollar value:
  `new_balance = round(old_credits / 1000 / UNIT_USD)`; a `reason="redenomination"`
  ledger row records the conversion per account so the ledger SUM stays consistent
  with the cached balance (`reconcile_balance` keeps working).
- Signup grant: **20 units** (2 standard jobs). `CREDIT_SIGNUP_GRANT` default changes.
- Packs (`core/payments.py`): server-computed as
  `units = pack_usd / UNIT_USD × tier multiplier`, replacing the current
  1000-credits-per-dollar math. Tier margins keep working as pack-size multipliers.

## Calibration (first implementation step)

Query the live ledger:
`SELECT action, COUNT(*), AVG(raw_cost_usd), MAX(raw_cost_usd) FROM credit_ledger
WHERE reason='debit' GROUP BY action`. Set `UNIT_USD` so the priciest action
(fresh generation with refine turns, 4 units) retains **≥ 2× margin** at its
*max* observed cost. Everything downstream reads `UNIT_USD`; the analysis lands in
the plan doc so the number is reproducible.

## Frontend

- `CreditBalance` / `BuyCreditsModal`: no structural change (numbers get smaller).
- Action buttons gain price hints (e.g. "Generate — 4 ⚡").
- The 402 toast upgrades to show `price` vs `balance` from the new payload.
- The recent-activity list renders `refund` and `redenomination` rows.

## Testing

- Price resolver: fresh vs. regen detection per doc_type; env overrides.
- Gate: blocks below price; exact-price passes; 402 payload carries `price`/`action`.
- Prepaid semantics: debit exists after enter; refund row + restored balance on body
  exception; success writes `raw_cost_usd` into the debit row.
- Concurrency: two simultaneous actions with balance for one → exactly one succeeds
  (conditional-UPDATE rowcount check).
- Migration math: balance conversion + redenomination ledger row; pack computation
  from `UNIT_USD` × tier.
- Admin/dev bypass unchanged.

## Out of Scope

- Automatic refund/clawback on Stripe payment refunds (existing known limitation).
- Rate-limiting free non-LLM endpoints.
- Per-tier per-action discounts (tiers only affect pack sizes).
