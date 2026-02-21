"""Domain models for pm_market — pure dataclasses, no business logic."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Market:
    id: str
    title: str
    description: str | None
    category: str | None
    status: str
    min_price_cents: int
    max_price_cents: int
    max_order_quantity: int
    max_position_per_user: int
    max_order_amount_cents: int
    maker_fee_bps: int
    taker_fee_bps: int
    reserve_balance: int
    pnl_pool: int
    total_yes_shares: int
    total_no_shares: int
    trading_start_at: datetime | None
    trading_end_at: datetime | None
    resolution_date: datetime | None
    resolved_at: datetime | None
    settled_at: datetime | None
    resolution_result: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class PriceLevel:
    """Single price level in an order book."""

    price_cents: int
    total_quantity: int


@dataclass
class OrderbookSnapshot:
    """YES-side order book snapshot. NO conversion done in schema layer."""

    market_id: str
    yes_bids: list[PriceLevel]       # descending by price
    yes_asks: list[PriceLevel]       # ascending by price
    last_trade_price_cents: int | None
    updated_at: datetime
