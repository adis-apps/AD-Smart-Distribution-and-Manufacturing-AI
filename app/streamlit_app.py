import os
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
API = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
st.set_page_config(page_title="AD Smart Distribution AI", page_icon="📦", layout="wide")
st.title("📦 AD Smart Distribution AI")
st.caption("Packaging & distribution operations intelligence | Synthetic POC data; no live ERP/EDI connections")

@st.cache_data(ttl=30)
def get_reference_data():
    response = requests.get(f"{API}/reference-data", timeout=8)
    response.raise_for_status()
    return response.json()

def fetch_quote_context(customer_id, product_id):
    response = requests.get(f"{API}/quote-context", params={"customer_id": customer_id, "product_id": product_id}, timeout=8)
    response.raise_for_status()
    return response.json()

try:
    refs = get_reference_data()
except Exception as exc:
    st.error(f"API not reachable: {exc}. Start it with `uvicorn app.main:app --reload --port 8000`.")
    st.stop()
products = refs.get("products", [])
customers = refs.get("customers", [])
if not products or not customers:
    st.warning("No reference data found. Run `python -m app.seed_data` first.")
    st.stop()

with st.sidebar:
    workspace = st.radio("Copilot workspace", ["Pricing & Margin", "EDI Exception & Order Guard", "Demand-Supply Reconciliation"])

if workspace == "EDI Exception & Order Guard":
    st.header("🧾 EDI Exception Resolution & Pre-Rejection Guard")
    st.write("Pre-check inbound orders and outbound documents, identify likely rejection causes, and prepare a controlled fix for review before transmission.")
    try:
        payload = requests.get(f"{API}/ops/edi/exceptions", timeout=12); payload.raise_for_status(); docs = payload.json().get("transactions", [])
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            st.error("The API returned 404 for /ops/edi/exceptions. This endpoint exists in AD Smart Distribution AI v0.7.1; a 404 usually means an older API process or a different project folder is running. Stop the old API (Ctrl+C), open a terminal in the v0.7.1 project root, run `python -m app.seed_data`, then restart with `uvicorn app.main:app --reload --port 8000`. Verify `http://localhost:8000/openapi.json` contains `/ops/edi/exceptions`.")
        else:
            st.error(f"Could not load EDI demo transactions: {exc}. Check that the API is running and run `python -m app.seed_data` from the project root.")
        st.stop()
    except Exception as exc:
        st.error(f"Could not load EDI demo transactions: {exc}. Check that the API is running and run `python -m app.seed_data` from the project root."); st.stop()
    st.info("Synthetic EDI 850/855/856/810/997 records. No real partner files are transmitted or modified.")
    f1, f2 = st.columns(2)
    with f1: type_filter = st.selectbox("Transaction type", ["All"] + sorted({str(x["transaction_type"]) for x in docs}))
    with f2: status_filter = st.selectbox("Pre-check", ["All", "Needs Fix", "Passed"])
    filtered = [d for d in docs if (type_filter == "All" or d["transaction_type"] == type_filter) and (status_filter == "All" or (status_filter == "Needs Fix" and not d["precheck_valid"]) or (status_filter == "Passed" and d["precheck_valid"]))]
    cols = st.columns(4); cols[0].metric("Documents checked", len(docs)); cols[1].metric("Need correction/review", sum(not x["precheck_valid"] for x in docs)); cols[2].metric("High severity", sum(x["severity"] == "High" for x in docs)); cols[3].metric("Passed pre-check", sum(x["precheck_valid"] for x in docs))
    st.dataframe(pd.DataFrame([{k:d.get(k) for k in ["transaction_id","transaction_type","partner_id","order_ref","sku_partner","uom","quantity","status","severity","precheck_valid"]} for d in filtered]), hide_index=True, use_container_width=True)
    if filtered:
        choices = {f"{d['transaction_id']} · {d['transaction_type']} · {d['severity']}": d for d in filtered}
        selected = st.selectbox("Inspect document", list(choices), key="edi_selected")
        doc = choices[selected]
        left, right = st.columns(2)
        with left:
            st.subheader("Validation findings")
            if doc["errors"]:
                for e in doc["errors"]: st.error(e)
            if doc["warnings"]:
                for w in doc["warnings"]: st.warning(w)
            if not doc["errors"] and not doc["warnings"]: st.success("No blocking rule found in this synthetic pre-check.")
        with right:
            st.subheader("Suggested resolution")
            st.write(doc["recommended_action"])
            st.caption("AI/agent proposes; a human validates the partner guide and approves any correction.")
            if st.button("Create resolution draft", type="primary", key=f"draft_{doc['transaction_id']}"):
                try:
                    res = requests.post(f"{API}/ops/actions/draft", json={"agent_name":"EDI Exception Resolution Agent","entity_id":doc["transaction_id"],"action_type":"EDI correction / partner follow-up","proposal":doc["recommended_action"]}, timeout=10)
                    res.raise_for_status(); st.success(res.json().get("message", "Draft saved for review."))
                except Exception as exc: st.error(f"Could not save draft: {exc}")
    st.subheader("Connected workflow")
    st.markdown("**Receive document → validate required fields / SKU / UOM / quantities → classify error → draft correction or partner query → human approval → (future) send through EDI gateway → reconcile 997 / ERP posting status.**")
    st.stop()

