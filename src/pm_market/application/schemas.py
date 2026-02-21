"""Pydantic schemas for pm_market API responses.

Cursor format for markets (VARCHAR PK, not sequential):
  {"ts": "<created_at ISO>", "id": "<market_id>"}
  Encoded as Base64 JSON string.

YES->NO orderbook conversion (per API contract §4.3):
  NO bids[i].price = 100 - YES asks[i].price (same qty), sorted descending
  NO asks[i].price = 100 - YES bids[i].price (same qty), sorted ascending
"""

import base64
import json

from pydantic import BaseModel

from src.pm_common.cents import cents_to_display
from src.pm_market.domain.models import Market, OrderbookSnapshot

# ---------------------------------------------------------------------------
# Cursor utilities
# ---------------------------------------------------------------------------


def cursor_encode(last_market: Market) -> str:
    """Encode composite cursor from last market in page."""
    payload = {
        "ts": last_market.created_at.isoformat(),
        "id": last_market.id,
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def cursor_decode(cursor: str | None) -> tuple[str | None, str | None]:
    """Decode composite cursor -> (ts_iso, market_id), or (None, None) on error."""
    if cursor is None:
        return None, None
    try:
        data = json.loads(base64.b64decode(cursor.encode()).decode())
        return data["ts"], data["id"]
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Price level
# ---------------------------------------------------------------------------


class PriceLevelOut(BaseModel):
    price_cents: int
    total_quantity: int


class OrderSideOut(BaseModel):
    bids: list[PriceLevelOut]
    asks: list[PriceLevelOut]


# ---------------------------------------------------------------------------
# Orderbook response
# ---------------------------------------------------------------------------


def _to_no_view(
    yes_bids: list[PriceLevelOut],
    yes_asks: list[PriceLevelOut],
) -> tuple[list[PriceLevelOut], list[PriceLevelOut]]:
    """Convert YES orderbook to NO dual view.

    NO bids come from YES asks: price = 100 - yes_ask_price, same qty.
    NO asks come from YES bids: price = 100 - yes_bid_price, same qty.
    Sort result: no.bids descending, no.asks ascending.
    """
    no_bids = sorted(
        [
            PriceLevelOut(price_cents=100 - lv.price_cents, total_quantity=lv.total_quantity)
            for lv in yes_asks
        ],
        key=lambda x: x.price_cents,
        reverse=True,
    )
    no_asks = sorted(
        [
            PriceLevelOut(price_cents=100 - lv.price_cents, total_quantity=lv.total_quantity)
            for lv in yes_bids
        ],
        key=lambda x: x.price_cents,
    )
    return no_bids, no_asks


class OrderbookResponse(BaseModel):
    market_id: str
    yes: OrderSideOut
    no: OrderSideOut
    last_trade_price_cents: int | None
    updated_at: str

    @classmethod
    def from_snapshot(cls, snapshot: OrderbookSnapshot) -> "OrderbookResponse":
        yes_bids = [
            PriceLevelOut(price_cents=lv.price_cents, total_quantity=lv.total_quantity)
            for lv in snapshot.yes_bids
        ]
        yes_asks = [
            PriceLevelOut(price_cents=lv.price_cents, total_quantity=lv.total_quantity)
            for lv in snapshot.yes_asks
        ]
        no_bids, no_asks = _to_no_view(yes_bids, yes_asks)
        return cls(
            market_id=snapshot.market_id,
            yes=OrderSideOut(bids=yes_bids, asks=yes_asks),
            no=OrderSideOut(bids=no_bids, asks=no_asks),
            last_trade_price_cents=snapshot.last_trade_price_cents,
            updated_at=snapshot.updated_at.isoformat(),
        )


# ---------------------------------------------------------------------------
# Market list item (lightweight — no pnl_pool, no max_order_* risk params)
# ---------------------------------------------------------------------------


class MarketListItem(BaseModel):
    id: str
    title: str
    description: str | None
    category: str | None
    status: str
    min_price_cents: int
    max_price_cents: int
    maker_fee_bps: int
    taker_fee_bps: int
    reserve_balance_cents: int
    reserve_balance_display: str
    total_yes_shares: int
    total_no_shares: int
    trading_start_at: str | None
    resolution_date: str | None

    @classmethod
    def from_domain(cls, m: Market) -> "MarketListItem":
        return cls(
            id=m.id,
            title=m.title,
            description=m.description,
            category=m.category,
            status=m.status,
            min_price_cents=m.min_price_cents,
            max_price_cents=m.max_price_cents,
            maker_fee_bps=m.maker_fee_bps,
            taker_fee_bps=m.taker_fee_bps,
            reserve_balance_cents=m.reserve_balance,
            reserve_balance_display=cents_to_display(m.reserve_balance),
            total_yes_shares=m.total_yes_shares,
            total_no_shares=m.total_no_shares,
            trading_start_at=m.trading_start_at.isoformat() if m.trading_start_at else None,
            resolution_date=m.resolution_date.isoformat() if m.resolution_date else None,
        )


class MarketListResponse(BaseModel):
    items: list[MarketListItem]
    next_cursor: str | None
    has_more: bool


# ---------------------------------------------------------------------------
# Market detail (full fields — includes pnl_pool + all risk params)
# ---------------------------------------------------------------------------


class MarketDetail(BaseModel):
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
    reserve_balance_cents: int
    reserve_balance_display: str
    pnl_pool_cents: int
    pnl_pool_display: str
    total_yes_shares: int
    total_no_shares: int
    trading_start_at: str | None
    trading_end_at: str | None
    resolution_date: str | None
    resolved_at: str | None
    settled_at: str | None
    resolution_result: str | None

    @classmethod
    def from_domain(cls, m: Market) -> "MarketDetail":
        def _iso(dt: object) -> str | None:
            if dt is None:
                return None
            return dt.isoformat()  # type: ignore[attr-defined]

        return cls(
            id=m.id,
            title=m.title,
            description=m.description,
            category=m.category,
            status=m.status,
            min_price_cents=m.min_price_cents,
            max_price_cents=m.max_price_cents,
            max_order_quantity=m.max_order_quantity,
            max_position_per_user=m.max_position_per_user,
            max_order_amount_cents=m.max_order_amount_cents,
            maker_fee_bps=m.maker_fee_bps,
            taker_fee_bps=m.taker_fee_bps,
            reserve_balance_cents=m.reserve_balance,
            reserve_balance_display=cents_to_display(m.reserve_balance),
            pnl_pool_cents=m.pnl_pool,
            pnl_pool_display=cents_to_display(m.pnl_pool),
            total_yes_shares=m.total_yes_shares,
            total_no_shares=m.total_no_shares,
            trading_start_at=_iso(m.trading_start_at),
            trading_end_at=_iso(m.trading_end_at),
            resolution_date=_iso(m.resolution_date),
            resolved_at=_iso(m.resolved_at),
            settled_at=_iso(m.settled_at),
            resolution_result=m.resolution_result,
        )
