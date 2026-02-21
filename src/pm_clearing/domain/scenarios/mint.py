"""MINT scenario: NATIVE_BUY + SYNTHETIC_SELL — create YES/NO contract pair."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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

_ADD_NO_VOLUME_SQL = text("""
    INSERT INTO positions (user_id, market_id, no_volume, no_cost_sum)
    VALUES (:user_id, :market_id, :qty, :cost)
    ON CONFLICT (user_id, market_id) DO UPDATE
    SET no_volume   = positions.no_volume   + :qty,
        no_cost_sum = positions.no_cost_sum + :cost,
        updated_at = NOW()
""")


async def clear_mint(
    trade: TradeResult, market: object, db: AsyncSession
) -> tuple[int | None, int | None]:
    """MINT: NATIVE_BUY + SYNTHETIC_SELL — create YES/NO contract pair."""
    buyer_cost = trade.price * trade.quantity
    seller_cost = (100 - trade.price) * trade.quantity

    # buyer: unfreeze funds, debit YES cost, receive YES shares
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

    # seller (Buy NO): unfreeze funds, debit NO cost, receive NO shares
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

    market.reserve_balance += trade.quantity * 100  # type: ignore[attr-defined]
    market.total_yes_shares += trade.quantity  # type: ignore[attr-defined]
    market.total_no_shares += trade.quantity  # type: ignore[attr-defined]

    return (None, None)