if workspace == "Demand-Supply Reconciliation":
    st.header("📦 Demand-Supply Reconciliation Agent")
    st.write("Reconciles synthetic demand, open customer orders, on-hand inventory, open purchase orders, safety stock, supplier ETA, and line capacity.")
    try:
        payload = requests.get(f"{API}/ops/supply/reconcile", timeout=12); payload.raise_for_status(); plans = payload.json().get("items", [])
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            st.error("The API returned 404 for /ops/supply/reconcile. This endpoint exists in AD Smart Distribution AI v0.7.1; a 404 usually means an older API process or a different project folder is running. Stop the old API (Ctrl+C), open a terminal in the v0.7.1 project root, run `python -m app.seed_data`, then restart with `uvicorn app.main:app --reload --port 8000`. Verify `http://localhost:8000/openapi.json` contains `/ops/supply/reconcile`.")
        else:
            st.error(f"Could not load supply plans: {exc}. Check that the API is running and run `python -m app.seed_data` from the project root.")
        st.stop()
    except Exception as exc:
        st.error(f"Could not load supply plans: {exc}. Check that the API is running and run `python -m app.seed_data` from the project root."); st.stop()
    st.info("Synthetic planning inputs only. Recommendations are not live ERP/MRP/ATP decisions.")
    f = st.selectbox("Supply status", ["All", "Shortage Risk", "Balanced", "Potential Excess"])
    shown = [x for x in plans if f == "All" or x["status"] == f]
    c = st.columns(3); c[0].metric("SKUs monitored", len(plans)); c[1].metric("Shortage risk", sum(x["status"] == "Shortage Risk" for x in plans)); c[2].metric("Potential excess", sum(x["status"] == "Potential Excess" for x in plans))
    cols = ["plan_id","product_id","product_name","forecast_qty","open_customer_orders","inventory_qty","open_purchase_orders","safety_stock","projected_net_qty","shortage_to_safety_stock","supplier_eta","line_capacity_qty","status"]
    st.dataframe(pd.DataFrame([{k:x.get(k) for k in cols} for x in shown]), hide_index=True, use_container_width=True)
    if shown:
        selected = st.selectbox("Inspect supply plan", [f"{x['plan_id']} · {x['product_name']} · {x['status']}" for x in shown])
        plan = shown[[f"{x['plan_id']} · {x['product_name']} · {x['status']}" for x in shown].index(selected)]
        st.subheader("Recommended planner actions")
        for action in plan["recommended_actions"]: st.write(f"- {action}")
        proposal = "; ".join(plan["recommended_actions"])
        if st.button("Draft planner action for approval", type="primary"):
            try:
                res = requests.post(f"{API}/ops/actions/draft", json={"agent_name":"Demand-Supply Reconciliation Agent","entity_id":plan["plan_id"],"action_type":"Supply plan adjustment","proposal":proposal}, timeout=10); res.raise_for_status(); st.success(res.json().get("message"))
            except Exception as exc: st.error(f"Could not save draft: {exc}")
    st.markdown("**Connected workflow:** CRM/e-commerce forecast + open orders + inventory + open POs → shortage/excess analysis → proposed expedite, transfer, or PO adjustment → planner approval → (future) ERP update.")
    st.stop()

c_map = {f"{x['customer_name']} ({x['customer_id']})": x for x in customers}
p_map = {f"{x['product_name']} ({x['product_id']})": x for x in products}
with st.sidebar:
    st.header("Quote inputs")
    c_label = st.selectbox("Customer", list(c_map), key="customer_selection")
    p_label = st.selectbox("Product", list(p_map), key="product_selection")
    customer = c_map[c_label]
    product = p_map[p_label]

# Refresh source values whenever either selected entity changes. Keying this by IDs
# prevents Streamlit's prior widget state from leaking into another customer/product.
pair_key = (customer["customer_id"], product["product_id"])
if st.session_state.get("_context_pair") != pair_key:
    try:
        ctx = fetch_quote_context(*pair_key)
    except Exception as exc:
        st.error(f"Could not load customer/product pricing context: {exc}")
        st.stop()
    st.session_state["_quote_context"] = ctx
    st.session_state["_context_pair"] = pair_key
    st.session_state["current_price_input"] = float(ctx["current_price"] or 1.0)
    st.session_state["competitor_price_input"] = float(ctx["competitor_price"] or 0.0)
