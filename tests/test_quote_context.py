from app.repository import get_quote_context


def test_quote_context_is_scoped_to_customer_product_pair():
    ctx = get_quote_context("CUST-001", "BAG-001")
    assert ctx["customer_id"] == "CUST-001"
    assert ctx["product_id"] == "BAG-001"
    assert ctx["current_price"] is not None
    assert ctx["competitor_price"] is not None
    assert ctx["customer_product_quote_count"] > 0


def test_quote_context_does_not_use_other_products_history_for_current_price():
    ctx = get_quote_context("CUST-001", "BOX-003")
    assert ctx["customer_id"] == "CUST-001"
    assert ctx["product_id"] == "BOX-003"
    assert ctx["customer_product_quote_count"] > 0
    assert ctx["current_price_source"] == "latest_quote_for_customer_product"
