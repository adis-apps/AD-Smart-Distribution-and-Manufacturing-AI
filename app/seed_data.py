"""Synthetic data generator for the Pricing & Margin Copilot POC.

Every number here is a simulation assumption, not a fact about real customers.
Design goals (v0.5):
  * List prices sit above each product's margin floor, so history is commercially plausible.
  * Each product has a unit of measure and its own realistic order-quantity range.
  * Competitor prices exist for every quote in the simulated market, but only ~80% are
    *observed* (recorded); the rest are missing, as in real CRM data.
  * Credit hold is a per-quote state (customers go on/off hold), so its effect is
    separable from customer identity.
  * Dates are anchored to a fixed date so runs are reproducible.
  * Customer annual_revenue (annual spend with us) is derived from the won quotes it
    generated, so the two are consistent.
"""
import os
import random
from datetime import date, timedelta
import numpy as np
import pandas as pd
from sqlalchemy import text
from app.config import DATA_DIR
from app.db import engine, init_db

SEED = int(os.getenv("SYNTHETIC_SEED", "42"))
ANCHOR_DATE = date.fromisoformat(os.getenv("SYNTHETIC_ANCHOR_DATE", "2026-09-30"))
N_QUOTES = int(os.getenv("SYNTHETIC_N_QUOTES", "1200"))
HISTORY_DAYS = 720

# --- Simulated market behaviour (documented assumptions) ---------------------------
PRICE_SENSITIVITY = 16.0        # logit change per 1.00 (=100%) price premium over competitor
COMPETITOR_OBSERVED_RATE = 0.80 # share of quotes where the rep recorded a competitor price
INTERCEPT = 0.55
CREDIT_HOLD_EFFECT = -0.70
QUANTITY_EFFECT_MAX = 0.40      # larger deals within a product's range win slightly more often
CUSTOMER_EFFECT = {"CUST-001": 0.12, "CUST-002": 0.25, "CUST-003": -0.08, "CUST-004": -0.30,
                   "CUST-005": 0.16, "CUST-006": 0.02}
SEGMENT_EFFECT = {"Distributor": 0.18, "Food & Beverage": 0.10, "Industrial": 0.00, "Retail": -0.08}
CREDIT_HOLD_RATE = {"CUST-004": 0.85}  # others default to CREDIT_HOLD_BASE_RATE
CREDIT_HOLD_BASE_RATE = 0.04

PRODUCTS = [
    dict(product_id="BAG-001", product_name="Zip Top Bag 5x6 2mil", unit_of_measure="case of 1,000",
         category="Flexible Packaging", material_cost=15.20, labor_cost=2.10, overhead_cost=2.00,
         freight_cost=1.30, tariff_cost=0.0, min_margin_pct=0.15, list_price=28.50),
    dict(product_id="FILM-002", product_name="Pallet Stretch Film 18in", unit_of_measure="roll",
         category="Stretch Film", material_cost=31.0, labor_cost=2.8, overhead_cost=3.2,
         freight_cost=2.4, tariff_cost=0.5, min_margin_pct=0.18, list_price=56.00),
    dict(product_id="BOX-003", product_name="Corrugated Shipping Box M", unit_of_measure="each",
         category="Corrugated", material_cost=0.72, labor_cost=0.18, overhead_cost=0.14,
         freight_cost=0.12, tariff_cost=0.0, min_margin_pct=0.16, list_price=1.69),
    dict(product_id="TAPE-004", product_name="Carton Sealing Tape 48mm", unit_of_measure="roll",
         category="Packaging Supplies", material_cost=1.15, labor_cost=0.20, overhead_cost=0.18,
         freight_cost=0.14, tariff_cost=0.0, min_margin_pct=0.20, list_price=2.55),
    dict(product_id="PAL-005", product_name="Reusable Plastic Pallet", unit_of_measure="each",
         category="Material Handling", material_cost=19.0, labor_cost=2.4, overhead_cost=2.2,
         freight_cost=3.5, tariff_cost=0.4, min_margin_pct=0.17, list_price=39.50),
]
QUANTITY_CHOICES = {
    "BAG-001": [20, 50, 100, 200, 500, 1000, 2000],
    "FILM-002": [50, 100, 250, 500, 1000, 2500],
    "BOX-003": [1000, 2500, 5000, 10000, 25000, 50000, 100000],
    "TAPE-004": [500, 1000, 2500, 5000, 10000, 25000],
    "PAL-005": [25, 50, 100, 250, 500, 1000],
}
INVENTORY = {"BAG-001": (1500, 42), "FILM-002": (1800, 19), "BOX-003": (150000, 55),
             "TAPE-004": (30000, 73), "PAL-005": (800, 12)}
