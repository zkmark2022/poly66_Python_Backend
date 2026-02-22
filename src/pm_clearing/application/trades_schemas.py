# src/pm_clearing/application/trades_schemas.py
"""Pydantic schemas for trades API."""
from pydantic import BaseModel


class TradeResponse(BaseModel):
    trade_id: str
    market_id: str
    scenario: str
    price: int
    quantity: int
    buy_user_id: str
    sell_user_id: str
    taker_fee: int
    buy_realized_pnl: int | None
    sell_realized_pnl: int | None
    executed_at: str | None


class TradeListResponse(BaseModel):
    items: list[TradeResponse]
    has_more: bool
    next_cursor: str | None
