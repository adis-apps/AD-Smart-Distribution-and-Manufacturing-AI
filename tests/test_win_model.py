"""Regression tests for the win-probability model and how the optimizer uses it."""
import numpy as np
import pytest
from app.ml_model import win_probability, load_model
from app.pricing_engine import recommend

PRODUCT = {"product_id": "BAG-001", "product_name": "Zip Top Bag", "material_cost": 15.2, "labor_cost": 2.1,
           "overhead_cost": 2.0, "freight_cost": 1.3, "tariff_cost": 0, "min_margin_pct": .15, "list_price": 28.5}
CUSTOMER = {"customer_id": "CUST-001", "customer_name": "ABC", "segment": "Food & Beverage",
            "target_margin_pct": .18, "credit_hold": False}
INVENTORY = {"available_qty": 1500, "days_on_hand": 40}

needs_model = pytest.mark.skipif(load_model() is None, reason="run `python -m app.train_model` first")


def _p(price, competitor):
    return win_probability({"price": price, "list_price": 28.5, "competitor_price": competitor, "quantity": 200,
                            "segment": "Food & Beverage", "product_id": "BAG-001", "customer_id": "CUST-001",
                            "credit_hold": False})


@needs_model
@pytest.mark.parametrize("competitor", [26.0, None])
def test_win_probability_falls_as_price_rises(competitor):
    probs = [_p(price, competitor)[0] for price in np.linspace(22, 36, 15)]
    assert all(a >= b for a, b in zip(probs, probs[1:])), probs
    assert probs[0] - probs[-1] > 0.15  # meaningfully price-sensitive, with or without a competitor
    assert _p(28.5, competitor)[1] == "model"


@needs_model
def test_missing_competitor_does_not_push_price_to_top_of_range():
    req = {"quantity": 200, "current_price": 27.0}
    blank = recommend(PRODUCT, CUSTOMER, INVENTORY, None, dict(req, competitor_price=None))
    upper = max(27.0 * 1.12, blank["target_margin_price"] * 1.18, blank["minimum_price"] * 1.08)
    assert blank["recommended_price"] < upper * 0.97
    assert blank["win_probability_source"] == "model"
    # A blank competitor must not produce a higher price AND a higher win probability than a typical one.
    typical = recommend(PRODUCT, CUSTOMER, INVENTORY, None, dict(req, competitor_price=26.5))
    assert not (blank["recommended_price"] > typical["recommended_price"]
                and blank["win_probability_pct"] > typical["win_probability_pct"])


def test_competitor_scenario_omitted_when_unknown():
    result = recommend(PRODUCT, CUSTOMER, INVENTORY, None, {"quantity": 200, "current_price": 27.0})
    assert "Competitor" not in [s["scenario"] for s in result["scenarios"]]
