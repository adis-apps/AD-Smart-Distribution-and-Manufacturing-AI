# Pricing & Margin Copilot v0.5.1 (Packaging & Distribution POC)

## Baseline v0.5 changes
- **Synthetic data rebuilt** (`app/seed_data.py`): list prices above each margin floor, unit of measure and realistic order sizes per product, ~20% of quotes with no recorded competitor price, customer-status credit hold aligned between training and inference, fixed anchor date (`SYNTHETIC_ANCHOR_DATE`) and `SYNTHETIC_SEED` so runs are reproducible, customer `annual_revenue` derived from won quotes. Model metrics are diagnostics on synthetic data only. In the v0.5 baseline, five-fold CV ROC-AUC was about 0.729 and the holdout ROC-AUC about 0.653; these are not evidence of real-world performance.
- **Win model is now logistic regression** with 5-fold CV, base-rate baselines and a price-sign check that refuses to save a model where higher prices raise win odds. Features live in `app/features.py`, shared by training and the API.
- **Fixed: missing competitor price no longer pushes the recommendation to the top of the range.** Price is also measured against list price (new `products.list_price` column, added automatically to existing databases).
- Model errors are logged and the response reports `win_probability_source` (`model` or `heuristic`); the API reloads the model automatically after retraining.
- New tests in `tests/test_win_model.py`.

After upgrading, re-run `python -m app.seed_data` and `python -m app.train_model`.


A local, synthetic-data MVP for price recommendations, margin guardrails, a logistic-regression win-probability model, FastAPI APIs, optional Gemini explanations, lightweight retrieval of pricing policy, and a Streamlit UI.

> **POC only:** data is synthetic. The ML model is trained on simulated quote outcomes and is not evidence of real-world predictive accuracy. Treat outputs as decision support, not automatic price approval. Validate policies, cost definitions, model calibration, and customer/contract constraints before a pilot.

## v0.4 features
- Allocates setup and engineering costs across a configured production quantity and adds per-unit cost-to-serve to landed cost.
- Enforces a hard minimum-margin price floor even when an active agreement or quantity tier suggests a lower price.
- Resolves active effective-dated customer/product price agreements and quantity tiers.
- Adds explicit value-added price options (expedited delivery, guaranteed inventory, warranty, regulatory documentation, sustainability certification); options are never assumed unless selected.
- High capacity utilization creates a review flag; no automatic surcharge or low-capacity discount is assumed without validated commercial rules.
- Writes recommendation decisions and approval flags to `quote_decision_audit`.
- Streamlit displays loaded-cost components, contract/tier context, capacity and selected service options.

## Features
- Sample products, customers, quotes, inventory, competitor observations, and pricing policy.
- Deterministic landed-cost and minimum-price calculations. The margin floor is a hard guardrail.
- Candidate-price search balancing estimated win probability and contribution profit.
- Logistic-regression win model (monotonic in price, calibrated); a monotonic LightGBM challenger is cross-validated and reported but not deployed.
- FastAPI `/health`, `/reference-data`, `/recommend`, `/explain` and `/feedback` endpoints.
- Optional Gemini explanation via `GEMINI_API_KEY`; the app works without an API key using a grounded local explanation.
- RAG-lite retrieval from `docs/pricing_policy.md`; retrieved policy is context, never allowed to override numeric guardrails.
- Streamlit UI for quote inputs, recommendation, scenario comparison, and saving feedback.
- PostgreSQL schema + Docker Compose; SQLite is the default local mode so it can run without Docker.

## Quick start (Python 3.11 recommended)

### 1. Create environment and install
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
```
Edit `.env` only if needed. Default database is SQLite at `./data/copilot.db`. For PostgreSQL, set `DATABASE_URL=postgresql+psycopg://copilot:copilot@localhost:5432/copilot` and start Docker Compose.

### 3. Generate synthetic data and train the model
```bash
python -m app.seed_data
python -m app.train_model
```
Seed data is intentionally reproducible. It creates CSV files in `data/` and loads the operational tables into the configured database. The synthetic outcome generator now deliberately includes a price-versus-competitor signal, quantity effect, customer propensity, segment effect, and credit-hold penalty. These are simulation assumptions, not claims about real customer behavior.

