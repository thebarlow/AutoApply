"""Tier-aware credit-pack pricing.

Packs are denominated in fixed-price units (``core.pricing.unit_usd()``):
a pack's net proceeds convert to units at the unit price, then scale by a
tier purchasing-power multiplier and any bulk discount. All functions here
are pure config math — no Stripe calls.
"""

from __future__ import annotations

import json
import os

_DEFAULT_MULTIPLIERS = {"standard": 1.0, "friends_family": 4.0, "beta": 10.0}
_DEFAULT_PRICE_TIERS = {1: 0.0, 5: 0.05, 10: 0.10, 20: 0.15}
_DEFAULT_VISIBILITY = {
    "beta": [1],
    "friends_family": [1, 5, 10, 20],
    "standard": [1, 5, 10, 20],
}


def _env_json(key: str) -> dict | None:
    raw = os.getenv(key, "").strip()
    return json.loads(raw) if raw else None


def tier_multipliers() -> dict[str, float]:
    """Tier name -> pack purchasing-power multiplier."""
    cfg = _env_json("CREDIT_TIER_MULTIPLIERS")
    if not cfg:
        return dict(_DEFAULT_MULTIPLIERS)
    return {str(k): float(v) for k, v in cfg.items()}


def price_tiers() -> dict[int, float]:
    """Dollar amount -> bulk discount fraction."""
    cfg = _env_json("CREDIT_PRICE_TIERS")
    if not cfg:
        return dict(_DEFAULT_PRICE_TIERS)
    return {int(k): float(v) for k, v in cfg.items()}


def tier_visibility() -> dict[str, list[int]]:
    """Tier name -> list of dollar pack amounts visible to that tier."""
    cfg = _env_json("CREDIT_TIER_VISIBILITY")
    if not cfg:
        return {k: list(v) for k, v in _DEFAULT_VISIBILITY.items()}
    return {str(k): [int(a) for a in v] for k, v in cfg.items()}


def price_ids() -> dict[int, str]:
    """Dollar amount -> Stripe price id (from STRIPE_PRICE_IDS env)."""
    cfg = _env_json("STRIPE_PRICE_IDS")
    if not cfg:
        return {}
    return {int(k): str(v) for k, v in cfg.items()}


def _fee_pct() -> float:
    return float(os.getenv("STRIPE_FEE_PCT", "0.029"))


def _fee_fixed() -> float:
    return float(os.getenv("STRIPE_FEE_FIXED", "0.30"))


def _tax_rate() -> float:
    return float(os.getenv("TAX_RATE", "0"))


def _net(price_usd: float) -> float:
    """Dollars the platform keeps after Stripe's cut and the tax buffer."""
    return price_usd - (_fee_pct() * price_usd + _fee_fixed()) - _tax_rate() * price_usd


def compute_credits(price_usd: int, tier: str) -> int:
    """Units granted for a pack: net proceeds ÷ UNIT_USD × tier multiplier,
    plus the bulk discount. Replaces the cost-margin model (meaningless at
    near-zero LLM cost).

    Raises:
        ValueError: if the tier is unknown or the pack cannot be made profitable.
    """
    from core.pricing import unit_usd

    mults = tier_multipliers()
    if tier not in mults:
        raise ValueError(f"unknown tier: {tier}")
    discount = price_tiers().get(price_usd, 0.0)
    units = round(_net(price_usd) / unit_usd() * mults[tier] * (1 + discount))
    if units <= 0:
        raise ValueError(f"pack ${price_usd} for tier {tier} is not profitable")
    return units


def packs_for_tier(tier: str) -> list[dict]:
    """Visible, purchasable packs for a tier, each with computed credits.

    A pack is included only if its dollar amount has a configured Stripe price id
    (``STRIPE_PRICE_IDS``); amounts without one are skipped so the UI never shows
    a pack that cannot be checked out (which would post a null ``price_id``).
    """
    ids = price_ids()
    discounts = price_tiers()
    out = []
    for amount in tier_visibility().get(tier, []):
        price_id = ids.get(amount)
        if price_id is None:
            continue
        out.append(
            {
                "price_id": price_id,
                "amount_usd": amount,
                "credits": compute_credits(amount, tier),
                "discount": discounts.get(amount, 0.0),
            }
        )
    return out


def resolve_price_id(price_id: str, tier: str) -> tuple[int, int] | None:
    """Map a Stripe price id to (dollar amount, credits) for this tier.

    Returns None if the price id is unknown or the amount is not visible to the
    tier (prevents buying a pack outside your tier by passing a foreign price id).
    """
    amount = next((amt for amt, pid in price_ids().items() if pid == price_id), None)
    if amount is None or amount not in tier_visibility().get(tier, []):
        return None
    return amount, compute_credits(amount, tier)