CUSTOMERS = [
    dict(customer_id="CUST-001", customer_name="ABC Food Packaging", segment="Food & Beverage", payment_terms=30, credit_hold=False, target_margin_pct=0.18),
    dict(customer_id="CUST-002", customer_name="Northstar Distribution", segment="Distributor", payment_terms=45, credit_hold=False, target_margin_pct=0.20),
    dict(customer_id="CUST-003", customer_name="Metro Industrial Supply", segment="Industrial", payment_terms=30, credit_hold=False, target_margin_pct=0.19),
    dict(customer_id="CUST-004", customer_name="ValuePack Retail", segment="Retail", payment_terms=60, credit_hold=True, target_margin_pct=0.21),
    dict(customer_id="CUST-005", customer_name="Greenline Packaging", segment="Food & Beverage", payment_terms=30, credit_hold=False, target_margin_pct=0.17),
    dict(customer_id="CUST-006", customer_name="Summit Warehouse Group", segment="Industrial", payment_terms=45, credit_hold=False, target_margin_pct=0.20),
]


def write_csv(name, rows):
    pd.DataFrame(rows).to_csv(DATA_DIR / name, index=False)


def generate_history(rng: random.Random, np_rng: np.random.Generator, n: int = N_QUOTES):
    """Return (quote rows, true win probabilities). True probabilities are for diagnostics only."""
    history, true_p = [], []
    for qid in range(1, n + 1):
        c = rng.choice(CUSTOMERS); p = rng.choice(PRODUCTS)
        cid, pid, lp = c["customer_id"], p["product_id"], p["list_price"]
        choices = QUANTITY_CHOICES[pid]
        qty = rng.choice(choices)
        # Competitors usually price at or below our list.
        competitor = lp * rng.uniform(0.86, 1.02)
        discount = min(0.22, max(-0.05, rng.gauss(0.06, 0.06)))
        price = round(lp * (1 - discount), 4)
        rel = (price - competitor) / competitor
        qty_pos = (np.log(qty) - np.log(choices[0])) / (np.log(choices[-1]) - np.log(choices[0]))
        # Match inference semantics: the training feature is the customer's credit status, not a random per-quote event.
        on_hold = bool(c["credit_hold"])
        logit = (INTERCEPT - PRICE_SENSITIVITY * rel + QUANTITY_EFFECT_MAX * qty_pos
                 + SEGMENT_EFFECT[c["segment"]] + CUSTOMER_EFFECT[cid] + (CREDIT_HOLD_EFFECT if on_hold else 0))
        prob = 1 / (1 + np.exp(-logit))
        won = int(np_rng.random() < prob)
        observed = rng.random() < COMPETITOR_OBSERVED_RATE
        history.append(dict(
            quote_id=f"Q-{qid:05d}", customer_id=cid, product_id=pid, quantity=qty,
            quoted_price=price, competitor_price=round(competitor, 4) if observed else None,
            won=won, quote_date=(ANCHOR_DATE - timedelta(days=rng.randint(0, HISTORY_DAYS))).isoformat(),
            segment=c["segment"], credit_hold=int(on_hold)))
        true_p.append(prob)
    return history, np.array(true_p)


