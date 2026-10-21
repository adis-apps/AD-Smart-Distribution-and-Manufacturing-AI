import unittest
from app.pricing_engine import recommend

class PricingEngineTests(unittest.TestCase):
    def setUp(self):
        self.product={"product_id":"BAG-001","product_name":"Test Bag","material_cost":15.2,"labor_cost":2.1,"overhead_cost":2.0,"freight_cost":1.3,"tariff_cost":0,"min_margin_pct":.15}
        self.customer={"customer_id":"C1","customer_name":"Test Customer","segment":"Food & Beverage","target_margin_pct":.18,"credit_hold":False}
        self.inventory={"available_qty":200000,"days_on_hand":40}
    def test_minimum_price_meets_floor(self):
        result=recommend(self.product,self.customer,self.inventory,None,{"quantity":1000,"current_price":26,"requested_discount_pct":8,"competitor_price":24.5})
        self.assertGreaterEqual(result["minimum_price"],20.6/.85-1e-5)
        self.assertGreaterEqual(result["recommended_price"]+1e-6,result["minimum_price"])
    def test_setup_and_engineering_cost_are_allocated(self):
        profile={"setup_cost":100,"engineering_cost":50,"setup_allocation_qty":1000,"cost_to_serve_unit":.2}
        result=recommend(self.product,self.customer,self.inventory,None,{"quantity":1000,"current_price":26,"requested_discount_pct":0},profile)
        self.assertAlmostEqual(result["unit_cost"],20.6+.1+.05+.2,places=4)
        self.assertAlmostEqual(result["cost_breakdown"]["setup_allocation"],.1,places=4)

    def test_active_agreement_below_floor_does_not_override_floor(self):
        agreement={"agreement_id":"SPA-TEST","contract_price":10,"status":"active"}
        result=recommend(self.product,self.customer,self.inventory,None,{"quantity":1000,"current_price":26,"requested_discount_pct":0},None,agreement)
        self.assertGreaterEqual(result["recommended_price"]+1e-6,result["minimum_price"])
        self.assertTrue(any("BELOW THE HARD MARGIN FLOOR" in x for x in result["approval_flags"]))

    def test_quantity_tier_applies_discount_anchor_but_respects_floor(self):
        tier={"tier_id":"TIER-25K","min_quantity":25000,"max_quantity":None,"discount_pct":3,"status":"active"}
        result=recommend(self.product,self.customer,self.inventory,None,{"quantity":30000,"current_price":26,"requested_discount_pct":0},None,None,tier)
        self.assertIsNotNone(result["quantity_tier"])
        self.assertGreaterEqual(result["target_margin_price"]+1e-6,result["minimum_price"])

    def test_expired_agreement_is_ignored(self):
        agreement={"agreement_id":"SPA-OLD","contract_price":12,"status":"active","start_date":"2020-01-01","end_date":"2020-12-31"}
        result=recommend(self.product,self.customer,self.inventory,None,{"quantity":1000,"current_price":26,"requested_discount_pct":0},None,agreement)
        self.assertIsNone(result["agreement"])
        self.assertFalse(any("ACTIVE PRICE AGREEMENT" in x for x in result["approval_flags"]))

    def test_value_add_on_is_explicit(self):
        base=recommend(self.product,self.customer,self.inventory,None,{"quantity":1000,"current_price":26,"requested_discount_pct":0})
        premium=recommend(self.product,self.customer,self.inventory,None,{"quantity":1000,"current_price":26,"requested_discount_pct":0,"expedited_delivery":True})
        self.assertEqual(premium["selected_value_addons"],["expedited_delivery"])
        self.assertGreater(premium["value_addon_premium_pct"],base["value_addon_premium_pct"])

    def test_win_focused_strategy_undercuts_competitor_when_above_floor(self):
        req={"quantity":1000,"current_price":26,"requested_discount_pct":0,"competitor_price":25,"pricing_strategy":"win_focused"}
        result=recommend(self.product,self.customer,self.inventory,None,req)
        self.assertAlmostEqual(result["recommended_price"],24.875,places=3)
        self.assertGreaterEqual(result["recommended_price"]+1e-6,result["minimum_price"])

    def test_competitor_below_floor_does_not_override_floor(self):
        req={"quantity":1000,"current_price":26,"requested_discount_pct":0,"competitor_price":15,"pricing_strategy":"win_focused"}
        result=recommend(self.product,self.customer,self.inventory,None,req)
        self.assertAlmostEqual(result["recommended_price"],result["minimum_price"],places=3)
        self.assertTrue(any("COMPETITOR PRICE IS BELOW" in x for x in result["approval_flags"]))

    def test_active_agreement_is_exact_binding_price_when_feasible(self):
        agreement={"agreement_id":"SPA-TEST","contract_price":25.5,"status":"active"}
        result=recommend(self.product,self.customer,self.inventory,None,{"quantity":1000,"current_price":26,"requested_discount_pct":0,"competitor_price":24,"pricing_strategy":"win_focused"},None,agreement)
        self.assertAlmostEqual(result["recommended_price"],25.5,places=4)
        self.assertTrue(result["agreement"]["binding"])

    def test_strategies_are_returned_and_balanced_is_supported(self):
        result=recommend(self.product,self.customer,self.inventory,None,{"quantity":1000,"current_price":26,"requested_discount_pct":0,"competitor_price":25,"pricing_strategy":"balanced"})
        self.assertEqual(result["pricing_strategy"],"balanced")
        self.assertGreaterEqual(result["recommended_price"]+1e-6,result["minimum_price"])

    def test_high_capacity_creates_review_flag(self):
        result=recommend(self.product,self.customer,self.inventory,None,{"quantity":1000,"current_price":26,"requested_discount_pct":0},{"capacity_utilization_pct":95})
        self.assertTrue(any("Capacity utilization" in x for x in result["approval_flags"]))

    def test_credit_hold_flag(self):
        c=dict(self.customer,credit_hold=True)
        result=recommend(self.product,c,self.inventory,None,{"quantity":1000,"current_price":26,"requested_discount_pct":8,"competitor_price":24.5})
        self.assertTrue(any("credit hold" in x.lower() for x in result["approval_flags"]))
    def test_inventory_shortage_flag(self):
        result=recommend(self.product,self.customer,{"available_qty":10,"days_on_hand":1},None,{"quantity":1000,"current_price":26,"requested_discount_pct":8,"competitor_price":24.5})
        self.assertTrue(any("exceeds available inventory" in x for x in result["approval_flags"]))

if __name__=="__main__": unittest.main()
