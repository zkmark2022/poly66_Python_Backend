from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_clearing.infrastructure.ledger import write_ledger
from src.pm_common.errors import InsufficientBalanceError, InsufficientPositionError
from src.pm_order.domain.models import Order

TAKER_FEE_BPS: int = 20  # 0.2%, design doc default


def _calc_max_fee(trade_value: int) -> int:
    """Ceiling division: max taker fee for a given trade value."""
    return (trade_value * TAKER_FEE_BPS + 9999) // 10000


_FREEZE_FUNDS_SQL = text("""
    UPDATE accounts
    SET available_balance = available_balance - :amount,
        frozen_balance     = frozen_balance   + :amount,
        version = version + 1, updated_at = NOW()
    WHERE user_id = :user_id AND available_balance >= :amount
    RETURNING id
""")

_FREEZE_YES_SQL = text("""
    UPDATE positions
    SET yes_pending_sell = yes_pending_sell + :qty, updated_at = NOW()
    WHERE user_id = :user_id AND market_id = :market_id
      AND (yes_volume - yes_pending_sell) >= :qty
    RETURNING id
""")

_FREEZE_NO_SQL = text("""
    UPDATE positions
    SET no_pending_sell = no_pending_sell + :qty, updated_at = NOW()
    WHERE user_id = :user_id AND market_id = :market_id
      AND (no_volume - no_pending_sell) >= :qty
    RETURNING id
""")


async def check_and_freeze(order: Order, db: AsyncSession) -> None:
    """Freeze funds or shares atomically.

    Mutates order.frozen_amount and order.frozen_asset_type.
    """
    if order.book_type in ("NATIVE_BUY", "SYNTHETIC_SELL"):
        trade_value = order.original_price * order.quantity
        freeze_amount = trade_value + _calc_max_fee(trade_value)
        result = await db.execute(
            _FREEZE_FUNDS_SQL, {"user_id": order.user_id, "amount": freeze_amount}
        )
        row = result.fetchone()
        if row is None:
            raise InsufficientBalanceError(freeze_amount, 0)
        order.frozen_amount = freeze_amount
        order.frozen_asset_type = "FUNDS"
        await write_ledger(
            user_id=order.user_id,
            entry_type="ORDER_FREEZE",
            amount=-freeze_amount,
            balance_after=0,
            reference_type="ORDER",
            reference_id=order.id,
            db=db,
        )
    elif order.book_type == "NATIVE_SELL":
        row = (
            await db.execute(
                _FREEZE_YES_SQL,
                {"user_id": order.user_id, "market_id": order.market_id, "qty": order.quantity},
            )
        ).fetchone()
        if row is None:
            raise InsufficientPositionError(f"Insufficient YES shares: need {order.quantity}")
        order.frozen_amount = order.quantity
        order.frozen_asset_type = "YES_SHARES"
    else:  # SYNTHETIC_BUY
        row = (
            await db.execute(
                _FREEZE_NO_SQL,
                {"user_id": order.user_id, "market_id": order.market_id, "qty": order.quantity},
            )
        ).fetchone()
        if row is None:
            raise InsufficientPositionError(f"Insufficient NO shares: need {order.quantity}")
        order.frozen_amount = order.quantity
        order.frozen_asset_type = "NO_SHARES"
