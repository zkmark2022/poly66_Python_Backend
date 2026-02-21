"""TRANSFER_NO scenario: SYNTHETIC_BUY + SYNTHETIC_SELL — NO shares change hands."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_clearing.domain.fee import calc_released_cost
from src.pm_matching.domain.models import TradeResult

_UNFREEZE_DEBIT_SQL = text("""
    UPDATE accounts
    SET frozen_balance    = frozen_balance    - :unfreeze,
        available_balance = available_balance + :refund,
        version = version + 1, updated_at = NOW()
    WHERE user_id = :user_id
""")

_ADD_NO_VOLUME_SQL = text("""
    INSERT INTO positions (user_id, market_id, no_volume, no_cost_sum)
    VALUES (:user_id, :market_id, :qty, :cost)
    ON CONFLICT (user_id, market_id) DO UPDATE
    SET no_volume   = positions.no_volume   + :qty,
        no_cost_sum = positions.no_cost_sum + :cost,
        updated_at = NOW()
""")

_GET_BUYER_NO_SQL = text("""
    SELECT no_volume, no_cost_sum, no_pending_sell
    FROM positions WHERE user_id = :user_id AND market_id = :market_id
    FOR UPDATE
""")

_REDUCE_NO_VOLUME_SQL = text("""
    UPDATE positions
    SET no_volume       = no_volume       - :qty,
        no_cost_sum     = no_cost_sum     - :cost_released,
        no_pending_sell = no_pending_sell - :qty,
        updated_at = NOW()
    WHERE user_id = :user_id AND market_id = :market_id
""")

_ADD_BALANCE_SQL = text("""
    UPDATE accounts
    SET available_balance = available_balance + :amount,
        version = version + 1, updated_at = NOW()
    WHERE user_id = :user_id
""")


async def clear_transfer_no(
    trade: TradeResult, market: object, db: AsyncSession
) -> None:
    """TRANSFER_NO: SYNTHETIC_BUY + SYNTHETIC_SELL — NO shares change hands."""
    no_trade_price = 100 - trade.price  # convert YES trade price to NO price
    seller_cost = no_trade_price * trade.quantity  # SYNTHETIC_SELL (Buy NO) pays this

    # "seller" (Buy NO / SYNTHETIC_SELL): unfreeze funds, gain NO shares
    await db.execute(
        _UNFREEZE_DEBIT_SQL,
        {"user_id": trade.sell_user_id, "unfreeze": seller_cost, "refund": 0},
    )
    await db.execute(
        _ADD_NO_VOLUME_SQL,
        {
            "user_id": trade.sell_user_id,
            "market_id": trade.market_id,
            "qty": trade.quantity,
            "cost": seller_cost,
        },
    )

    # "buyer" (Sell NO / SYNTHETIC_BUY): fetch NO position, release pending, gain funds
    row = (
        await db.execute(
            _GET_BUYER_NO_SQL,
            {"user_id": trade.buy_user_id, "market_id": trade.market_id},
        )
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Buyer NO position not found: {trade.buy_user_id}")
    no_vol, no_cost, _ = row
    cost_released = calc_released_cost(no_cost, no_vol, trade.quantity)
    proceeds = no_trade_price * trade.quantity

    await db.execute(
        _REDUCE_NO_VOLUME_SQL,
        {
            "user_id": trade.buy_user_id,
            "market_id": trade.market_id,
            "qty": trade.quantity,
            "cost_released": cost_released,
        },
    )
    await db.execute(
        _ADD_BALANCE_SQL,
        {"user_id": trade.buy_user_id, "amount": proceeds},
    )

    market.pnl_pool -= proceeds - cost_released  # type: ignore[attr-defined]
