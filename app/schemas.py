from pydantic import BaseModel, Field
from typing import Optional

class RecommendRequest(BaseModel):
    customer_id: str
    product_id: str
    quantity: int = Field(gt=0, le=100_000_000)
    current_price: float = Field(gt=0)
    requested_discount_pct: float = Field(default=0, ge=0, le=100)
    pricing_strategy: str = Field(default="win_focused", pattern="^(win_focused|balanced|margin_focused)$")
    competitor_price: Optional[float] = Field(default=None, gt=0)
    expedited_delivery: bool = False
    guaranteed_inventory: bool = False
    extended_warranty: bool = False
    regulatory_documentation: bool = False
    sustainability_certified: bool = False

class FeedbackRequest(BaseModel):
    customer_id: str
    product_id: str
    quantity: int = Field(gt=0)
    recommended_price: float = Field(gt=0)
    selected_price: float = Field(gt=0)
    outcome: str = Field(description="e.g. won, lost, pending, ignored")
    notes: str = ""
