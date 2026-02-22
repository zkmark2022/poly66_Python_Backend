# src/pm_admin/application/service.py
"""Admin application service."""
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pm_clearing.domain.settlement import settle_market
from src.pm_common.errors import AppError

_GET_MARKET_SQL = text("SELECT id, status FROM markets WHERE id = :market_id")
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
