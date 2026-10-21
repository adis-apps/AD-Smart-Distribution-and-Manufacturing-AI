from __future__ import annotations
from typing import Any
from datetime import date
import math
from app.ml_model import win_probability


def fnum(value, default=0.0):
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)): return default
        return float(value)
    except (TypeError, ValueError): return default


def _active(row: dict | None, today: str) -> bool:
    if not row or str(row.get("status", "active")).lower() != "active": return False
    start, end = row.get("start_date"), row.get("end_date")
    return (not start or str(start)[:10] <= today) and (not end or str(end)[:10] >= today)


def recommend(product: dict, customer: dict, inventory: dict, history, req: dict,
              cost_profile: dict | None = None, agreement: dict | None = None,
              quantity_tier: dict | None = None) -> dict[str, Any]:
    """Recommend a price with an explicit strategy and non-negotiable margin floor.

    win_focused: undercut a comparable competitor by 0.5% when feasible; never breach floor.
    balanced: maximize expected gross profit with a meaningful penalty for being uncompetitive.
    margin_focused: maximize expected gross profit with a margin-rate preference.
    Active agreements are binding price constraints unless below the floor, in which case
    the floor is shown with an approval/conflict flag rather than silently honoring the SPA.
    """
    profile = cost_profile or {}
    material=fnum(product.get("material_cost")); labor=fnum(product.get("labor_cost")); overhead=fnum(product.get("overhead_cost")); freight=fnum(product.get("freight_cost")); tariff=fnum(product.get("tariff_cost"))
    setup=fnum(profile.get("setup_cost")); engineering=fnum(profile.get("engineering_cost")); allocation_qty=max(1,int(fnum(profile.get("setup_allocation_qty"),1)))
    setup_alloc=setup/allocation_qty; engineering_alloc=engineering/allocation_qty; service=fnum(profile.get("cost_to_serve_unit"))
    landed_cost=material+labor+overhead+freight+tariff
    unit_cost=landed_cost+setup_alloc+engineering_alloc+service
    margin_floor=max(0.0,min(.80,fnum(product.get("min_margin_pct"),.15)))
    target_margin=max(margin_floor,min(.80,fnum(customer.get("target_margin_pct"),.18)))
    min_price=unit_cost/(1-margin_floor) if margin_floor < 1 else unit_cost*100
    base_target_price=unit_cost/(1-target_margin) if target_margin < 1 else min_price
    qty=int(req["quantity"]); current=float(req["current_price"]); competitor=req.get("competitor_price")
    competitor=float(competitor) if competitor is not None and fnum(competitor)>0 else None
    strategy=str(req.get("pricing_strategy", "win_focused")).lower()
    if strategy not in {"win_focused", "balanced", "margin_focused"}: strategy="win_focused"
    list_price=fnum(product.get("list_price")) or current
    credit_hold=bool(customer.get("credit_hold",False)); available=int(fnum((inventory or {}).get("available_qty"))); days_on_hand=int(fnum((inventory or {}).get("days_on_hand")))
    today=date.today().isoformat()
    agreement_active=_active(agreement,today)
    tier_active=_active(quantity_tier,today) and qty >= int(fnum(quantity_tier.get("min_quantity"))) and (quantity_tier.get("max_quantity") is None or qty <= int(fnum(quantity_tier.get("max_quantity"))))
    tier_discount=min(.50,max(0,fnum(quantity_tier.get("discount_pct"))/100)) if tier_active else 0.0
    target_price=max(min_price,base_target_price*(1-tier_discount))
    contract_price=fnum(agreement.get("contract_price")) if agreement_active else None
    # A below-floor SPA is a conflict: do not present it as a valid quote price.
    agreement_below_floor=contract_price is not None and contract_price < min_price-1e-6
    if contract_price is not None and not agreement_below_floor:
        target_price=contract_price
    capacity=fnum(profile.get("capacity_utilization_pct"),50)
    # Capacity is a review signal unless the source system supplies a validated surcharge/cost.
    capacity_adjustment=0.0
    premium_options={"expedited_delivery":fnum(profile.get("expedite_premium_pct"),.03),"guaranteed_inventory":fnum(profile.get("guaranteed_inventory_premium_pct"),.02),"extended_warranty":fnum(profile.get("warranty_premium_pct"),.02),"regulatory_documentation":fnum(profile.get("regulatory_premium_pct"),.015),"sustainability_certified":fnum(profile.get("sustainability_premium_pct"),.01)}
    selected_premiums=[k for k in premium_options if bool(req.get(k,False))]
    premium_pct=sum(premium_options[k] for k in selected_premiums)
    target_price=max(min_price,target_price*(1+premium_pct))
    upper=max(current*1.12,target_price*1.18,(competitor*1.12 if competitor else 0),min_price*1.08)
    candidates=sorted({round(max(min_price,min_price+i*(upper-min_price)/160),4) for i in range(161)} | {round(max(min_price,target_price),4),round(max(min_price,current),4)})
    hist_avg=float(history["quoted_price"].mean()) if history is not None and not history.empty else None
    hist_win=float(history["won"].mean()) if history is not None and not history.empty else None
    def win_inputs(price):
        return {"price":price,"list_price":list_price,"competitor_price":competitor,"quantity":qty,"segment":customer.get("segment","Unknown"),"product_id":product.get("product_id","Unknown"),"customer_id":customer.get("customer_id","Unknown"),"credit_hold":credit_hold}
    scored=[]
    for price in candidates:
        margin=(price-unit_cost)/price if price else 0
        pwin,pwin_source=win_probability(win_inputs(price))
        contribution=max(0,price-unit_cost)*qty*pwin
        if strategy == "balanced":
            # Penalize competitor premiums materially, but retain the expected-profit trade-off.
            competitive_penalty=(max(0,(price-competitor)/competitor)*unit_cost*qty*0.35) if competitor else 0
            score=contribution-competitive_penalty
        elif strategy == "margin_focused":
            score=contribution + max(0,margin-target_margin)*unit_cost*qty*0.20
        else:
            score=contribution
        scored.append((score,price,pwin,margin,contribution,pwin_source))
    if contract_price is not None and not agreement_below_floor:
        # Binding SPA: exact contract price, not a soft penalty/anchor.
        chosen=contract_price
        pwin,pwin_source=win_probability(win_inputs(chosen)); margin=(chosen-unit_cost)/chosen
        expected_profit=max(0,chosen-unit_cost)*qty*pwin
    elif strategy == "win_focused" and competitor is not None:
        # Prefer a modest 0.5% undercut when feasible; floor wins if competitor is below floor.
        chosen=max(min_price, competitor*0.995)
        pwin,pwin_source=win_probability(win_inputs(chosen)); margin=(chosen-unit_cost)/chosen
        expected_profit=max(0,chosen-unit_cost)*qty*pwin
    else:
        _,chosen,pwin,margin,expected_profit,pwin_source=max(scored,key=lambda x:x[0])
    flags=[]
    if credit_hold: flags.append("Customer is on credit hold: route for finance approval before quote release.")
    if qty>available: flags.append(f"Requested quantity ({qty:,}) exceeds available inventory ({available:,}); validate replenishment/lead time.")
    if margin+1e-8 < target_margin: flags.append("Recommended price is below the customer's target margin; approval may be required.")
    if competitor is not None and competitor < min_price-1e-6: flags.append("COMPETITOR PRICE IS BELOW THE HARD MARGIN FLOOR; do not match or undercut without an approved exception.")
    if competitor is not None and chosen > competitor+1e-6: flags.append("Recommended price is above the supplied competitor observation; validate comparability, freshness, and service differences.")
    if hist_avg is not None and abs(chosen-hist_avg)/max(hist_avg,.01)>.08: flags.append("Recommendation differs materially from this customer's historical average; review contract/price history.")
    if agreement_below_floor: flags.append("ACTIVE PRICE AGREEMENT IS BELOW THE HARD MARGIN FLOOR; resolve contract/cost conflict before quote release.")
    if agreement_active and not agreement_below_floor and abs(chosen-contract_price)>1e-6: flags.append("Recommendation deviates from the active binding agreement; obtain authorized contract exception before quote release.")
    if agreement_active and not agreement_below_floor and selected_premiums: flags.append("Active agreement is binding; selected value-added services may require separate line items or an approved agreement amendment. Do not assume the contract price includes the proposed premium.")
    if capacity >= 90: flags.append("Capacity utilization is at least 90%; confirm lead time and apply capacity-priority policy. No automatic surcharge was assumed.")
    if selected_premiums: flags.append("Value-added options selected: " + ", ".join(selected_premiums) + ". Premium is a proposed price uplift, not proof of realized value; confirm availability and customer acceptance.")
    if tier_active: flags.append(f"Quantity tier {quantity_tier.get('tier_id')} applied: {fnum(quantity_tier.get('discount_pct')):.2f}% discount to target-price anchor, subject to floor.")
    max_discount=max(0,(current-min_price)/current*100) if current else 0
    requested_price=current*(1-float(req.get("requested_discount_pct",0))/100); requested_margin=(requested_price-unit_cost)/requested_price if requested_price else -1
    if requested_price < min_price-1e-6: flags.append("Requested discount breaches the configured minimum gross-margin floor.")
    scenarios=[]
    scenario_prices=[("Minimum",min_price),("Target margin",target_price),("Recommended",chosen),("Current",max(min_price,current))]
    if competitor is not None: scenario_prices.append(("Competitor (floor constrained)",max(min_price,competitor)))
    for label,price in scenario_prices:
        pp=win_probability(win_inputs(price))[0]
        scenarios.append({"scenario":label,"price":round(price,4),"gross_margin_pct":round((price-unit_cost)/price*100,2),"win_probability_pct":round(pp*100,1),"expected_gross_profit":round(max(0,price-unit_cost)*qty*pp,2)})
    cost_breakdown={"material":material,"labor":labor,"overhead":overhead,"freight":freight,"tariff":tariff,"setup_allocation":setup_alloc,"engineering_allocation":engineering_alloc,"cost_to_serve":service}
    return {"customer_id":customer.get("customer_id"),"customer_name":customer.get("customer_name"),"product_id":product.get("product_id"),"product_name":product.get("product_name"),"quantity":qty,
      "pricing_strategy":strategy,"unit_cost":round(unit_cost,4),"landed_cost":round(landed_cost,4),"cost_breakdown":cost_breakdown,
      "minimum_price":round(min_price,4),"target_margin_pct":round(target_margin*100,2),"base_target_margin_price":round(base_target_price,4),"target_margin_price":round(target_price,4),"recommended_price":round(chosen,4),"current_price":round(current,4),
      "recommended_discount_pct":round(max(0,(current-chosen)/current*100),2),"maximum_discount_pct":round(max_discount,2),"gross_margin_pct":round(margin*100,2),"win_probability_pct":round(pwin*100,1),"win_probability_source":pwin_source,"list_price":round(list_price,4),"expected_gross_profit":round(expected_profit,2),
      "requested_price":round(requested_price,4),"requested_price_margin_pct":round(requested_margin*100,2),"requested_discount_breaches_floor":requested_price < min_price-1e-6,
      "competitor_price":competitor,"customer_historical_average_price":round(hist_avg,4) if hist_avg is not None else None,"customer_historical_win_rate_pct":round(hist_win*100,1) if hist_win is not None else None,
      "available_inventory":available,"days_on_hand":days_on_hand,"capacity_utilization_pct":capacity,"capacity_adjustment_pct":round(capacity_adjustment*100,2),"selected_value_addons":selected_premiums,"value_addon_premium_pct":round(premium_pct*100,2),
      "agreement":{"agreement_id":agreement.get("agreement_id"),"contract_price":contract_price,"status":"active","binding":True} if agreement_active else None,
      "quantity_tier":{"tier_id":quantity_tier.get("tier_id"),"min_quantity":quantity_tier.get("min_quantity"),"max_quantity":quantity_tier.get("max_quantity"),"discount_pct":fnum(quantity_tier.get("discount_pct"))} if tier_active else None,
      "credit_hold":credit_hold,"approval_flags":flags,"scenarios":scenarios,
      "model_note":"Win probabilities are synthetic-data POC estimates; validate and calibrate on representative real quote outcomes before commercial use."}
