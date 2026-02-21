from dataclasses import dataclass
from datetime import datetime


@dataclass
class BookOrder:
    """In-memory orderbook entry."""

    order_id: str
    user_id: str
    book_type: str  # for determine_scenario + self-trade check
    quantity: int  # remaining matchable quantity
    created_at: datetime


@dataclass
class TradeResult:
    """Single fill passed from matching to clearing."""

    buy_order_id: str
    sell_order_id: str
    buy_user_id: str
    sell_user_id: str
    market_id: str
    price: int  # YES trade price (maker price)
    quantity: int
    buy_book_type: str
    sell_book_type: str
    buy_original_price: int  # for Synthetic fee calc (NO price)
    maker_order_id: str
    taker_order_id: str
