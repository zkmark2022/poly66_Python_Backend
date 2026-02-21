"""Market invariant verification after each trade."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_COST_SUM_SQL = text("""
    SELECT COALESCE(SUM(yes_cost_sum + no_cost_sum), 0)
    FROM positions
    WHERE market_id = :market_id
""")


async def verify_invariants_after_trade(market: object, db: AsyncSession) -> None:
    """Verify critical market invariants after a trade. Raises AssertionError if violated.

    INV-1: total_yes_shares == total_no_shares
    INV-2: reserve_balance == total_yes_shares * 100
    INV-3: reserve_balance + pnl_pool == total cost_sum across all positions
    """
    yes = market.total_yes_shares  # type: ignore[attr-defined]
    no = market.total_no_shares  # type: ignore[attr-defined]
    reserve = market.reserve_balance  # type: ignore[attr-defined]
    pnl = market.pnl_pool  # type: ignore[attr-defined]
    market_id = market.id  # type: ignore[attr-defined]

    assert yes == no, f"INV-1 violated: yes_shares={yes} != no_shares={no}"
    assert reserve == yes * 100, (
        f"INV-2 violated: reserve={reserve} != yes_shares * 100 = {yes * 100}"
    )

    cost_row = await db.execute(_COST_SUM_SQL, {"market_id": market_id})
    total_cost = cost_row.scalar_one()
    assert reserve + pnl == total_cost, (
        f"INV-3 violated: reserve({reserve}) + pnl({pnl}) = {reserve + pnl} "
        f"!= total_cost_sum={total_cost}"
    )

    logger.debug(
        "Invariants OK: market=%s, reserve=%d, shares=%d", market_id, reserve, yes
    )
