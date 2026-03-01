"""BURN scenario: SYNTHETIC_BUY + NATIVE_SELL — destroy YES/NO pair, release reserve."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_clearing.domain.fee import calc_released_cost
from src.pm_matching.domain.models import TradeResult

_GET_YES_POS_SQL = text("""
    SELECT yes_volume, yes_cost_sum, yes_pending_sell
    FROM positions WHERE user_id = :user_id AND market_id = :market_id
    FOR UPDATE
""")

_GET_NO_POS_SQL = text("""
    SELECT no_volume, no_cost_sum, no_pending_sell
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


async def clear_burn(
    trade: TradeResult, market: object, db: AsyncSession
) -> tuple[int | None, int | None]:
    """BURN: SYNTHETIC_BUY + NATIVE_SELL — destroy YES/NO pair, release reserve."""
    payout_per_share = 100  # each pair worth 100 cents at settlement

    # sell_user (NATIVE_SELL / Sell YES): fetch YES position
    yes_row = (
        await db.execute(
            _GET_YES_POS_SQL,
            {"user_id": trade.sell_user_id, "market_id": trade.market_id},
        )
    ).fetchone()
    if yes_row is None:
        raise RuntimeError(f"Sell YES position not found: {trade.sell_user_id}")
    yes_vol, yes_cost, _ = yes_row
    yes_cost_rel = calc_released_cost(yes_cost, yes_vol, trade.quantity)
    yes_proceeds = trade.price * trade.quantity

    # buy_user (SYNTHETIC_BUY / Sell NO): fetch NO position
    no_row = (
        await db.execute(
            _GET_NO_POS_SQL,
            {"user_id": trade.buy_user_id, "market_id": trade.market_id},
        )
    ).fetchone()
    if no_row is None:
        raise RuntimeError(f"Sell NO position not found: {trade.buy_user_id}")
    no_vol, no_cost, _ = no_row
    no_cost_rel = calc_released_cost(no_cost, no_vol, trade.quantity)
    no_trade_price = 100 - trade.price
    no_proceeds = no_trade_price * trade.quantity

    # Release YES side
    await db.execute(
        _REDUCE_YES_VOLUME_SQL,
        {
            "user_id": trade.sell_user_id,
            "market_id": trade.market_id,
            "qty": trade.quantity,
            "cost_released": yes_cost_rel,
        },
    )
    yes_result = await db.execute(
        _ADD_BALANCE_SQL,
        {"user_id": trade.sell_user_id, "amount": yes_proceeds},
    )
    if yes_result.rowcount == 0:
        raise RuntimeError(f"Account not found for YES seller: {trade.sell_user_id}")

    # Release NO side
    await db.execute(
        _REDUCE_NO_VOLUME_SQL,
        {
            "user_id": trade.buy_user_id,
            "market_id": trade.market_id,
            "qty": trade.quantity,
            "cost_released": no_cost_rel,
        },
    )
    no_result = await db.execute(
        _ADD_BALANCE_SQL,
        {"user_id": trade.buy_user_id, "amount": no_proceeds},
    )
    if no_result.rowcount == 0:
        raise RuntimeError(f"Account not found for NO seller: {trade.buy_user_id}")

    # Market: contract pair destroyed
    market.reserve_balance -= payout_per_share * trade.quantity  # type: ignore[attr-defined]
    market.total_yes_shares -= trade.quantity  # type: ignore[attr-defined]
    market.total_no_shares -= trade.quantity  # type: ignore[attr-defined]
    # pnl adjustments: refund to both sides from reserve
    market.pnl_pool -= yes_proceeds - yes_cost_rel  # type: ignore[attr-defined]
    market.pnl_pool -= no_proceeds - no_cost_rel  # type: ignore[attr-defined]

    sell_realized_pnl = yes_proceeds - yes_cost_rel
    buy_realized_pnl = no_proceeds - no_cost_rel
    return (buy_realized_pnl, sell_realized_pnl)