ctx = st.session_state["_quote_context"]

with st.sidebar:
    uom = product.get("unit_of_measure") or "unit"
    quantity = st.number_input(f"Quantity ({uom})", min_value=1, value=500, step=50, key="quantity_input")
    st.caption(f"Current price source: {ctx['current_price_source']}" + (f" · {ctx['current_price_date']}" if ctx.get("current_price_date") else ""))
    current_price = st.number_input(f"Current / latest quoted price per {uom} ($)", min_value=0.0001, step=0.10, format="%.4f", key="current_price_input")
    requested_discount = st.slider("Customer requested discount (%)", 0.0, 25.0, 8.0, 0.5, key="requested_discount_input")
    pricing_strategy = st.selectbox("Pricing strategy", ["win_focused", "balanced", "margin_focused"], index=0, format_func=lambda x: {"win_focused":"Win-focused — competitive price, floor protected", "balanced":"Balanced — expected profit vs competitiveness", "margin_focused":"Margin-focused — prioritize contribution"}[x])
    st.caption(f"Competitor source: {ctx['competitor_price_source']}" + (f" · {ctx['competitor_price_date']}" if ctx.get("competitor_price_date") else ""))
    if ctx.get("competitor_price_stale"):
        st.warning("The latest stored competitor observation is older than 90 days or has an invalid/future date. It was not prefilled; verify a current, comparable price before entering one.")
    competitor = st.number_input("Competitor price ($, 0 = unknown)", min_value=0.0, step=0.10, format="%.4f", key="competitor_price_input")
    st.subheader("Value-added options")
    expedited_delivery = st.checkbox("Expedited delivery")
    guaranteed_inventory = st.checkbox("Guaranteed inventory allocation")
    extended_warranty = st.checkbox("Extended warranty")
    regulatory_documentation = st.checkbox("Regulatory documentation")
    sustainability_certified = st.checkbox("Sustainability-certified product")
    run = st.button("Recommend price", type="primary", use_container_width=True)

# Never display an old recommendation as if it belongs to the newly selected pair.
rec_key = (customer["customer_id"], product["product_id"])
if run:
    payload = {"customer_id": customer["customer_id"], "product_id": product["product_id"],
               "quantity": int(quantity), "current_price": float(current_price),
               "requested_discount_pct": float(requested_discount), "pricing_strategy": pricing_strategy,
               "competitor_price": float(competitor) if competitor > 0 else None,
               "expedited_delivery": expedited_delivery, "guaranteed_inventory": guaranteed_inventory,
               "extended_warranty": extended_warranty, "regulatory_documentation": regulatory_documentation,
               "sustainability_certified": sustainability_certified}
    try:
        response = requests.post(f"{API}/recommend", json=payload, timeout=30)
        response.raise_for_status()
        st.session_state["recommendation"] = response.json()
        st.session_state["recommendation_pair"] = rec_key
        st.session_state["request"] = payload
    except Exception as exc:
        st.error(f"Recommendation failed: {exc}")
        st.stop()

rec = st.session_state.get("recommendation")
if rec is None or st.session_state.get("recommendation_pair") != rec_key:
    st.info("Pricing context loaded for the selected customer and product. Review the source values, then click **Recommend price**.")
    st.write({"Customer": customer["customer_name"], "Product": product["product_name"],
              "Current price": ctx.get("current_price"), "Current-price date": ctx.get("current_price_date"),
              "Competitor price": ctx.get("competitor_price"), "Competitor-price date": ctx.get("competitor_price_date"),
              "Historical quotes for this customer/product": ctx.get("customer_product_quote_count")})
    st.stop()

left, mid, right = st.columns(3)
left.metric("Recommended price", f"${rec['recommended_price']:,.4f}", f"{rec['recommended_discount_pct']:.1f}% vs current")
mid.metric("Gross margin", f"{rec['gross_margin_pct']:.1f}%", f"Target {rec['target_margin_pct']:.1f}%")
right.metric("Estimated win probability", f"{rec['win_probability_pct']:.1f}%", help="Synthetic-data estimate only; not validated for commercial decisions.")
if rec.get("win_probability_source") == "heuristic":
    st.warning("Win probability is from the fallback heuristic, not the trained model. Run `python -m app.train_model`.")
if rec.get("competitor_price") is None:
    st.caption("No competitor price given: win probability is estimated against list price and is less certain.")
