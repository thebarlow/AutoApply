# Tiered Credit Pricing — Design

**Date:** 2026-06-15
**Status:** Approved (design); pending spec review
**Builds on:** `2026-06-13-payments-design.md` (Stripe Checkout + credit-pack fulfillment), `2026-06-12-credits-metering-design.md` (cost-backed credit ledger)

## Problem

The shipped payments feature sells one uniform credit pack set: `STRIPE_PACKS` maps each Stripe
price to a flat credit amount, so every user pays the same dollars for the same credits. We need
**different pricing for different users** (beta testers, friends & family, standard) while keeping
the cost of using the service identical for everyone.

## Principle

**Spending is transparent; pricing is opaque.**

- Every feature costs the same number of credits for every user — credits mirror raw service cost
  1:1 (`credit_rate = 1.0` for all metered users).
- The same dollar amount buys **different credit amounts** depending on the buyer's tier and the
  pack size. Margin and bulk discount live entirely on the purchase side.

This is the "Model B" choice (margin on purchase price) over "Model A" (margin on consumption via
`credit_rate`), explicitly because we want different products/value per user, not a uniform catalog.

## Credit model

- `CREDITS_PER_DOLLAR = 1000` (unchanged): **1 credit = $0.001 of raw API cost.**
- `Account.credit_rate` default changes `1.5 → 1.0`. With rate 1.0, `to_credits(raw_cost, rate)`
  debits exactly the raw cost in credits — no markup on consumption. Admins keep `credit_rate = 0.0`
  (unmetered). The margin that used to live here moves to the purchase calculation below.

## Pricing calculation

Credits granted for a purchase are computed **server-side at fulfillment**, never trusted from the
client, from the buyer's tier and the pack's dollar price:

```
net        = price − (STRIPE_FEE_PCT · price + STRIPE_FEE_FIXED) − TAX_RATE · price
cost_basis = net / tier_margin
credits    = round25( cost_basis × CREDITS_PER_DOLLAR × (1 + tier_discount) )
guard:     while net ≤ credits / CREDITS_PER_DOLLAR: credits −= 25   # every pack must profit
```

- `net` — dollars the platform keeps after Stripe's cut and a flat tax buffer.
- `cost_basis` — dollars of raw API cost the granted credits commit the platform to cover.
- `round25(x)` — round to the nearest 25 credits.
- **Profit guard** — if rounding pushed `credits` high enough that the committed cost basis meets or
  exceeds net revenue, step down by 25 until `net > cost_basis`. Guarantees every pack is profitable.

### Configuration (env JSON, mirroring the existing `STRIPE_PACKS` pattern)

| Key | Meaning | Default |
|---|---|---|
| `CREDIT_TIER_MARGINS` | `{tier: margin}` | `{"beta":1.5,"friends_family":5,"standard":20}` |
| `CREDIT_PRICE_TIERS` | dollar amounts → bulk discount | `{"1":0,"5":0.05,"10":0.10,"20":0.15}` |
| `CREDIT_TIER_VISIBILITY` | `{tier: [dollar amounts]}` | `{"beta":[1],"friends_family":[1,5,10,20],"standard":[1,5,10,20]}` |
| `STRIPE_FEE_PCT` | Stripe percentage cut | `0.029` |
| `STRIPE_FEE_FIXED` | Stripe fixed per-transaction fee | `0.30` |
| `TAX_RATE` | flat tax buffer subtracted from net | `0` (set once tax obligation is known; margins keep packs green at 0) |
| `STRIPE_PRICE_IDS` | `{dollar amount: stripe_price_id}` | (populated after creating test prices) |

`STRIPE_PACKS` is retired — replaced by the calculator + `STRIPE_PRICE_IDS`.

### Worked table (TAX_RATE = 0, discounts 0/5/10/15%, round to nearest 25)

| Tier (margin) | $1 | $5 | $10 | $20 |
|---|---|---|---|---|
| Beta (1.5×) | 450 | — | — | — |
| Friends & Family (5×) | 125 | 950 | 2,075 | 4,400 |
| Standard (20×) | 25 | 250 | 525 | 1,100 |

