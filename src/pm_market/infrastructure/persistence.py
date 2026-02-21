"""MarketRepository — concrete implementation of MarketRepositoryProtocol.

All queries use raw text() SQL (no ORM).
asyncpg NULL parameter pattern: CAST(:param AS TYPE) IS NULL required for None values.
"""

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_market.domain.models import Market, OrderbookSnapshot, PriceLevel

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_GET_MARKET_SQL = text("""
    SELECT id, title, description, category, status,
           min_price_cents, max_price_cents,
           max_order_quantity, max_position_per_user, max_order_amount_cents,
           maker_fee_bps, taker_fee_bps,
           reserve_balance, pnl_pool,
           total_yes_shares, total_no_shares,
           trading_start_at, trading_end_at,
           resolution_date, resolved_at, settled_at, resolution_result,
           created_at, updated_at
    FROM markets
    WHERE id = :market_id
""")

_LIST_MARKETS_SQL = text("""
    SELECT id, title, description, category, status,
           min_price_cents, max_price_cents,
           max_order_quantity, max_position_per_user, max_order_amount_cents,
           maker_fee_bps, taker_fee_bps,
           reserve_balance, pnl_pool,
           total_yes_shares, total_no_shares,
           trading_start_at, trading_end_at,
           resolution_date, resolved_at, settled_at, resolution_result,
           created_at, updated_at
    FROM markets
    WHERE
        (CAST(:status AS TEXT) IS NULL OR status = CAST(:status AS TEXT))
        AND (CAST(:category AS TEXT) IS NULL OR category = CAST(:category AS TEXT))
        AND (
            CAST(:cursor_ts AS TIMESTAMPTZ) IS NULL
            OR created_at < CAST(:cursor_ts AS TIMESTAMPTZ)
            OR (
                created_at = CAST(:cursor_ts AS TIMESTAMPTZ)
                AND id < CAST(:cursor_id AS TEXT)
            )
        )
    ORDER BY created_at DESC, id DESC
    LIMIT :limit
""")

_ORDERBOOK_AGGREGATE_SQL = text("""
    SELECT book_price, book_direction,
           SUM(remaining_quantity) AS total_qty
    FROM orders
    WHERE market_id = :market_id
      AND status IN ('OPEN', 'PARTIALLY_FILLED')
    GROUP BY book_price, book_direction
    ORDER BY book_price
""")

_LAST_TRADE_SQL = text("""
    SELECT price
    FROM trades
    WHERE market_id = :market_id
    ORDER BY executed_at DESC, id DESC
    LIMIT 1
""")

# ---------------------------------------------------------------------------
# Row mappers
# ---------------------------------------------------------------------------

def _row_to_market(row: object) -> Market:
    return Market(
        id=row.id,  # type: ignore[attr-defined]
        title=row.title,  # type: ignore[attr-defined]
        description=row.description,  # type: ignore[attr-defined]
        category=row.category,  # type: ignore[attr-defined]
        status=row.status,  # type: ignore[attr-defined]
        min_price_cents=row.min_price_cents,  # type: ignore[attr-defined]
        max_price_cents=row.max_price_cents,  # type: ignore[attr-defined]
        max_order_quantity=row.max_order_quantity,  # type: ignore[attr-defined]
        max_position_per_user=row.max_position_per_user,  # type: ignore[attr-defined]
        max_order_amount_cents=row.max_order_amount_cents,  # type: ignore[attr-defined]
        maker_fee_bps=row.maker_fee_bps,  # type: ignore[attr-defined]
        taker_fee_bps=row.taker_fee_bps,  # type: ignore[attr-defined]
        reserve_balance=row.reserve_balance,  # type: ignore[attr-defined]
        pnl_pool=row.pnl_pool,  # type: ignore[attr-defined]
        total_yes_shares=row.total_yes_shares,  # type: ignore[attr-defined]
        total_no_shares=row.total_no_shares,  # type: ignore[attr-defined]
        trading_start_at=row.trading_start_at,  # type: ignore[attr-defined]
        trading_end_at=row.trading_end_at,  # type: ignore[attr-defined]
        resolution_date=row.resolution_date,  # type: ignore[attr-defined]
        resolved_at=row.resolved_at,  # type: ignore[attr-defined]
        settled_at=row.settled_at,  # type: ignore[attr-defined]
        resolution_result=row.resolution_result,  # type: ignore[attr-defined]
        created_at=row.created_at,  # type: ignore[attr-defined]
        updated_at=row.updated_at,  # type: ignore[attr-defined]
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class MarketRepository:
    """Concrete repository — all operations are read-only SQL queries."""

    async def get_market_by_id(
        self, db: AsyncSession, market_id: str
    ) -> Market | None:
        result = await db.execute(_GET_MARKET_SQL, {"market_id": market_id})
        row = result.fetchone()
        return _row_to_market(row) if row else None

    async def list_markets(
        self,
        db: AsyncSession,
        status: str | None,
        category: str | None,
        cursor_ts: str | None,
        cursor_id: str | None,
        limit: int,
    ) -> list[Market]:
        # asyncpg requires a real datetime object for TIMESTAMPTZ parameters,
        # not an ISO string.  Parse the cursor timestamp here.
        cursor_ts_dt: datetime | None = None
        if cursor_ts is not None:
            cursor_ts_dt = datetime.fromisoformat(cursor_ts)

        result = await db.execute(
            _LIST_MARKETS_SQL,
            {
                "status": status,
                "category": category,
                "cursor_ts": cursor_ts_dt,
                "cursor_id": cursor_id,
                "limit": limit,
            },
        )
        rows = result.fetchall()
        return [_row_to_market(row) for row in rows]

    async def get_orderbook_snapshot(
        self, db: AsyncSession, market_id: str, levels: int
    ) -> OrderbookSnapshot:
        # Step 1: aggregate active orders by price level
        agg_result = await db.execute(
            _ORDERBOOK_AGGREGATE_SQL, {"market_id": market_id}
        )
        agg_rows = agg_result.fetchall()

        bids: list[PriceLevel] = []
        asks: list[PriceLevel] = []
        for row in agg_rows:
            level = PriceLevel(
                price_cents=row.book_price,
                total_quantity=row.total_qty,
            )
            if row.book_direction == "BUY":
                bids.append(level)
            else:
                asks.append(level)

        # Sort: bids descending, asks ascending; then truncate to `levels`
        bids.sort(key=lambda lv: lv.price_cents, reverse=True)
        asks.sort(key=lambda lv: lv.price_cents)
        bids = bids[:levels]
        asks = asks[:levels]

        # Step 2: last trade price
        trade_result = await db.execute(
            _LAST_TRADE_SQL, {"market_id": market_id}
        )
        trade_row = trade_result.fetchone()
        last_price = trade_row.price if trade_row else None

        return OrderbookSnapshot(
            market_id=market_id,
            yes_bids=bids,
            yes_asks=asks,
            last_trade_price_cents=last_price,
            updated_at=datetime.now(UTC),
        )
