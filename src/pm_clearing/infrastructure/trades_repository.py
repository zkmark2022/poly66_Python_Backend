# src/pm_clearing/infrastructure/trades_repository.py
"""Read-only trades queries — user perspective."""
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_LIST_SQL = text("""
    SELECT trade_id, market_id, scenario,
           buy_order_id, sell_order_id,
           buy_user_id, sell_user_id,
           buy_book_type, sell_book_type,
           price, quantity,
           maker_order_id, taker_order_id,
           maker_fee, taker_fee,
           buy_realized_pnl, sell_realized_pnl,
           executed_at
    FROM trades
    WHERE (buy_user_id = :user_id OR sell_user_id = :user_id)
      AND (CAST(:market_id AS TEXT) IS NULL OR market_id = :market_id)
      AND (CAST(:cursor_id AS TEXT) IS NULL OR trade_id < :cursor_id)
    ORDER BY executed_at DESC, trade_id DESC
    LIMIT :limit
""")


class TradesRepository:
    async def list_by_user(
        self,
        user_id: str,
        market_id: str | None,
        limit: int,
        cursor_id: str | None,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                _LIST_SQL,
                {
                    "user_id": user_id,
                    "market_id": market_id,
                    "limit": limit,
                    "cursor_id": cursor_id,
                },
            )
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "trade_id": row.trade_id,
        "market_id": row.market_id,
        "scenario": row.scenario,
        "buy_order_id": row.buy_order_id,
        "sell_order_id": row.sell_order_id,
        "buy_user_id": row.buy_user_id,
        "sell_user_id": row.sell_user_id,
        "buy_book_type": row.buy_book_type,
        "sell_book_type": row.sell_book_type,
        "price": row.price,
        "quantity": row.quantity,
        "maker_order_id": row.maker_order_id,
        "taker_order_id": row.taker_order_id,
        "maker_fee": row.maker_fee,
        "taker_fee": row.taker_fee,
        "buy_realized_pnl": row.buy_realized_pnl,
        "sell_realized_pnl": row.sell_realized_pnl,
        "executed_at": row.executed_at.isoformat() if row.executed_at else None,
    }
