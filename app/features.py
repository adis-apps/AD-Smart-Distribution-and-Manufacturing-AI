"""Win-probability features, shared by training and inference so they cannot drift apart.

Price is measured three ways:
  * price_vs_list        - always available (our own list price), so the model stays
                           price-sensitive even when no competitor price was recorded.
  * price_vs_competitor  - only when a competitor price is known; 0 otherwise, with
                           has_competitor telling the model which case it is in.
  * price_vs_list_no_competitor - price_vs_list again, but only on quotes with no competitor
                           price (0 otherwise). Without it, a linear model shares one list-price
                           slope across both cases and learns only the small residual effect seen
                           when the competitor price is known, making no-competitor quotes look
                           almost price-insensitive.
"""
import numpy as np
import pandas as pd

NUMERIC = ["price_vs_list", "price_vs_competitor", "price_vs_list_no_competitor", "has_competitor", "quantity_log"]
CATEGORICAL = ["segment", "product_id", "customer_id", "credit_hold"]
FEATURES = NUMERIC + CATEGORICAL


def _rel(price, ref):
    return (price - ref) / ref if ref and ref > 0 else 0.0


def build_row(*, price: float, list_price: float | None, competitor_price: float | None, quantity: float,
              segment: str, product_id: str, customer_id: str, credit_hold: bool) -> dict:
    has_comp = competitor_price is not None and competitor_price > 0
    vs_list = float(_rel(price, list_price))
    return {
        "price_vs_list": vs_list,
        "price_vs_competitor": float(_rel(price, competitor_price)) if has_comp else 0.0,
        "price_vs_list_no_competitor": 0.0 if has_comp else vs_list,
        "has_competitor": float(has_comp),
        "quantity_log": float(np.log1p(max(0.0, float(quantity)))),
        "segment": str(segment or "Unknown"),
        "product_id": str(product_id or "Unknown"),
        "customer_id": str(customer_id or "Unknown"),
        "credit_hold": str(int(bool(credit_hold))),
    }


def build_frame(quotes: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """Training features from quote history joined to product list prices."""
    df = quotes.merge(products[["product_id", "list_price"]], on="product_id", how="left")
    comp = pd.to_numeric(df["competitor_price"], errors="coerce")
    has_comp = comp.notna() & (comp > 0)
    vs_list = (df["quoted_price"] - df["list_price"]) / df["list_price"]
    out = pd.DataFrame({
        "price_vs_list": vs_list,
        "price_vs_competitor": np.where(has_comp, (df["quoted_price"] - comp) / comp.where(has_comp, 1), 0.0),
        "price_vs_list_no_competitor": np.where(has_comp, 0.0, vs_list),
        "has_competitor": has_comp.astype(float),
        "quantity_log": np.log1p(df["quantity"].clip(lower=0)),
        "segment": df["segment"].fillna("Unknown").astype(str),
        "product_id": df["product_id"].astype(str),
        "customer_id": df["customer_id"].astype(str),
        "credit_hold": df["credit_hold"].fillna(0).astype(int).astype(str),
    })
    return out[FEATURES]
