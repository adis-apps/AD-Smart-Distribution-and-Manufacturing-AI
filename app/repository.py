import pandas as pd
from sqlalchemy import text
from app.db import engine

def rows(query, params=None):
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params=params or {})

def get_product(product_id):
    df=rows("SELECT * FROM products WHERE product_id=:id", {"id":product_id})
    return None if df.empty else df.iloc[0].to_dict()

def get_customer(customer_id):
    df=rows("SELECT * FROM customers WHERE customer_id=:id", {"id":customer_id})
    return None if df.empty else df.iloc[0].to_dict()

def get_inventory(product_id):
    df=rows("SELECT * FROM inventory WHERE product_id=:id", {"id":product_id})
    return None if df.empty else df.iloc[0].to_dict()

def get_history(customer_id, product_id):
    return rows("SELECT * FROM quote_history WHERE customer_id=:c AND product_id=:p", {"c":customer_id,"p":product_id})

def reference_data():
    return {"products":rows("SELECT product_id,product_name,category,unit_of_measure,list_price FROM products").to_dict("records"),
            "customers":rows("SELECT customer_id,customer_name,segment,credit_hold FROM customers").to_dict("records")}


def get_quote_context(customer_id, product_id):
    """Return pair-specific current price and product-level competitor benchmark.

    Current price is the latest recorded quote for this exact customer/product pair.
    Competitor benchmark is the latest non-null observation for this product.
    These are demo source rules; production should use effective-dated ERP price lists
    and a governed competitor-observation feed.
    """
    customer_price = rows(
        "SELECT quoted_price, quote_date, quote_id FROM quote_history "
        "WHERE customer_id=:c AND product_id=:p ORDER BY quote_date DESC, quote_id DESC LIMIT 1",
        {"c": customer_id, "p": product_id})
    competitor = rows(
        "SELECT competitor_price, quote_date, quote_id FROM quote_history "
        "WHERE product_id=:p AND competitor_price IS NOT NULL "
        "ORDER BY quote_date DESC, quote_id DESC LIMIT 1", {"p": product_id})
    hist = rows(
        "SELECT COUNT(*) AS quote_count, AVG(quoted_price) AS average_price "
        "FROM quote_history WHERE customer_id=:c AND product_id=:p",
        {"c": customer_id, "p": product_id}).iloc[0].to_dict()
    current = None if customer_price.empty else float(customer_price.iloc[0]["quoted_price"])
    current_date = None if customer_price.empty else str(customer_price.iloc[0]["quote_date"])
    comp = None if competitor.empty else float(competitor.iloc[0]["competitor_price"])
    comp_date = None if competitor.empty else str(competitor.iloc[0]["quote_date"])
    competitor_age_days = None
    competitor_stale = False
    if comp_date:
        from datetime import date
        try:
            competitor_age_days = (date.today() - date.fromisoformat(comp_date[:10])).days
            if competitor_age_days < 0 or competitor_age_days > 90:
                competitor_stale = True
                comp = None
        except ValueError:
            competitor_stale = True
            comp = None
    return {
        "customer_id": customer_id, "product_id": product_id,
        "current_price": current, "current_price_date": current_date,
        "current_price_source": "latest_quote_for_customer_product" if current is not None else "not_available",
        "competitor_price": comp, "competitor_price_date": comp_date,
        "competitor_price_age_days": competitor_age_days, "competitor_price_stale": competitor_stale,
        "competitor_price_source": ("latest_product_observation" if comp is not None else ("stale_observation_not_prefilled" if competitor_stale else "not_available")),
        "customer_product_quote_count": int(hist["quote_count"] or 0),
        "customer_product_average_price": None if hist["average_price"] is None else float(hist["average_price"]),
    }

def get_cost_profile(product_id):
    df=rows("SELECT * FROM product_cost_profiles WHERE product_id=:id", {"id":product_id})
    return None if df.empty else df.iloc[0].to_dict()

def get_active_agreement(customer_id, product_id, today=None):
    from datetime import date
    today = today or date.today().isoformat()
    df=rows("SELECT * FROM price_agreements WHERE customer_id=:c AND product_id=:p AND status='active' AND start_date<=:d AND end_date>=:d ORDER BY start_date DESC LIMIT 1", {"c":customer_id,"p":product_id,"d":today})
    return None if df.empty else df.iloc[0].to_dict()

def get_quantity_tier(customer_id, product_id, quantity, today=None):
    from datetime import date
    today = today or date.today().isoformat()
    df=rows("SELECT * FROM quantity_tiers WHERE product_id=:p AND (customer_id=:c OR customer_id IS NULL) AND status='active' AND min_quantity<=:q AND (max_quantity IS NULL OR max_quantity>=:q) AND (start_date IS NULL OR start_date<=:d) AND (end_date IS NULL OR end_date>=:d) ORDER BY CASE WHEN customer_id=:c THEN 0 ELSE 1 END, min_quantity DESC LIMIT 1", {"c":customer_id,"p":product_id,"q":quantity,"d":today})
    return None if df.empty else df.iloc[0].to_dict()
