import pytest

from core import payments


def test_load_packs_parses_env(monkeypatch):
    monkeypatch.setenv("STRIPE_PACKS", '{"price_a": 5000, "price_b": 15000}')
    assert payments.load_packs() == {"price_a": 5000, "price_b": 15000}


def test_load_packs_empty_when_unset(monkeypatch):
    monkeypatch.delenv("STRIPE_PACKS", raising=False)
    assert payments.load_packs() == {}


def test_credits_for_price_known(monkeypatch):
    monkeypatch.setenv("STRIPE_PACKS", '{"price_a": 5000}')
    assert payments.credits_for_price("price_a") == 5000


def test_credits_for_price_unknown_returns_none(monkeypatch):
    monkeypatch.setenv("STRIPE_PACKS", '{"price_a": 5000}')
    assert payments.credits_for_price("nope") is None
