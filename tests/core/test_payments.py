"""Pricing calculator: unit-denominated packs, tier multipliers, bulk discounts, fees."""

import pytest

from core import payments


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Force all calculator config to its documented defaults.
    for k in (
        "CREDIT_TIER_MULTIPLIERS",
        "CREDIT_PRICE_TIERS",
        "CREDIT_TIER_VISIBILITY",
        "STRIPE_FEE_PCT",
        "STRIPE_FEE_FIXED",
        "TAX_RATE",
        "STRIPE_PRICE_IDS",
        "CREDIT_UNIT_USD",
    ):
        monkeypatch.delenv(k, raising=False)


def test_compute_credits_standard():
    # $5 pack: net = 5 - (0.30 + 5*0.029) = 4.555; /0.02 = 227.75; x1; +5% bulk discount
    got = payments.compute_credits(5, "standard")
    assert got == round(4.555 / 0.02 * 1.0 * 1.05)  # 239


def test_compute_credits_beta_multiplier():
    std = payments.compute_credits(5, "standard")
    beta = payments.compute_credits(5, "beta")
    assert beta == pytest.approx(std * 10, rel=0.01)


def test_unknown_tier_raises():
    with pytest.raises(ValueError):
        payments.compute_credits(5, "nope")


def test_every_configured_pack_is_profitable():
    for tier, amounts in payments.tier_visibility().items():
        for price in amounts:
            units = payments.compute_credits(price, tier)
            assert units > 0, (tier, price)


_ALL_PRICE_IDS = '{"1": "price_1", "5": "price_5", "10": "price_10", "20": "price_20"}'


def test_packs_for_tier_beta_only_dollar_one(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_IDS", _ALL_PRICE_IDS)
    packs = payments.packs_for_tier("beta")
    assert [p["amount_usd"] for p in packs] == [1]
    assert packs[0]["discount"] == 0


def test_packs_for_tier_standard_all_four(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_IDS", _ALL_PRICE_IDS)
    packs = payments.packs_for_tier("standard")
    assert [p["amount_usd"] for p in packs] == [1, 5, 10, 20]


def test_packs_for_tier_skips_amounts_without_a_price_id(monkeypatch):
    # Only $1 and $5 have configured Stripe price ids -> the other visible
    # amounts ($10, $20) are omitted rather than returned un-purchasable.
    monkeypatch.setenv("STRIPE_PRICE_IDS", '{"1": "price_1", "5": "price_5"}')
    packs = payments.packs_for_tier("standard")
    assert [p["amount_usd"] for p in packs] == [1, 5]


def test_packs_for_tier_empty_when_no_price_ids():
    # STRIPE_PRICE_IDS unset (via the autouse fixture) -> nothing sellable.
    assert payments.packs_for_tier("standard") == []


def test_packs_for_tier_uses_configured_price_ids(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_IDS", '{"1": "price_one", "5": "price_five"}')
    packs = payments.packs_for_tier("friends_family")
    by_amt = {p["amount_usd"]: p["price_id"] for p in packs}
    assert by_amt[1] == "price_one"
    assert by_amt[5] == "price_five"


def test_resolve_price_id_returns_amount_and_credits(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_IDS", '{"5": "price_five"}')
    amount, credits = payments.resolve_price_id("price_five", "standard")
    assert amount == 5
    assert credits == payments.compute_credits(5, "standard")


def test_resolve_price_id_not_visible_to_tier_returns_none(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_IDS", '{"20": "price_twenty"}')
    # $20 is not visible to beta.
    assert payments.resolve_price_id("price_twenty", "beta") is None


def test_resolve_price_id_unknown_returns_none():
    assert payments.resolve_price_id("price_unknown", "standard") is None
