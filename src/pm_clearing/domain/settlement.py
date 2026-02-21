"""Market settlement — pay out winners and zero the market."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_common.datetime_utils import utc_now

_GET_POSITIONS_SQL = text(
    "SELECT user_id, yes_volume, no_volume FROM positions WHERE market_id = :market_id"
)
_CREDIT_SQL = text(
    "UPDATE accounts"
    " SET available_balance = available_balance + :amount,"
    "     version = version + 1,"
    "     updated_at = NOW()"
    " WHERE user_id = :user_id"
)
_CLEAR_POSITION_SQL = text(
    "UPDATE positions"
    " SET yes_volume=0, yes_cost_sum=0, yes_pending_sell=0,"
    "     no_volume=0, no_cost_sum=0, no_pending_sell=0,"
    "     updated_at=NOW()"
    " WHERE user_id=:user_id AND market_id=:market_id"
)
_SETTLE_MARKET_SQL = text(
    "UPDATE markets"
    " SET status='SETTLED',"
    "     reserve_balance=0,"
    "     pnl_pool=0,"
    "     total_yes_shares=0,"
    "     total_no_shares=0,"
    "     resolution_result=:result,"
    "     settled_at=:settled_at"
    " WHERE id=:market_id"
)


async def settle_market(
    market_id: str,
    outcome: str,
    db: AsyncSession,
) -> None:
    """Phase 1-5: cancel orders (caller responsibility), pay out winners, zero market."""
    rows = (await db.execute(_GET_POSITIONS_SQL, {"market_id": market_id})).fetchall()
    for user_id, yes_vol, no_vol in rows:
        winning_shares = yes_vol if outcome == "YES" else no_vol
        if winning_shares > 0:
            payout = winning_shares * 100
            await db.execute(_CREDIT_SQL, {"user_id": user_id, "amount": payout})
        await db.execute(_CLEAR_POSITION_SQL, {"user_id": user_id, "market_id": market_id})
    await db.execute(
        _SETTLE_MARKET_SQL,
        {"market_id": market_id, "result": outcome, "settled_at": utc_now()},
    )