### 4. Run the API
```bash
uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

### 5. Run Streamlit (new terminal)
```bash
streamlit run app/streamlit_app.py
```
The UI calls `http://localhost:8000` by default. Change `API_BASE_URL` in `.env` if needed.

### Optional Gemini explanations
Set `GEMINI_API_KEY` in `.env`. The integration uses `google-genai`; choose `GEMINI_MODEL` appropriate to your account. If Gemini fails or is not configured, a local explanation is returned. Do not send confidential customer or pricing data to an external model without your organization's approval.

## API example
```bash
curl -X POST http://localhost:8000/recommend \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"CUST-001","product_id":"BAG-001","quantity":100000,"current_price":26.0,"requested_discount_pct":8,"competitor_price":24.5,"expedited_delivery":true}'
```

## Price logic
- `landed_cost = material + labor + overhead + freight + tariff`
- `fully_loaded_unit_cost = landed_cost + setup_cost/allocation_qty + engineering_cost/allocation_qty + cost_to_serve_unit`
- `minimum_price = fully_loaded_unit_cost / (1 - minimum_gross_margin_pct)`
- `gross_margin_pct = (price - fully_loaded_unit_cost) / price`
- Active price agreements and effective-dated quantity tiers influence the target anchor; neither can override the hard minimum-price floor. A contract/floor conflict is flagged for human resolution.
- Capacity and value-added premiums are transparent heuristics and must be configured/validated by pricing and operations teams before customer use.
- Candidate prices are never below the minimum price (rounding tolerance included).
- The pricing objective is selectable: win-focused, balanced, or margin-focused. All modes preserve the hard gross-margin floor. Win-focused uses a 0.5% undercut of a supplied competitor price when feasible; active agreements remain binding when above the floor.
- Credit hold and contract/floor conflicts are surfaced as approval flags; the demo does not autonomously approve or transmit a quote. The demo does not autonomously approve or transmit a quote.

## Project layout
```
app/
  config.py db.py schemas.py seed_data.py pricing_engine.py ml_model.py train_model.py rag_gemini.py main.py streamlit_app.py
  repository.py
data/                 generated synthetic CSVs, model artifact and metrics
 docs/pricing_policy.md
 sql/schema.sql        PostgreSQL schema including v0.4 tables
 tests/                pricing, quote-context, and synthetic-signal tests
 Dockerfile docker-compose.yml requirements.txt .env.example
```

## Production hardening before customer pilot
1. Replace synthetic data with approved, reconciled ERP/CRM/quote data; define cost accounting and margin denominator with finance.
2. Add authentication/SSO, RBAC, tenant isolation, secrets management, audit retention, rate limits, and observability.
3. Validate pricing policy by product/customer/contract, freight allocations, rebates, commissions, taxes, and currency.
4. Train only on sufficient real quote history; use time-based validation, calibration, drift monitoring, and human review.
5. Keep competitor prices sourced, timestamped, licensed, and compliant with competition law. Never use competitors' non-public or coordinated pricing.
6. Add idempotent integration and approval workflow before writing any recommendation to Salesforce or ERP.

## UI data integrity fix (preserved from v0.2 enterprise-readiness baseline)

The previous UI used fixed defaults (`$26.00` current price and `$24.50` competitor price) for every customer/product combination. This is corrected:

- `GET /quote-context?customer_id=...&product_id=...` returns the latest historical quote for that exact customer/product pair and the latest non-null competitor observation for that product, but only when no older than 90 days.
- Streamlit reloads those defaults when either customer or product changes, shows the source/date, and does not show an old recommendation under a new selection.
- Current price and competitor price remain editable overrides; users should verify the source before recommending a price.

**Important source definition:** the demo's `current_price` is the latest quote-history price for the selected customer/product pair, not a guaranteed active ERP contract price. The demo's competitor benchmark is the latest product-level competitor observation in synthetic quote history, not a validated, named-competitor price feed. In a real customer deployment, replace these lookup rules with effective-dated ERP/customer price agreements and governed competitor observations (source, observed date, geography, pack/unit, freight terms, and confidence).

