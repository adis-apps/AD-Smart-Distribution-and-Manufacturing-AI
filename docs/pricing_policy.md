# Demo Pricing Policy

## Minimum gross margin
Every recommended selling price must meet or exceed the product's configured minimum gross margin. The deterministic pricing engine calculates minimum price as total landed unit cost divided by one minus the margin floor. This rule is authoritative; an LLM must never override it.

## Approval workflow
Quotes for customers on credit hold require Finance review before release. Any quote that breaches a contract, customer-specific price agreement, or product margin floor must be reviewed by the authorized pricing manager. Large deviations from customer history should be reviewed rather than silently applied.

## Customer and product context
Compare like-for-like pack size, grade, specification, delivery terms, quantity breaks, rebates, and service levels. Competitor observations should be dated, sourced, and legally obtained. Do not treat an unverified competitor quote as fact.

## Inventory and supply constraints
If requested quantity exceeds available inventory, flag the order for replenishment, substitution, or split-shipment review. Do not infer a guaranteed delivery date from inventory alone.

## Human accountability
The Copilot provides decision support only. Sales, Pricing, Finance, and Operations retain approval responsibilities. Do not auto-send a quote or write a price to ERP/CRM without an explicit approval workflow.

## Model transparency
Win probability is an estimate. The starter dataset is synthetic and its model is for software demonstration only. Before production, use real historical quotes with outcomes, avoid target leakage, split by time, evaluate calibration and segment performance, and monitor drift.


## v0.4 cost-to-serve and setup allocation
Fully loaded unit cost includes landed unit cost plus setup and engineering costs divided by the configured allocation quantity, plus per-unit cost-to-serve. Finance must define the allocation denominator and whether each cost belongs in gross margin or contribution margin. Do not treat illustrative seed values as approved accounting data.

## Effective-dated price agreements and quantity tiers
Only active agreements/tiers whose effective dates include the quote date are considered. Customer-specific tiers take precedence over product-wide tiers. The configured minimum-price floor always wins in the calculation; if an agreement price is below that floor, the system flags a contract/cost conflict rather than silently recommending a below-floor price. Legal/contract owners must resolve such conflicts.

## Capacity and value-added services
Capacity utilization is a simple configurable signal, not a demand-forecasting model. High utilization triggers review; low utilization only supports a limited tactical adjustment when stock is sufficient. Service premiums apply only when the salesperson explicitly selects the relevant service and the business can actually deliver it. Premium percentages are demonstration defaults and require commercial validation.

## Decision audit
The API records recommendation inputs' key outputs and approval flags in `quote_decision_audit`. Before production, add actor identity, tenant ID, source-data timestamps, policy/model versions, request correlation ID, override reason, approval identity, and append-only/retention controls.
