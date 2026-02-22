"""Persist a single trade row to the trades table."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_common.datetime_utils import utc_now
from src.pm_common.id_generator import generate_id
from src.pm_matching.domain.models import TradeResult

_INSERT_TRADE_SQL = text("""
    INSERT INTO trades (
        trade_id, market_id, scenario,
        buy_order_id, sell_order_id,
        buy_user_id, sell_user_id,
        buy_book_type, sell_book_type,
        price, quantity,
        maker_order_id, taker_order_id,
        maker_fee, taker_fee,
        buy_realized_pnl, sell_realized_pnl,
        executed_at
    ) VALUES (
        :trade_id, :market_id, :scenario,
        :buy_order_id, :sell_order_id,
        :buy_user_id, :sell_user_id,
        :buy_book_type, :sell_book_type,
        :price, :quantity,
        :maker_order_id, :taker_order_id,
        :maker_fee, :taker_fee,
        :buy_realized_pnl, :sell_realized_pnl,
        :executed_at
    )
""")


async def write_trade(
    trade: TradeResult,
    scenario: str,
    maker_fee: int,
    taker_fee: int,
    buy_pnl: int | None,
    sell_pnl: int | None,
    db: AsyncSession,
) -> None:
    """Insert one row into the trades table."""
    await db.execute(
        _INSERT_TRADE_SQL,
        {
            "trade_id": generate_id(),
            "market_id": trade.market_id,
            "scenario": scenario,
            "buy_order_id": trade.buy_order_id,
            "sell_order_id": trade.sell_order_id,
            "buy_user_id": trade.buy_user_id,
            "sell_user_id": trade.sell_user_id,
            "buy_book_type": trade.buy_book_type,
            "sell_book_type": trade.sell_book_type,
            "price": trade.price,
            "quantity": trade.quantity,
            "maker_order_id": trade.maker_order_id,
            "taker_order_id": trade.taker_order_id,
            "maker_fee": maker_fee,
            "taker_fee": taker_fee,
            "buy_realized_pnl": buy_pnl,
            "sell_realized_pnl": sell_pnl,
            "executed_at": utc_now(),
        },
    )
