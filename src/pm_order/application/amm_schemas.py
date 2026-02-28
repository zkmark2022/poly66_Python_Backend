"""AMM-specific schemas for Atomic Replace and Batch Cancel APIs."""
from pydantic import BaseModel, Field

from src.pm_order.application.schemas import PlaceOrderRequest


class ReplaceRequest(BaseModel):
    old_order_id: str
    new_order: PlaceOrderRequest


class ReplaceResponse(BaseModel):
    old_order_id: str
    old_order_status: str
    old_order_filled_quantity: int
    old_order_original_quantity: int
    new_order: dict
    trades: list[dict]


class BatchCancelRequest(BaseModel):
    market_id: str
    cancel_scope: str = Field(
        default="ALL", pattern="^(ALL|BUY_ONLY|SELL_ONLY)$"
    )


class BatchCancelResponse(BaseModel):
    market_id: str
    cancelled_count: int
    total_unfrozen_funds_cents: int
    total_unfrozen_yes_shares: int
    total_unfrozen_no_shares: int
