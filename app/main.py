from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from app.db import engine, init_db
from app.schemas import RecommendRequest, FeedbackRequest
from app.repository import get_product,get_customer,get_inventory,get_history,reference_data,get_quote_context,get_cost_profile,get_active_agreement,get_quantity_tier
from app.pricing_engine import recommend
import json
from app.rag_gemini import explain_recommendation
from app.ops_agents import init_ops_tables, seed_ops_data, edi_exceptions, validate_transaction, supply_reconcile, draft_action

app=FastAPI(title="Pricing & Margin Copilot API",version="0.7.1",description="Integrated packaging operations and pricing POC")
@app.on_event("startup")
def startup():
    init_db()
    init_ops_tables()

@app.get("/health")
def health():
    try:
        with engine.connect() as c: c.execute(text("SELECT 1"))
        return {"status":"ok","database":"connected"}
    except Exception as e: return {"status":"degraded","database":"unavailable","detail":type(e).__name__}

@app.get("/reference-data")
def refs(): return reference_data()

@app.get("/quote-context")
def quote_context(customer_id: str, product_id: str):
    if not get_customer(customer_id): raise HTTPException(404, f"Unknown customer_id: {customer_id}")
    if not get_product(product_id): raise HTTPException(404, f"Unknown product_id: {product_id}")
    return get_quote_context(customer_id, product_id)

@app.post("/recommend")
def get_recommendation(req: RecommendRequest):
    p=get_product(req.product_id); c=get_customer(req.customer_id); inv=get_inventory(req.product_id)
    if not p: raise HTTPException(404,f"Unknown product_id: {req.product_id}. Run python -m app.seed_data first.")
    if not c: raise HTTPException(404,f"Unknown customer_id: {req.customer_id}. Run python -m app.seed_data first.")
    history=get_history(req.customer_id,req.product_id)
    profile=get_cost_profile(req.product_id)
    agreement=get_active_agreement(req.customer_id,req.product_id)
    tier=get_quantity_tier(req.customer_id,req.product_id,req.quantity)
    result=recommend(p,c,inv,history,req.model_dump(),profile,agreement,tier)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO quote_decision_audit (customer_id,product_id,quantity,recommended_price,unit_cost,minimum_price,target_margin_pct,agreement_id,approval_flags) VALUES (:c,:p,:q,:r,:u,:m,:t,:a,:f)"), {"c":req.customer_id,"p":req.product_id,"q":req.quantity,"r":result["recommended_price"],"u":result["unit_cost"],"m":result["minimum_price"],"t":result["target_margin_pct"],"a":(result.get("agreement") or {}).get("agreement_id"),"f":json.dumps(result["approval_flags"])})
    return result

@app.post("/explain")
def explain(payload: dict):
    rec=payload.get("recommendation",payload)
    if "recommended_price" not in rec: raise HTTPException(400,"Pass a recommendation object or {recommendation: ...}")
    return explain_recommendation(rec,payload.get("query","Explain the recommended price"))

@app.post("/feedback")
def feedback(req: FeedbackRequest):
    with engine.begin() as conn:
        if engine.dialect.name=="sqlite":
            conn.execute(text("INSERT INTO recommendation_feedback (customer_id,product_id,quantity,recommended_price,selected_price,outcome,notes) VALUES (:c,:p,:q,:r,:s,:o,:n)"),{"c":req.customer_id,"p":req.product_id,"q":req.quantity,"r":req.recommended_price,"s":req.selected_price,"o":req.outcome,"n":req.notes})
        else:
            conn.execute(text("INSERT INTO recommendation_feedback (customer_id,product_id,quantity,recommended_price,selected_price,outcome,notes) VALUES (:c,:p,:q,:r,:s,:o,:n)"),{"c":req.customer_id,"p":req.product_id,"q":req.quantity,"r":req.recommended_price,"s":req.selected_price,"o":req.outcome,"n":req.notes})
    return {"saved":True,"message":"Feedback recorded; it does not retrain the model automatically."}


@app.get("/ops/edi/exceptions")
def get_edi_exceptions():
    return {"transactions": edi_exceptions(), "count": 30, "data_notice": "Synthetic EDI documents; no trading-partner connection."}

@app.post("/ops/edi/validate/{transaction_id}")
def prevalidate_edi(transaction_id: str):
    result = validate_transaction(transaction_id)
    if result is None: raise HTTPException(404, f"Unknown transaction_id: {transaction_id}")
    return result

@app.get("/ops/supply/reconcile")
def get_supply_reconciliation():
    rows = supply_reconcile()
    return {"items": rows, "count": len(rows), "data_notice": "Synthetic planning inputs; not a live MRP/ATP calculation."}

@app.post("/ops/actions/draft")
def create_draft_action(payload: dict):
    required = ["agent_name", "entity_id", "action_type", "proposal"]
    missing = [k for k in required if not payload.get(k)]
    if missing: raise HTTPException(400, f"Missing required fields: {', '.join(missing)}")
    return draft_action(payload["agent_name"], payload["entity_id"], payload["action_type"], payload["proposal"])
