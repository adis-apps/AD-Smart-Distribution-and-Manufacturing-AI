# Operations Agents — Design Notes (v0.7.0)

## 1. EDI Exception Resolution & Pre-Rejection Guard

**Goal:** catch common data-quality problems before a document is accepted for processing or transmitted to a trading partner.

### Demo checks
- Missing order/PO reference
- Missing ship-to identifier
- Partner SKU without a verified crosswalk
- UOM outside the configured demo set
- Non-positive quantity / invoice amount
- ASN and invoice follow-up warnings

### Connected workflow
1. Receive an EDI document into a durable queue (future connector).
2. Parse the envelope and transaction set with a standards-aware translator.
3. Validate partner profile, required segments, qualifiers, code lists, SKU crosswalk, UOM conversions, and business rules.
4. Correlate the transaction to its source order and related documents.
5. Classify the failure, show evidence, and suggest a repair or partner question.
6. Save an immutable draft for an authorized operator.
7. After approval, send the correction through an EDI gateway with idempotency and audit controls.
8. Correlate 997/999 functional acknowledgement and business response such as 855; update the exception state.

**Important:** a 997 is a functional acknowledgement of syntax/structure, not an order acceptance. A partner's 855 is the business acknowledgement; 856 is the advance ship notice; 810 is the invoice. Production correlation must use envelope/control numbers, partner IDs, transaction set IDs, and business document references.

## 2. Demand-Supply Reconciliation

The demo compares forecast + open customer orders with on-hand inventory + open purchase orders, then checks a safety-stock threshold. It exposes supplier ETA and line capacity for review but does not yet solve production scheduling or MRP.

Recommended next version should add time-phased buckets (day/week), inventory reservations, PO due dates and partial receipts, BOM/component demand, yield/scrap, MOQ/multiple, lead-time variability, warehouse transfer lead times, and customer/order priority. Only then should the system calculate a replenishment quantity or reschedule a production line.

## 3. Shared action workflow

Agent recommendations are drafts with agent, entity, action type, proposal, status, and creation time. Future states should include `PendingApproval`, `Approved`, `Rejected`, `Executing`, `Succeeded`, `Failed`, and `Reconciled`. Require user identity, authorization policy, approval limits, duplicate-action protection, source-system correlation IDs, and a full audit log before execution is enabled.

## 4. Roadmap

1. Replace sample records with partner-specific test files and canonical source-system exports.
2. Implement raw X12 parsing / translator integration and a partner implementation-guide rules registry.
3. Add order execution entity model and correlation across 850 → 855 → 856 → 810 → 997/999.
4. Add time-phased demand-supply planning and supplier performance history.
5. Integrate read-only ERP/CRM/WMS and an EDI test gateway.
6. Add approval queue and controlled write-back only after security and idempotency reviews.