st.caption(f"Strategy: {rec.get('pricing_strategy', 'win_focused')} | Minimum price: ${rec['minimum_price']:.4f} | Target-margin price: ${rec['target_margin_price']:.4f} | Expected gross profit: ${rec['expected_gross_profit']:,.2f}")
st.caption(f"Capacity utilization: {rec.get('capacity_utilization_pct', 0):.1f}% | Automatic capacity surcharge: not assumed | Selected value-add premium proposal: {rec.get('value_addon_premium_pct', 0):.1f}%")
if rec.get("agreement"):
    st.info(f"Active agreement {rec['agreement']['agreement_id']} — contract price ${rec['agreement']['contract_price']:.4f}; review any deviation flags below.")
if rec.get("quantity_tier"):
    st.caption(f"Quantity tier {rec['quantity_tier']['tier_id']} applied: {rec['quantity_tier']['discount_pct']:.2f}% anchor discount.")
if rec.get("credit_hold"): st.error("CREDIT HOLD — Finance approval required before quote release.")
if rec.get("approval_flags"):
    st.subheader("Review flags")
    for flag in rec["approval_flags"]: st.warning(flag)
else: st.success("No demo-rule exception flagged. Follow your normal quote approval policy.")
col1, col2 = st.columns(2)
with col1:
    st.subheader("Cost breakdown per unit")
    st.dataframe(pd.DataFrame([{"Cost component": k.replace("_", " ").title(), "$/unit": v} for k, v in rec["cost_breakdown"].items()] + [{"Cost component": "Fully loaded unit cost", "$/unit": rec["unit_cost"]}]), hide_index=True, use_container_width=True)
    st.subheader("Context")
    st.write(f"Available inventory: **{rec['available_inventory']:,}** | Days on hand: **{rec['days_on_hand']}**")
    st.write(f"Customer/product historical average: **{('$'+format(rec['customer_historical_average_price'],'.4f')) if rec['customer_historical_average_price'] is not None else 'Not enough history'}**")
    st.write(f"Customer/product historical win rate: **{(str(rec['customer_historical_win_rate_pct'])+'%') if rec['customer_historical_win_rate_pct'] is not None else 'Not enough history'}**")
with col2:
    st.subheader("Price scenario comparison")
    sdf = pd.DataFrame(rec["scenarios"])
    st.dataframe(sdf.rename(columns={"scenario":"Scenario", "price":"Price ($)", "gross_margin_pct":"Margin (%)", "win_probability_pct":"Win probability (%)", "expected_gross_profit":"Expected gross profit ($)"}), hide_index=True, use_container_width=True)
    st.subheader("Requested discount check")
    st.write(f"Requested price: **${rec['requested_price']:.4f}** | Implied margin: **{rec['requested_price_margin_pct']:.1f}%**")
    if rec["requested_discount_breaches_floor"]: st.error("Requested discount breaches minimum-margin floor.")
    else: st.success("Requested price is at/above the configured minimum-price floor.")

if st.button("Generate explanation (RAG + optional Gemini)"):
    try:
        exr = requests.post(f"{API}/explain", json={"recommendation":rec, "query":"Explain recommended price, margin floor, customer history, inventory, and approval policy"}, timeout=45)
        exr.raise_for_status(); ex = exr.json()
        st.subheader(f"Copilot explanation — {ex.get('provider','unknown')}"); st.write(ex.get("explanation"))
        with st.expander("Retrieved policy context"): st.write("\n\n---\n\n".join(ex.get("retrieved_policy", [])) or "No policy chunks retrieved")
        if ex.get("warning"): st.caption(ex["warning"])
    except Exception as exc: st.error(f"Explanation request failed: {exc}")

st.divider(); st.subheader("Record sales feedback")
with st.form("feedback_form"):
    chosen = st.number_input("Actual selected price ($/unit)", min_value=.0001, value=float(rec["recommended_price"]), step=.10)
    outcome = st.selectbox("Quote outcome", ["pending", "won", "lost", "ignored"])
    notes = st.text_input("Notes (optional)")
    submitted = st.form_submit_button("Save feedback")
if submitted:
    try:
        data = {"customer_id":rec["customer_id"], "product_id":rec["product_id"], "quantity":rec["quantity"], "recommended_price":rec["recommended_price"], "selected_price":float(chosen), "outcome":outcome, "notes":notes}
        rr = requests.post(f"{API}/feedback", json=data, timeout=10); rr.raise_for_status(); st.success("Feedback saved. Model retraining is deliberately manual.")
    except Exception as exc: st.error(f"Could not save feedback: {exc}")
st.caption(rec.get("model_note", ""))
