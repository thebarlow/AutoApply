from core.pricing import DEFAULT_PRICES, price_for


def test_map_fields_price_registered():
    assert "map_fields" in DEFAULT_PRICES
    assert price_for("map_fields") == DEFAULT_PRICES["map_fields"]
