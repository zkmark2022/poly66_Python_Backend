"""TRANSFER_YES scenario: NATIVE_BUY + NATIVE_SELL — YES shares change hands."""
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

_ADD_YES_VOLUME_SQL = text("""
    INSERT INTO positions (user_id, market_id, yes_volume, yes_cost_sum)
    VALUES (:user_id, :market_id, :qty, :cost)
    ON CONFLICT (user_id, market_id) DO UPDATE
    SET yes_volume   = positions.yes_volume   + :qty,
        yes_cost_sum = positions.yes_cost_sum + :cost,
        updated_at = NOW()
""")

_GET_SELLER_YES_SQL = text("""
    SELECT yes_volume, yes_cost_sum, yes_pending_sell
    FROM positions WHERE user_id = :user_id AND market_id = :market_id
    FOR UPDATE
""")

_REDUCE_YES_VOLUME_SQL = text("""
    UPDATE positions
    SET yes_volume       = yes_volume       - :qty,
        yes_cost_sum     = yes_cost_sum     - :cost_released,
        yes_pending_sell = yes_pending_sell - :qty,
        updated_at = NOW()
    WHERE user_id = :user_id AND market_id = :market_id
""")

_ADD_BALANCE_SQL = text("""
    UPDATE accounts
    SET available_balance = available_balance + :amount,
        version = version + 1, updated_at = NOW()
    WHERE user_id = :user_id
""")


async def clear_transfer_yes(
    trade: TradeResult, market: object, db: AsyncSession
) -> None:
    """TRANSFER_YES: NATIVE_BUY + NATIVE_SELL — YES shares change hands."""
    buyer_cost = trade.price * trade.quantity

    # buyer: unfreeze funds, gain YES shares
    await db.execute(
        _UNFREEZE_DEBIT_SQL,
        {"user_id": trade.buy_user_id, "unfreeze": buyer_cost, "refund": 0},
    )
    await db.execute(
        _ADD_YES_VOLUME_SQL,
        {
            "user_id": trade.buy_user_id,
            "market_id": trade.market_id,
            "qty": trade.quantity,
            "cost": buyer_cost,
        },
    )

    # seller: fetch position to compute released cost
    row = (
        await db.execute(
            _GET_SELLER_YES_SQL,
            {"user_id": trade.sell_user_id, "market_id": trade.market_id},
        )
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Seller position not found: {trade.sell_user_id}")
    yes_vol, yes_cost, _ = row
    cost_released = calc_released_cost(yes_cost, yes_vol, trade.quantity)
    proceeds = trade.price * trade.quantity

    # seller: reduce YES volume + pending_sell, receive proceeds
    await db.execute(
        _REDUCE_YES_VOLUME_SQL,
        {
            "user_id": trade.sell_user_id,
            "market_id": trade.market_id,
            "qty": trade.quantity,
            "cost_released": cost_released,
        },
    )
    await db.execute(
        _ADD_BALANCE_SQL,
        {"user_id": trade.sell_user_id, "amount": proceeds},
    )

    market.pnl_pool -= proceeds - cost_released  # type: ignore[attr-defined]
