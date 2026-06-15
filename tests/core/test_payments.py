"""Pricing calculator: tier margins, bulk discounts, fees, profit guard."""
import pytest

from core import payments


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Force all calculator config to its documented defaults.
    for k in ("CREDIT_TIER_MARGINS", "CREDIT_PRICE_TIERS", "CREDIT_TIER_VISIBILITY",
              "STRIPE_FEE_PCT", "STRIPE_FEE_FIXED", "TAX_RATE", "STRIPE_PRICE_IDS"):
        monkeypatch.delenv(k, raising=False)


@pytest.mark.parametrize("tier,price,expected", [
    ("beta", 1, 450),
    ("friends_family", 1, 125),
    ("friends_family", 5, 950),
    ("friends_family", 10, 2075),
    ("friends_family", 20, 4400),
    ("standard", 1, 25),
    ("standard", 5, 250),
    ("standard", 10, 525),
    ("standard", 20, 1100),
])
def test_compute_credits_matches_worked_table(tier, price, expected):
    assert payments.compute_credits(price, tier) == expected


def test_every_configured_pack_is_profitable():
    for tier, amounts in payments.tier_visibility().items():
        for price in amounts:
            credits = payments.compute_credits(price, tier)
            net = payments._net(price)
            assert net > credits / payments.CREDITS_PER_DOLLAR, (tier, price)


def test_packs_for_tier_beta_only_dollar_one():
    packs = payments.packs_for_tier("beta")
    assert [p["amount_usd"] for p in packs] == [1]
    assert packs[0]["credits"] == 450
    assert packs[0]["discount"] == 0


def test_packs_for_tier_standard_all_four():
    packs = payments.packs_for_tier("standard")
    assert [p["amount_usd"] for p in packs] == [1, 5, 10, 20]


def test_packs_for_tier_uses_configured_price_ids(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_IDS", '{"1": "price_one", "5": "price_five"}')
    packs = payments.packs_for_tier("friends_family")
    by_amt = {p["amount_usd"]: p["price_id"] for p in packs}
    assert by_amt[1] == "price_one"
    assert by_amt[5] == "price_five"


def test_resolve_price_id_returns_amount_and_credits(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_IDS", '{"5": "price_five"}')
    assert payments.resolve_price_id("price_five", "standard") == (5, 250)


def test_resolve_price_id_not_visible_to_tier_returns_none(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_IDS", '{"20": "price_twenty"}')
    # $20 is not visible to beta.
    assert payments.resolve_price_id("price_twenty", "beta") is None


def test_resolve_price_id_unknown_returns_none():
    assert payments.resolve_price_id("price_unknown", "standard") is None


def test_round25():
    assert payments._round25(33.55) == 25
    assert payments._round25(239.14) == 250
    assert payments._round25(12.5) == 25  # ties round up
