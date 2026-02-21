# src/pm_order/application/schemas.py
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


class PlaceOrderRequest(BaseModel):
    client_order_id: str
    market_id: str
    side: Literal["YES", "NO"]
    direction: Literal["BUY", "SELL"]
    price_cents: int
    quantity: int
    time_in_force: Literal["GTC", "IOC"] = "GTC"

    @field_validator("client_order_id")
    @classmethod
    def no_whitespace(cls, v: str) -> str:
        if not v or v != v.strip() or " " in v:
            raise ValueError("client_order_id must not contain whitespace")
        return v


class TradeResponse(BaseModel):
    buy_order_id: str
    sell_order_id: str
    price: int
    quantity: int
    scenario: str


class OrderResponse(BaseModel):
    id: str
    client_order_id: str
    market_id: str
    original_side: str
    original_direction: str
    original_price_cents: int
    book_type: str
    price_type: str
    time_in_force: str
    quantity: int
    filled_quantity: int
    remaining_quantity: int
    frozen_amount: int
    frozen_asset_type: str
    status: str
    cancel_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PlaceOrderResponse(BaseModel):
    order: OrderResponse
    trades: list[TradeResponse]
    netting_result: dict[str, int] | None


class CancelOrderResponse(BaseModel):
    order_id: str
    status: str
    unfrozen_amount: int
    unfrozen_asset_type: str
    remaining_quantity_cancelled: int


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    next_cursor: str | None
    has_more: bool
