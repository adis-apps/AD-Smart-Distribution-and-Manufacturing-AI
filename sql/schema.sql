-- PostgreSQL schema for Pricing & Margin Copilot. Mirrors app/db.py.
CREATE TABLE IF NOT EXISTS products (
  product_id VARCHAR(40) PRIMARY KEY, product_name VARCHAR(200) NOT NULL, category VARCHAR(100),
  material_cost NUMERIC(12,4) NOT NULL, labor_cost NUMERIC(12,4) NOT NULL,
  overhead_cost NUMERIC(12,4) NOT NULL, freight_cost NUMERIC(12,4) NOT NULL,
  tariff_cost NUMERIC(12,4) NOT NULL DEFAULT 0, min_margin_pct NUMERIC(8,5) NOT NULL DEFAULT 0.15,
  list_price NUMERIC(12,4), unit_of_measure VARCHAR(40)
);
CREATE TABLE IF NOT EXISTS customers (
  customer_id VARCHAR(40) PRIMARY KEY, customer_name VARCHAR(200) NOT NULL, segment VARCHAR(80),
  payment_terms INTEGER, credit_hold BOOLEAN DEFAULT FALSE, target_margin_pct NUMERIC(8,5) DEFAULT 0.18,
  annual_revenue NUMERIC(14,2) DEFAULT 0
);
CREATE TABLE IF NOT EXISTS inventory (
  product_id VARCHAR(40) PRIMARY KEY REFERENCES products(product_id), available_qty INTEGER NOT NULL DEFAULT 0,
  days_on_hand INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS quote_history (
  quote_id VARCHAR(40) PRIMARY KEY, customer_id VARCHAR(40) NOT NULL REFERENCES customers(customer_id),
  product_id VARCHAR(40) NOT NULL REFERENCES products(product_id), quantity INTEGER NOT NULL,
  quoted_price NUMERIC(12,4) NOT NULL, competitor_price NUMERIC(12,4), won SMALLINT NOT NULL,
  quote_date DATE, segment VARCHAR(80)
);
CREATE INDEX IF NOT EXISTS idx_quote_history_customer_product ON quote_history(customer_id, product_id);
CREATE TABLE IF NOT EXISTS recommendation_feedback (
  id BIGSERIAL PRIMARY KEY, customer_id VARCHAR(40), product_id VARCHAR(40), quantity INTEGER,
  recommended_price NUMERIC(12,4), selected_price NUMERIC(12,4), outcome VARCHAR(30), notes TEXT,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- v0.4 governed cost-to-serve, contracts, quantity breaks, and decision audit
CREATE TABLE IF NOT EXISTS product_cost_profiles (
  product_id VARCHAR(40) PRIMARY KEY REFERENCES products(product_id), setup_cost NUMERIC(12,4) NOT NULL DEFAULT 0,
  engineering_cost NUMERIC(12,4) NOT NULL DEFAULT 0, setup_allocation_qty INTEGER NOT NULL DEFAULT 1,
  cost_to_serve_unit NUMERIC(12,4) NOT NULL DEFAULT 0, capacity_utilization_pct NUMERIC(8,4) NOT NULL DEFAULT 50,
  expedite_premium_pct NUMERIC(8,4) NOT NULL DEFAULT 0.03, guaranteed_inventory_premium_pct NUMERIC(8,4) NOT NULL DEFAULT 0.02,
  warranty_premium_pct NUMERIC(8,4) NOT NULL DEFAULT 0.02, regulatory_premium_pct NUMERIC(8,4) NOT NULL DEFAULT 0.015,
  sustainability_premium_pct NUMERIC(8,4) NOT NULL DEFAULT 0.01
);
CREATE TABLE IF NOT EXISTS price_agreements (
  agreement_id VARCHAR(40) PRIMARY KEY, customer_id VARCHAR(40) NOT NULL REFERENCES customers(customer_id),
  product_id VARCHAR(40) NOT NULL REFERENCES products(product_id), contract_price NUMERIC(12,4) NOT NULL,
  start_date DATE NOT NULL, end_date DATE NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'active', notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_price_agreement_pair_dates ON price_agreements(customer_id, product_id, start_date, end_date);
CREATE TABLE IF NOT EXISTS quantity_tiers (
  tier_id VARCHAR(40) PRIMARY KEY, product_id VARCHAR(40) NOT NULL REFERENCES products(product_id), customer_id VARCHAR(40),
  min_quantity INTEGER NOT NULL, max_quantity INTEGER, discount_pct NUMERIC(8,4) NOT NULL DEFAULT 0,
  start_date DATE, end_date DATE, status VARCHAR(20) NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_quantity_tier_lookup ON quantity_tiers(product_id, min_quantity, max_quantity, status);
CREATE TABLE IF NOT EXISTS quote_decision_audit (
  id BIGSERIAL PRIMARY KEY, customer_id VARCHAR(40), product_id VARCHAR(40), quantity INTEGER,
  recommended_price NUMERIC(12,4), unit_cost NUMERIC(12,4), minimum_price NUMERIC(12,4),
  target_margin_pct NUMERIC(8,4), agreement_id VARCHAR(40), approval_flags TEXT, created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
