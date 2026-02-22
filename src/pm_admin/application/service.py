# src/pm_admin/application/service.py
"""Admin application service."""
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_clearing.domain.global_invariants import verify_global_invariants
from src.pm_clearing.domain.invariants import verify_invariants_after_trade
from src.pm_clearing.domain.settlement import settle_market
from src.pm_common.errors import AppError

_GET_MARKET_SQL = text("SELECT id, status FROM markets WHERE id = :market_id")
_LIST_ACTIVE_MARKETS_SQL = text(
    "SELECT id, status, reserve_balance, pnl_pool, total_yes_shares, total_no_shares "
    "FROM markets WHERE status = 'ACTIVE'"
)
_GET_OPEN_ORDERS_SQL = text("""
    SELECT id, user_id, frozen_amount, frozen_asset_type, remaining_quantity
    FROM orders
    WHERE market_id = :market_id AND status IN ('OPEN', 'PARTIALLY_FILLED')
""")
_CANCEL_ORDER_SQL = text("""
    UPDATE orders SET status = 'CANCELLED', cancel_reason = 'MARKET_RESOLVED',
    updated_at = NOW()
    WHERE id = :order_id
""")
_UNFREEZE_FUNDS_SQL = text("""
    UPDATE accounts SET available_balance = available_balance + :amount,
    frozen_balance = frozen_balance - :amount,
    version = version + 1, updated_at = NOW()
    WHERE user_id = :user_id
""")
_UNFREEZE_YES_SQL = text("""
    UPDATE positions SET yes_pending_sell = yes_pending_sell - :qty, updated_at = NOW()
    WHERE user_id = :user_id AND market_id = :market_id
""")
_UNFREEZE_NO_SQL = text("""
    UPDATE positions SET no_pending_sell = no_pending_sell - :qty, updated_at = NOW()
    WHERE user_id = :user_id AND market_id = :market_id
""")
_STATS_SQL = text("""
    SELECT
        COUNT(*) AS total_trades,
        COALESCE(SUM(quantity), 0) AS total_volume,
        COALESCE(SUM(taker_fee + maker_fee), 0) AS total_fees,
        COUNT(DISTINCT buy_user_id) + COUNT(DISTINCT sell_user_id) AS unique_traders
    FROM trades
    WHERE market_id = :market_id
""")


class AdminService:
    async def resolve_market(
        self, market_id: str, outcome: str, db: AsyncSession
    ) -> dict[str, Any]:
        row = (await db.execute(_GET_MARKET_SQL, {"market_id": market_id})).fetchone()
        if row is None:
            raise AppError(3001, "Market not found", http_status=404)
        if row.status != "ACTIVE":
            raise AppError(
                3002, f"Market is not ACTIVE (status={row.status})", http_status=422
            )

        orders = (
            await db.execute(_GET_OPEN_ORDERS_SQL, {"market_id": market_id})
        ).fetchall()
        for o in orders:
            await db.execute(_CANCEL_ORDER_SQL, {"order_id": o.id})
            if o.frozen_asset_type == "FUNDS":
                await db.execute(
                    _UNFREEZE_FUNDS_SQL,
                    {"user_id": o.user_id, "amount": o.frozen_amount},
                )
            elif o.frozen_asset_type == "YES_SHARES":
                await db.execute(
                    _UNFREEZE_YES_SQL,
                    {"user_id": o.user_id, "market_id": market_id, "qty": o.remaining_quantity},
                )
            else:
                await db.execute(
                    _UNFREEZE_NO_SQL,
                    {"user_id": o.user_id, "market_id": market_id, "qty": o.remaining_quantity},
                )

        await settle_market(market_id, outcome, db)
        return {
            "market_id": market_id,
            "outcome": outcome,
            "cancelled_orders": len(orders),
        }

    async def get_market_stats(self, market_id: str, db: AsyncSession) -> dict[str, Any]:
        row = (await db.execute(_GET_MARKET_SQL, {"market_id": market_id})).fetchone()
        if row is None:
            raise AppError(3001, "Market not found", http_status=404)
        stats = (await db.execute(_STATS_SQL, {"market_id": market_id})).fetchone()
        return {
            "market_id": market_id,
            "status": row.status,
            "total_trades": stats.total_trades if stats else 0,
            "total_volume": int(stats.total_volume) if stats else 0,
            "total_fees": int(stats.total_fees) if stats else 0,
            "unique_traders": int(stats.unique_traders) if stats else 0,
        }

    async def verify_all_invariants(self, db: AsyncSession) -> dict[str, object]:
        """Run per-market (INV-1/2/3) and global (INV-G) invariant checks."""
        violations: list[str] = []
        rows = (await db.execute(_LIST_ACTIVE_MARKETS_SQL)).fetchall()
        for row in rows:
            try:
                ms = _MarketStateShim(row)
                await verify_invariants_after_trade(ms, db)
            except AssertionError as e:
                violations.append(str(e))
        global_violations = await verify_global_invariants(db)
        violations.extend(global_violations)
        return {"ok": len(violations) == 0, "violations": violations}


class _MarketStateShim:
    """Duck-typed MarketState for invariant checks (read-only, no fee fields needed)."""

    def __init__(self, row: Any) -> None:
        self.id: str = row.id
        self.reserve_balance: int = row.reserve_balance
        self.pnl_pool: int = row.pnl_pool
        self.total_yes_shares: int = row.total_yes_shares
        self.total_no_shares: int = row.total_no_shares