## v0.4 data tables
- `product_cost_profiles`: setup/engineering costs, allocation quantity, cost-to-serve, capacity and service premium assumptions.
- `price_agreements`: customer/product contract price with status and effective dates.
- `quantity_tiers`: product-wide or customer-specific volume tiers with effective dates.
- `quote_decision_audit`: recommended price, fully loaded cost, floor, target margin, agreement ID, approval flags and timestamp.

Seeded agreements, cost profiles, capacity and tiers are illustrative synthetic values. Replace them with finance-approved/customer-authorized source data before any commercial recommendation. The audit table is an operational decision log, not yet a tamper-proof immutable audit service.

## Enterprise readiness — what is and is not included

This is an enterprise-oriented development baseline, not yet a production-certified service. Before live customer quotes, implement and validate:

1. **Identity and tenant isolation:** SSO/OIDC, role-based access, tenant-scoped data access, secret management, and least privilege.
2. **Pricing governance:** versioned policies, approval matrix, effective dates, price floors, override reasons, and auditable approvals. Do not let the LLM set prices or bypass deterministic guardrails.
3. **Authoritative integrations:** ERP price agreements/costs, CRM account/opportunity/quote, inventory/availability, and a controlled competitor data source. Track source system, source timestamp, currency, unit of measure, and freshness.
4. **Data correctness:** unique keys, foreign keys, currency/unit normalization, effective-dated costs, idempotent ingestion, reconciliation reports, and data-quality alerts.
5. **Model governance:** replace synthetic training data, evaluate on time-based holdouts, calibrate win probabilities, monitor drift and outcomes, document feature lineage, and provide a rules-only fallback.
6. **Operational controls:** structured logs, request IDs, metrics/traces, alerting, health/readiness probes, retries/timeouts, backups/restore tests, migration tooling, and disaster-recovery objectives.
7. **Security:** TLS, encryption at rest, network controls, dependency/image scanning, vulnerability management, PII minimization, audit retention, and penetration testing.
8. **Commercial validation:** finance-approved margin definitions (gross vs contribution), representative historical quote outcomes, price override analysis, and a controlled pilot with sales/pricing approval before external quote release.

### Suggested production architecture

Salesforce/CRM + ERP + inventory + approved competitor feed → ingestion/validation and canonical product/customer/UOM mapping → PostgreSQL operational store and immutable decision audit → deterministic pricing/approval service → calibrated win-probability model → optional Gemini explanation grounded only in approved policy and recommendation fields → authenticated API/UI. Keep the pricing engine and approval rules independent from GenAI.

### Validation

Run from this directory:

```bash
python -m compileall -q app
python -m pytest -q
```

The LightGBM model is trained on synthetic data and its win probability is not suitable for commercial forecasting until retrained and validated on the customer's own quote history. `data/model_metrics.json` records the reproducible holdout metrics. The synthetic data is intentionally learnable, but model performance is still modest and should not be presented as a commercial forecast. For real data, use a time-based holdout and compare against simple baselines.


## v0.5.1 corrections

- Explicit strategies: `win_focused` (default), `balanced`, and `margin_focused`. Win-focused recommends a 0.5% undercut of a supplied competitor when that price remains above the hard margin floor; if the competitor is below the floor, the floor wins and an approval flag is raised.
- Active price agreements are treated as binding when their contract price clears the floor. An agreement below the floor is surfaced as a contract/cost conflict and is not silently quoted below the floor.
- Capacity is a review signal, not an invented surcharge. Selected value-add options are shown as proposed premiums and require operational/customer validation.
- Seed/reset deletes dependent records before parent records for PostgreSQL foreign-key compatibility. Synthetic training credit-hold features now use the same customer-status semantics as inference.
- Competitor observations older than 90 days (or with invalid/future dates) are not prefilled into the UI. A manually entered price still requires the user to validate product/UOM, geography, freight terms, and service comparability.
- Synthetic model metrics are diagnostic only; train and calibrate on representative real quote outcomes and use time-based validation before production decisions.

## v0.7.0 — Operations Agents & Pre-Rejection Guard