def main():
    rng = random.Random(SEED)
    np_rng = np.random.default_rng(SEED)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    products = [dict(p) for p in PRODUCTS]
    customers = [dict(c) for c in CUSTOMERS]
    history, _ = generate_history(rng, np_rng)

    # annual_revenue = this customer's annual spend with us, derived from won quotes.
    years = HISTORY_DAYS / 365
    won_value = pd.DataFrame(history).query("won == 1").assign(v=lambda d: d.quantity * d.quoted_price)
    spend = (won_value.groupby("customer_id").v.sum() / years).round(-3)
    for c in customers:
        c["annual_revenue"] = float(spend.get(c["customer_id"], 0.0))

    inventory = [dict(product_id=pid, available_qty=q, days_on_hand=d) for pid, (q, d) in INVENTORY.items()]
    cost_profiles = []
    for i, p in enumerate(products):
        cost_profiles.append(dict(product_id=p["product_id"], setup_cost=[180, 250, 80, 45, 300][i],
            engineering_cost=[120, 180, 35, 20, 150][i], setup_allocation_qty=[1000, 2000, 20000, 10000, 500][i],
            cost_to_serve_unit=[.12, .18, .025, .03, .45][i], capacity_utilization_pct=[72, 94, 38, 25, 88][i],
            expedite_premium_pct=.03, guaranteed_inventory_premium_pct=.02, warranty_premium_pct=.02,
            regulatory_premium_pct=.015, sustainability_premium_pct=.01))
    valid_from = (ANCHOR_DATE - timedelta(days=30)).isoformat()
    valid_to = (ANCHOR_DATE + timedelta(days=730)).isoformat()
    agreements = [dict(agreement_id="SPA-CUST001-BAG001", customer_id="CUST-001", product_id="BAG-001",
                       contract_price=26.75, start_date=valid_from, end_date=valid_to, status="active",
                       notes="Synthetic example only; replace with customer-approved agreement data.")]
    tiers = []
    for p in products:
        q = QUANTITY_CHOICES[p["product_id"]]
        t1, t2 = q[-3], q[-2]  # product-specific break points near the top of its order range
        tiers.extend([
            dict(tier_id=f"TIER-{p['product_id']}-T1", product_id=p["product_id"], customer_id=None, min_quantity=t1,
                 max_quantity=t2 - 1, discount_pct=1.5, start_date=(ANCHOR_DATE - timedelta(days=365)).isoformat(),
                 end_date=valid_to, status="active"),
            dict(tier_id=f"TIER-{p['product_id']}-T2", product_id=p["product_id"], customer_id=None, min_quantity=t2,
                 max_quantity=None, discount_pct=3.0, start_date=(ANCHOR_DATE - timedelta(days=365)).isoformat(),
                 end_date=valid_to, status="active")])

    write_csv("products.csv", products); write_csv("customers.csv", customers); write_csv("inventory.csv", inventory)
    write_csv("quote_history.csv", history); write_csv("product_cost_profiles.csv", cost_profiles)
    write_csv("price_agreements.csv", agreements); write_csv("quantity_tiers.csv", tiers)
    init_db()
    with engine.begin() as conn:
        # Delete dependent rows before their parent rows (required by PostgreSQL FKs).
        for table, rows in [("quote_decision_audit", []), ("recommendation_feedback", []),
                            ("quote_history", history), ("inventory", inventory),
                            ("product_cost_profiles", cost_profiles), ("price_agreements", agreements),
                            ("quantity_tiers", tiers), ("products", products), ("customers", customers)]:
            conn.execute(text(f"DELETE FROM {table}"))
            if rows:
                cols = list(rows[0].keys())
                # credit_hold is a per-quote training feature kept in the CSV, not a quote_history DB column.
                if table == "quote_history":
                    cols = [x for x in cols if x != "credit_hold"]
                    rows = [{k: v for k, v in row.items() if k in cols} for row in rows]
                sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(':' + c for c in cols)})"
                conn.execute(text(sql), rows)
    from app.ops_agents import seed_ops_data
    ops_counts = seed_ops_data()
    print(f"Seeded operations demo data: {ops_counts}")
    print(f"Seeded {len(products)} products, {len(customers)} customers, {len(history)} synthetic quotes "
          f"(anchor {ANCHOR_DATE}, seed {SEED}) into {engine.url} and CSVs in {DATA_DIR}")


if __name__ == "__main__":
    main()
