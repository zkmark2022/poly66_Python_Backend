"""Auto-netting: cancel opposing YES/NO positions and release frozen cost."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_clearing.domain.fee import calc_released_cost

_GET_POSITION_SQL = text("""
    SELECT yes_volume, yes_cost_sum, yes_pending_sell,
           no_volume,  no_cost_sum,  no_pending_sell
    FROM positions
    WHERE user_id = :user_id AND market_id = :market_id
    FOR UPDATE
""")

_UPDATE_POSITION_NET_SQL = text("""
    UPDATE positions
    SET yes_volume       = yes_volume       - :qty,
        yes_cost_sum     = yes_cost_sum     - :yes_cost,
        no_volume        = no_volume        - :qty,
        no_cost_sum      = no_cost_sum      - :no_cost,
        updated_at = NOW()
    WHERE user_id = :user_id AND market_id = :market_id
""")

_CREDIT_AVAILABLE_SQL = text("""
    UPDATE accounts
    SET available_balance = available_balance + :amount,
        version = version + 1, updated_at = NOW()
    WHERE user_id = :user_id
""")


async def execute_netting_if_needed(
    user_id: str, market_id: str, market: object, db: AsyncSession
) -> int:
    """Auto-net YES+NO positions. Returns qty netted (0 if nothing to net)."""
    row = (
        await db.execute(_GET_POSITION_SQL, {"user_id": user_id, "market_id": market_id})
    ).fetchone()
    if row is None:
        return 0
    yes_vol: int = int(row[0])
    yes_cost: int = int(row[1])
    yes_pend: int = int(row[2])
    no_vol: int = int(row[3])
    no_cost: int = int(row[4])
    no_pend: int = int(row[5])
    available_yes = yes_vol - yes_pend
    available_no = no_vol - no_pend
    nettable = min(available_yes, available_no)
    if nettable <= 0:
        return 0

    yes_cost_rel = calc_released_cost(yes_cost, yes_vol, nettable)
    no_cost_rel = calc_released_cost(no_cost, no_vol, nettable)
    total_cost_released = yes_cost_rel + no_cost_rel
    refund = nettable * 100

    await db.execute(
        _UPDATE_POSITION_NET_SQL,
        {
            "user_id": user_id,
            "market_id": market_id,
            "qty": nettable,
            "yes_cost": yes_cost_rel,
            "no_cost": no_cost_rel,
        },
    )
    await db.execute(_CREDIT_AVAILABLE_SQL, {"user_id": user_id, "amount": refund})

    market.reserve_balance -= refund  # type: ignore[attr-defined]
    market.pnl_pool -= refund - total_cost_released  # type: ignore[attr-defined]

    return nettable