This release expands the existing Pricing & Margin Copilot POC with two operations workspaces focused on manufacturing/distribution exceptions:

- **EDI Exception Resolution & Pre-Rejection Guard**: synthetic EDI 850/855/856/810/997 examples; validates required order reference, ship-to, partner SKU mapping, UOM, and quantity/amount basics; classifies findings; suggests a resolution; and can save a human-review draft.
- **Demand-Supply Reconciliation**: compares seeded forecast quantity, open customer orders, on-hand inventory, open purchase orders, safety stock, supplier ETA, and line capacity; flags shortage risk or potential excess and drafts planner actions for approval.
- **Human-in-the-loop action log**: draft actions are stored with `Draft` status. No EDI file is changed, no email is sent, and no ERP/PO/order is updated.
- **Pricing & Margin Copilot** remains available as the original pricing workspace.

### Run locally

```bash
pip install -r requirements.txt
python -m app.seed_data
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
streamlit run app/streamlit_app.py
```

Choose **EDI Exception & Order Guard** or **Demand-Supply Reconciliation** in the sidebar. API docs: `http://localhost:8000/docs`.

### Added API routes

- `GET /ops/edi/exceptions`
- `POST /ops/edi/validate/{transaction_id}`
- `GET /ops/supply/reconcile`
- `POST /ops/actions/draft`

### Workflow design

**EDI:** receive → pre-validate → diagnose likely issue → draft correction/partner query → human approval → future EDI gateway transmission → reconcile 997/ERP posting result.

**Supply:** forecast + open customer orders + on-hand inventory + open POs + safety stock → reconcile shortage/excess → draft expedite/transfer/PO adjustment → planner approval → future ERP update.

The final two system-write steps are intentionally not implemented until integrations, access controls, and partner-specific rules are validated.

### POC limitations and safeguards

- All operational EDI/supply records are synthetic and generated with deterministic seed logic.
- Validation rules are illustrative. Actual EDI compliance must use each trading partner's implementation guide, X12 version, code lists, SKU/UOM crosswalk, and envelope/control-number requirements.
- A 997 functional acknowledgement is not the same as a business-level order acceptance; 855 communicates purchase-order acknowledgement, while 856 is an ASN and 810 is an invoice. Production workflows must correlate each document to its original transaction and partner-specific rules.
- The demo checks visible field-level issues, but it does not parse raw X12 files or implement a complete X12 parser/translator.
- Supply calculations are a transparent planning heuristic, not a full MRP, ATP, finite-capacity scheduling, or optimization solver.
- Supplier news/weather monitoring, machine/line telemetry, WMS 940/945 processing, carrier claims, outbound email, and automatic correction are future integrations, not active capabilities in this build.
- Draft actions require human approval. Do not connect to production ERP/EDI endpoints without authentication, authorization, audit, idempotency, replay protection, partner testing, and a rollback plan.

### Tests

The local suite covers the existing pricing engine and new EDI pre-check, supply reconciliation, and draft-only action behavior. Synthetic POC validation does not imply production readiness.


## v0.7.1 troubleshooting: EDI and supply pages return 404

Both routes are registered in `app/main.py`:
- `GET /ops/edi/exceptions`
- `GET /ops/supply/reconcile`

A 404 means the server that Streamlit reached does not have those routes loaded (commonly an older Uvicorn process or a server started from a different project directory). Running the seed command alone cannot add routes to an already-running older process.

1. Stop the API process with `Ctrl+C`.
2. Extract this ZIP into a new folder and open the terminal in that exact project root (the folder containing `app/` and `requirements.txt`).
3. Run `python -m app.seed_data`.
4. Start the API again: `uvicorn app.main:app --reload --port 8000`.
5. Open `http://localhost:8000/openapi.json` and confirm both `/ops/edi/exceptions` and `/ops/supply/reconcile` are listed.
6. Restart Streamlit in a second terminal from the same project root: `streamlit run app/streamlit_app.py`.

If port 8000 is already occupied, stop the old process or start the API on another port and set `API_BASE_URL` in `.env` to that exact URL. A database/seed issue would normally cause a 500 or an empty result, not a 404 for a registered route.
