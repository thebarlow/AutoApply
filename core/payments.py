"""Tier-aware credit-pack pricing.

Margin lives on the *purchase* side: the same dollar amount buys different
credit counts per user tier. Credits mirror raw API cost 1:1 on consumption
(``credit_rate`` is 1.0 for metered users), so every feature costs the same
credits for everyone. All functions here are pure config math — no Stripe calls.
"""

from __future__ import annotations

import json
import math
import os

CREDITS_PER_DOLLAR = 1000

_DEFAULT_MARGINS = {"beta": 1.5, "friends_family": 5.0, "standard": 20.0}
_DEFAULT_PRICE_TIERS = {1: 0.0, 5: 0.05, 10: 0.10, 20: 0.15}
_DEFAULT_VISIBILITY = {
    "beta": [1],
    "friends_family": [1, 5, 10, 20],
    "standard": [1, 5, 10, 20],
}


def _env_json(key: str) -> dict | None:
    raw = os.getenv(key, "").strip()
    return json.loads(raw) if raw else None


def tier_margins() -> dict[str, float]:
    """Tier name -> profit margin multiplier applied to net proceeds."""
    cfg = _env_json("CREDIT_TIER_MARGINS")
    if not cfg:
        return dict(_DEFAULT_MARGINS)
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


def _round25(x: float) -> int:
    """Round to the nearest 25 (ties round up)."""
    return int(math.floor(x / 25.0 + 0.5)) * 25


def compute_credits(price_usd: int, tier: str) -> int:
    """Credits granted for a pack, computed from tier margin, bulk discount, fees.

    Raises:
        ValueError: if the tier is unknown or the pack cannot be made profitable.
    """
    margins = tier_margins()
    if tier not in margins:
        raise ValueError(f"unknown tier: {tier}")
    discount = price_tiers().get(price_usd, 0.0)
    net = _net(price_usd)
    cost_basis = net / margins[tier]
    credits = _round25(cost_basis * CREDITS_PER_DOLLAR * (1 + discount))
    # Profit guard: never grant credits whose committed cost basis meets/exceeds net.
    while credits > 0 and net <= credits / CREDITS_PER_DOLLAR:
        credits -= 25
    if credits <= 0:
        raise ValueError(f"pack ${price_usd} for tier {tier} is not profitable")
    return credits


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