Every cell satisfies `net > cost_basis`. Example — Standard $20: net `$19.12`, granted 1,100
credits = `$1.10` cost basis (effective ~17.4× after the 15% bulk discount, still well green). The
$1 pack is an entry/convenience tier: Stripe's `$0.30` flat fee eats ~33% of it, so it is the
weakest margin but still profitable at every tier (Beta $1: `$0.45` basis vs `$0.671` net).

## Tiers

`Account.tier` — new column, enum `{beta, friends_family, standard}`, not null.

- **New signups** default to `standard`.
- **Existing accounts** migrated to `beta` (they are early users).
- **Admins** are unaffected by tier for metering (they keep `credit_rate = 0.0`, unmetered) but
  carry a tier value for completeness; default existing admins to `beta`.
- An **admin-only endpoint** sets a profile's tier.

## Data flow

1. `GET /api/payments/packs` — resolves the current account's tier, returns only the dollar tiers in
   that tier's visibility list, each with its **computed** credit amount and price (so the UI shows
   "$5 → 950 credits"). Credits are computed via the calculator, not read from Stripe.
2. `POST /api/payments/checkout` — looks up the Stripe price id for the requested dollar amount from
   `STRIPE_PRICE_IDS`, validates the amount is visible to the buyer's tier, computes credits from
   `(price_amount, tier)`, records a pending `Purchase` storing the buyer's `tier` and computed
   `credits`, and returns the Checkout URL. The tier and credit amount are **locked at checkout**.
3. `POST /api/payments/webhook` and `GET /api/payments/verify` — fulfill by granting the credits
   already stored on the `Purchase` row (idempotent atomic claim, unchanged from the payments spec).

## Components

| Unit | Responsibility | Change |
|---|---|---|
| `db.database.Account` | account row | add `tier` column |
| Alembic migration | schema + data | add `tier`; backfill existing → `beta`; set existing metered accounts' `credit_rate` to 1.0 (admins with rate 0.0 stay 0.0). Required — leaving them at 1.5 would double-count margin (consumption markup **and** purchase markup). |
| `core/credits.py` | ledger + conversion | `credit_rate` default 1.0 |
| `core/payments.py` | pricing | replace flat map with calculator: `tier_margin`, `bulk_discount`, `round25`, `grant_for(price_amount, tier)`, `packs_for_tier(tier)`, profit guard. No Stripe calls. |
| `web/routers/payments.py` | API | tier-aware `/packs`, `/checkout`; store tier+credits on `Purchase`; admin set-tier endpoint |
| `db.database.Purchase` | purchase row | add `tier` column (audit of price applied) |
| `BuyCreditsModal.jsx` | UI | render tier-filtered packs with computed credit amounts |
| Stripe (test mode) | catalog | one "Auto Apply Credits" product, 4 prices ($1/$5/$10/$20) |

## Error handling

- Unknown dollar amount, or amount not visible to the buyer's tier → `400`.
- Account missing → `404` (existing behavior).
- Stripe API failure on checkout → `502` (existing behavior).
- Profit guard reducing credits below 25 (cannot happen with configured margins ≥ 1.5 and fees, but
  defensive): reject the pack with a `500`/config error rather than grant a non-profitable pack.

## Testing

- `core/payments.py` calculator: unit tests for each (tier, price) cell in the worked table;
  property test that `net > cost_basis` for every configured combination; round25 boundaries;
  profit-guard step-down.
- `/packs` returns only tier-visible amounts with correct computed credits.
- `/checkout` rejects amounts not visible to the buyer's tier; stores tier + computed credits.
- Fulfillment grants the stored credit amount (existing idempotency tests still pass).
- Migration: existing accounts land on `beta`; new accounts on `standard`.

## Out of scope

- Stripe Tax integration (real tax calc/collection) — flat `TAX_RATE` buffer only.
- Chargeback/dispute handling; automatic refund clawback (admin-manual, per payments spec).
- Currency conversion / international card surcharges — covered loosely by `TAX_RATE` buffer.
- Self-serve tier changes — admin-only for now.
